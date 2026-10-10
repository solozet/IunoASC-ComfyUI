// Exercise the actual page scripts without downloading weights or opening a GPU Pod.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require(process.env.IUNO_JSDOM_PATH||'jsdom');
const root=path.resolve(__dirname,'../panel/static'),dict=JSON.parse(fs.readFileSync(path.join(root,'i18n.json')));
const presetData=process.env.IUNO_PRESET_FIXTURE?JSON.parse(fs.readFileSync(process.env.IUNO_PRESET_FIXTURE)):{presets:[{id:'native-h3',name:'Native',size_bytes:1e9,remaining_bytes:1e9,files:[{filename:'diffusion_models/x.safetensors',size_bytes:1e9,ready:false}],optional_files:[],custom_nodes:[]},{id:'my-h3',name:'LightSpeed H3',size_bytes:2e9,remaining_bytes:2e9,files:[{filename:'loras/turbo.safetensors',size_bytes:2e9,ready:false}],optional_files:[],custom_nodes:[{name:'Spectrum',repo:'https://github.com/x/y',state:'active'}]}]};
async function ready(window){for(let i=0;i<200;i++){if(window.document.body.dataset.ready==='true')return;await new Promise(r=>setTimeout(r,5))}throw Error('UI did not become ready')}
async function mount(mode,lang='en',videoFixture=false){
 const dom=new JSDOM(fs.readFileSync(path.join(root,mode+'.html'),'utf8'),{url:`https://example-${mode==='models'?8081:mode==='control'?8082:8083}.proxy.runpod.net/?lang=${lang}`,runScripts:'outside-only'}),w=dom.window,calls=[];
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false};w.HTMLMediaElement.prototype.play=()=>Promise.resolve();w.HTMLMediaElement.prototype.pause=()=>{};w.HTMLMediaElement.prototype.load=()=>{};
 w.fetch=async(url,options={})=>{calls.push({url,options});let data;
  if(url==='./i18n.json')data=dict;
  else if(url.startsWith('./api/preset'))data=presetData;
  else if(url==='./api/status')data={gpus:[{name:'GPU',driver:'580',vram_used_mb:100,vram_total_mb:24576,utilization:20}],comfy:{online:true,queue:{running:1,pending:0}},disk:{free_bytes:100e9,used_bytes:50e9,total_bytes:150e9},versions:{comfy:'0.39.0',manager:'4.3',kitchen:'0.2.37',torch:'2.9.1',torch_cuda:'13.0',base_cuda:'13.0.2',attention:'ck'}};
  else if(url.startsWith('./api/outputs/metadata'))data={available:true,width:1088,height:1920,fps:24,codec:'hevc',bit_depth:10,color_transfer:'smpte2084',color_primaries:'bt2020'};
  else if(url.startsWith('./api/outputs'))data={files:videoFixture?[{name:'test.mp4',path:'video/test.mp4',directory:false,video:true,size_bytes:123456}]:[],path:''};
  else if(url==='./api/session')data={id:'session'};
  else if(url==='./api/weights')data={files:['sub/custom.safetensors','another.gguf'],selected:'sub/custom.safetensors'};
  else if(url==='./api/weights/download')data={id:'job'};
  else if(url==='./api/jobs/job')data={state:'done',done:1,total:1,current:'sub/custom.safetensors'};
  else throw Error('Unexpected fetch: '+url);
  return {ok:true,json:async()=>data};
 };
 w.eval(fs.readFileSync(path.join(root,'app.js'),'utf8'));await ready(w);return {dom,w,calls};
}
(async()=>{
 assert.deepEqual(Object.keys(dict),['en','ru','de','fr','zh','ja']);const keys=Object.keys(dict.en).sort();for(const lang of Object.keys(dict))assert.deepEqual(Object.keys(dict[lang]).sort(),keys);
 for(const mode of ['models','outputs','control']){
  const {dom,w}=await mount(mode);const doc=w.document;
  if(mode==='control')assert.equal(doc.getElementById('comfy-status').textContent,dict.en.online);
  for(const lang of Object.keys(dict)){
   doc.getElementById('language').value=lang;doc.getElementById('language').dispatchEvent(new w.Event('change'));
   assert.equal(doc.documentElement.lang,lang==='zh'?'zh-CN':lang);
   assert.equal(doc.querySelector('h1').textContent,dict[lang][mode+'Title']);
   assert.equal(w.localStorage.getItem('iuno-language'),lang);
   const link=doc.getElementById(mode==='models'?'outputs-link':'models-link');assert.equal(new URL(link.href).searchParams.get('lang'),lang);
   for(const el of doc.querySelectorAll('[data-i18n]'))assert.equal(el.textContent,dict[lang][el.dataset.i18n]);
  }
  if(mode==='models')assert.equal(doc.querySelectorAll('.preset-card').length,2);
  dom.window.close();
 }
 const {dom,w,calls}=await mount('models','en');const doc=w.document;
 doc.getElementById('weight-source').value='https://huggingface.co/a/b/resolve/main/sub/custom.safetensors';
 doc.getElementById('weight-type').value='diffusion_models';doc.getElementById('weight-type').dispatchEvent(new w.Event('change'));
 assert.match(doc.getElementById('weight-destination').textContent,/models\/diffusion_models/);
 await doc.getElementById('inspect-weight').onclick();assert.equal(doc.getElementById('weight-file').value,'sub/custom.safetensors');
 await doc.getElementById('download-weight').onclick();const download=calls.find(x=>x.url==='./api/weights/download');assert.equal(JSON.parse(download.options.body).directory,'diffusion_models');assert.equal(doc.getElementById('weight-status').textContent,dict.en.done);
 doc.getElementById('weight-source').value='a/c';doc.getElementById('weight-source').dispatchEvent(new w.Event('input'));assert(doc.getElementById('weight-picker').classList.contains('hidden'));
 dom.window.close();
 const gallery=await mount('outputs','ru',true),gd=gallery.w.document;assert.equal(gd.querySelectorAll('.thumbnail').length,1);assert(gd.querySelector('.output-card h3').textContent==='test.mp4');await gd.querySelector('.thumbnail').onclick();assert.equal(gd.getElementById('video-dialog').open,true);assert.match(gd.getElementById('video-player').src,/api\/outputs\/preview/);assert.match(gd.getElementById('video-meta').textContent,/10 bit/);const checkbox=gd.querySelector('.select-row input');checkbox.checked=true;checkbox.onchange();await gd.getElementById('save-session').onclick();const request=gallery.calls.find(x=>x.url==='./api/session');assert.deepEqual(JSON.parse(request.options.body).outputs,['video/test.mp4']);assert.match(gd.querySelector('iframe').src,/api\/session\/session/);gallery.dom.window.close();
 console.log('Frontend passed: 6 languages on all three pages, video gallery/playback and selected session export, persisted selection, cross-port links, direct-file selection, explicit destination and stale-source reset.');
})().catch(e=>{console.error(e);process.exitCode=1});
