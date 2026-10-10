"""Verify source routing, explicit folders and download relocation without big files."""
import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from panel import app as panel_app
from panel.hf_source import parse_hf_source


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(panel_app.app)

    def test_repo_file_branch_and_query_parsing(self):
        for value in ['author/model', 'https://huggingface.co/author/model/']:
            self.assertEqual(parse_hf_source(value).repo, 'author/model')
        source=parse_hf_source('https://huggingface.co/author/model/blob/dev/sub/weight.safetensors?download=true')
        self.assertEqual((source.revision,source.filename),('dev','sub/weight.safetensors'))
        self.assertEqual(parse_hf_source('https://huggingface.co/author/model/tree/main/folder').filename, None)

    def test_reject_external_urls_and_traversal(self):
        for value in ['https://evil.example/author/model', 'https://huggingface.co.evil.example/a/b', '../model', 'https://huggingface.co/a/b/resolve/main/%2e%2e/x.safetensors']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_hf_source(value)
        response=self.client.post('/api/weights/download',json={'repo':'a/b','filename':'x.safetensors','directory':'../outputs'})
        self.assertEqual(response.status_code,400)

    def test_direct_link_selects_only_the_requested_existing_file(self):
        with patch.object(panel_app.HfApi,'list_repo_files',return_value=['sub/x.safetensors','other.gguf','README.md']) as listing:
            data=self.client.post('/api/weights',json={'repo':'https://huggingface.co/a/b/resolve/dev/sub/x.safetensors'}).json()
            self.assertEqual(data['selected'],'sub/x.safetensors')
            self.assertEqual(data['files'],['sub/x.safetensors','other.gguf'])
            listing.assert_called_once_with(repo_id='a/b',revision='dev')

    def test_type_routes_to_selected_folder_even_for_official_repo(self):
        for directory in ['loras','diffusion_models','text_encoders','vae']:
            with self.subTest(directory=directory), patch.object(panel_app,'_new_job',return_value='job') as job:
                response=self.client.post('/api/weights/download',json={'repo':'https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/source/x.safetensors','directory':directory})
                self.assertEqual(response.status_code,200)
                self.assertEqual(job.call_args.args[0],[('Comfy-Org/MiniMax-H3','source/x.safetensors',directory+'/x.safetensors','main')])

    def test_direct_link_preselection_can_be_changed_explicitly(self):
        with patch.object(panel_app,'_new_job',return_value='job') as job:
            response=self.client.post('/api/weights/download',json={'repo':'https://huggingface.co/a/b/resolve/dev/default.safetensors','filename':'other.safetensors','directory':'loras'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(job.call_args.args[0],[('a/b','other.safetensors','loras/other.safetensors','dev')])

    def test_download_moves_to_explicit_folder_and_reuses_finished_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def target(name):return root/name
            def download(**kwargs):
                result=Path(kwargs['local_dir'])/kwargs['filename']
                result.parent.mkdir(parents=True,exist_ok=True)
                result.write_bytes(b'weights')
                return str(result)
            with patch.object(panel_app,'MODEL_DIR',root), patch.object(panel_app,'model_target',target), patch.object(panel_app,'hf_hub_download',side_effect=download) as hf:
                for _ in range(2):
                    job=panel_app._new_job([('Comfy-Org/MiniMax-H3','source/x.safetensors','diffusion_models/x.safetensors','dev')],'',{'diffusion_models/x.safetensors':7})
                    for _ in range(100):
                        if panel_app.jobs[job]['state'] in {'done','failed'}:break
                        time.sleep(.01)
                    self.assertEqual(panel_app.jobs[job]['state'],'done')
                self.assertEqual(hf.call_count,1)
                self.assertEqual(target('diffusion_models/x.safetensors').read_bytes(),b'weights')
                self.assertEqual(hf.call_args.kwargs['revision'],'dev')
                self.assertFalse((root/'source/x.safetensors').exists())

    def test_real_progress_adapter_and_retry_preserve_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);attempts=[]
            def download(**kwargs):
                attempts.append(1)
                if len(attempts)==1:raise ConnectionError('transient')
                with kwargs['tqdm_class'](total=7,name='huggingface_hub.http_get',unit='B') as bar:bar.update(7)
                path=Path(kwargs['local_dir'])/kwargs['filename'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'weights');return str(path)
            with patch.object(panel_app,'MODEL_DIR',root),patch.object(panel_app,'model_target',lambda name:root/name),patch.object(panel_app,'hf_hub_download',side_effect=download),patch.object(panel_app.time,'sleep',lambda delay:None):
                ident=panel_app._new_job([('a/b','x.safetensors','loras/x.safetensors')],'')
                for _ in range(1000):
                    if panel_app.jobs[ident]['state'] in {'done','failed'}:break
                    threading.Event().wait(.001)
                result=panel_app.jobs[ident]
                self.assertEqual(result['state'],'done');self.assertEqual(result['downloaded_bytes'],7);self.assertEqual(result['attempt'],2)


if __name__=='__main__':unittest.main()
