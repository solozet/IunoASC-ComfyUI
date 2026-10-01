"""Parse explicit Hugging Face model sources without guessing weight type."""
from dataclasses import dataclass
import re
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

WEIGHT_SUFFIXES = {'.safetensors', '.gguf', '.ckpt', '.bin', '.pt', '.pth'}
WEIGHT_DIRECTORIES = {'loras', 'diffusion_models', 'text_encoders', 'vae'}


@dataclass(frozen=True)
class HFSource:
    repo: str
    revision: str = 'main'
    filename: str | None = None


def weight_filename(filename: str) -> str:
    path = PurePosixPath(filename)
    if (path.is_absolute() or not path.parts or '..' in path.parts
            or '\\' in filename or any(ord(c) < 32 for c in filename)
            or path.suffix.lower() not in WEIGHT_SUFFIXES):
        raise ValueError('invalid_weight_file')
    return path.as_posix()


def parse_hf_source(value: str) -> HFSource:
    value = value.strip()
    revision, filename = 'main', None
    if '://' in value:
        url = urlsplit(value)
        if url.scheme != 'https' or url.netloc != 'huggingface.co':
            raise ValueError('invalid_hf_source')
        parts = url.path.strip('/').split('/')
        if len(parts) < 2:
            raise ValueError('invalid_hf_source')
        repo = '/'.join(parts[:2])
        if len(parts) > 2:
            if len(parts) < 4 or parts[2] not in {'blob', 'resolve', 'tree'}:
                raise ValueError('invalid_hf_source')
            revision = unquote(parts[3])
            if parts[2] != 'tree':
                filename = weight_filename(unquote('/'.join(parts[4:])))
    else:
        repo = value.strip('/')
    if (not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo)
            or '..' in repo or not revision or '..' in revision
            or '\\' in revision or any(ord(c) < 32 for c in revision)):
        raise ValueError('invalid_hf_source')
    return HFSource(repo, revision, filename)
