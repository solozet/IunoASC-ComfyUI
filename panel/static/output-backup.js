// Complete output copies live in Cache Storage, isolated to this Pod's HTTPS origin.
// zip.js 2.23.0 is bundled locally; emergency export never contacts the Pod/CDN.
(function(global){
 const CACHE='iunoasc-output-copies-v1',PREFIX='/__iuno_output_copy__/',STAGE='/__iuno_output_staging__/';
 class OutputBackup {
  constructor(onchange=()=>{}){this.onchange=onchange;this.saved=[];this.observed=new Map();this.enabled=true;this.busy=false;this.exporting=false;this.problem='';this.progress=null;this.available=!!global.caches;this.suspended=false;}
  key(path,prefix=PREFIX){return new URL(prefix+encodeURIComponent(path),location.origin).href}
  emit(){this.onchange(this)}
  async init(){
   if(!this.available){this.problem='cacheUnavailable';this.emit();return}
   try{this.cache=await caches.open(CACHE);await this.readSaved();}
   catch{this.available=false;this.problem='cacheUnavailable';this.emit()}
  }
  async readSaved(){
   const saved=[];
   for(const request of await this.cache.keys()){
    if(!new URL(request.url).pathname.startsWith(PREFIX))continue;
    const response=await this.cache.match(request);const encoded=response?.headers.get('X-Iuno-Path');const path=encoded?decodeURIComponent(encoded):null;
    if(path)saved.push({path,size_bytes:Number(response.headers.get('X-Iuno-Size')),version:response.headers.get('X-Iuno-Version')});
   }
   this.saved=saved.sort((a,b)=>a.path.localeCompare(b.path));this.emit();
  }
  observe(files){
   const now=Date.now(),next=new Map();
   for(const file of files){const old=this.observed.get(file.path);next.set(file.path,{...file,stableSince:old?.version===file.version?old.stableSince:now})}
   this.observed=next;void this.pump();
  }
  setEnabled(value){this.enabled=value;this.suspended=false;this.problem='';if(!value)this.controller?.abort();else{void navigator.storage?.persist?.().catch(()=>{});void this.pump()}this.emit()}
  async pump(){
   if(navigator.locks)return navigator.locks.request('iunoasc-output-copies',{ifAvailable:true},lock=>lock?this.capture():undefined);
   return this.capture();
  }
  async capture(){
   if(!this.cache||!this.enabled||this.suspended||this.busy||this.exporting)return;
   const file=[...this.observed.values()].find(f=>f.size_bytes>0&&Date.now()-f.stableSince>=6000&&!this.saved.some(s=>s.path===f.path&&s.version===f.version));
   if(!file)return;
   this.busy=true;this.controller=new AbortController();let idle;
   const stage=this.key(file.path+'-'+Math.random().toString(36).slice(2),STAGE);
   try{
    const space=await navigator.storage?.estimate?.();
    if(space?.quota&&space.quota-(space.usage||0)<file.size_bytes*2+64*1024*1024)throw Object.assign(new Error(),{name:'QuotaExceededError'});
    let loaded=0,lastNotice=0;const touch=()=>{clearTimeout(idle);idle=setTimeout(()=>this.controller.abort(),30000)};touch();
    const response=await fetch('./api/outputs/file?path='+encodeURIComponent(file.path),{cache:'no-store',signal:this.controller.signal});
    if(!response.ok||!response.body)throw new Error('copy_failed');
    const stated=Number(response.headers.get('Content-Length'));if(stated&&stated!==file.size_bytes)throw new Error('changed');
    const stream=response.body.pipeThrough(new TransformStream({transform:(chunk,controller)=>{
     loaded+=chunk.byteLength;touch();if(loaded>file.size_bytes)throw new Error('changed');controller.enqueue(chunk);
     if(Date.now()-lastNotice>500){lastNotice=Date.now();this.progress={path:file.path,loaded,total:file.size_bytes};this.emit()}
    },flush:()=>{if(loaded!==file.size_bytes)throw new Error('incomplete')}}));
    const headers=new Headers({'Content-Type':response.headers.get('Content-Type')||'application/octet-stream','X-Iuno-Path':encodeURIComponent(file.path),'X-Iuno-Size':String(file.size_bytes),'X-Iuno-Version':file.version});
    await this.cache.put(stage,new Response(stream,{headers}));clearTimeout(idle);
    // Do not replace a good previous copy if the remote file changed during transfer.
    const latest=await this.snapshot();if(!latest.files.some(f=>f.path===file.path&&f.version===file.version))return;
    await this.cache.put(this.key(file.path),await this.cache.match(stage));this.problem='';await this.readSaved();
   }catch(e){if(e.name==='QuotaExceededError'){this.problem='cacheQuota';this.suspended=true}else if(this.enabled)this.problem='cacheCopyFailed';}
   finally{clearTimeout(idle);try{await this.cache.delete(stage)}catch{}this.progress=null;this.busy=false;this.emit()}
  }
  async snapshot(){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);try{const r=await fetch('./api/outputs/snapshot',{cache:'no-store',signal:controller.signal});if(!r.ok){const data=await r.json().catch(()=>({}));throw new Error(data.detail?.code||'snapshot_failed')};return await r.json()}finally{clearTimeout(timer)}}
  async response(path){return this.cache?.match(this.key(path))}
  async downloadFile(path){const response=await this.response(path);if(!response)throw new Error('cacheMissing');this.downloadBlob(await response.blob(),path.split('/').pop())}
  downloadBlob(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000)}
  async export(){
   if(!this.cache||!this.saved.length)throw new Error('cacheMissing');
   const total=this.saved.reduce((n,f)=>n+f.size_bytes,0);let target,blobTarget,writer;
   // Call the picker directly in the button gesture, before any network/storage await.
   if(global.showSaveFilePicker){const handle=await global.showSaveFilePicker({suggestedName:'iunoasc-browser-backup.zip',types:[{description:'ZIP archive',accept:{'application/zip':['.zip']}}]});target=await handle.createWritable()}
   else{if(total>512*1024*1024)throw new Error('cacheLargeExport');blobTarget=new global.zip.BlobWriter('application/zip');target=blobTarget}
   this.exporting=true;this.emit();
   try{
    writer=new global.zip.ZipWriter(target,{level:0,zip64:true,useWebWorkers:false,useCompressionStream:false,bufferedWrite:false});
    for(const file of [...this.saved]){const response=await this.response(file.path);if(!response)throw new Error('cacheMissing');await writer.add(file.path,response.body,{level:0,zip64:true,uncompressedSize:Number(response.headers.get('X-Iuno-Size'))})}
    const blob=await writer.close();if(blobTarget)this.downloadBlob(blob,'iunoasc-browser-backup.zip');
   }catch(e){try{await target.abort?.(e)}catch{}throw e}
   finally{this.exporting=false;this.emit()}
  }
 }
 global.IunoOutputBackup=OutputBackup;
})(typeof window==='undefined'?globalThis:window);
