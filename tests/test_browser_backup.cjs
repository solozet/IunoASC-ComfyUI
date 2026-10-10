const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),os=require('node:os'),path=require('node:path'),{execFileSync}=require('node:child_process');
const zip=require('../panel/static/zip-native.min.js');
(async()=>{
 const items=new Map(),cache={keys:async()=>[...items.keys()].map(url=>new Request(url)),match:async key=>items.get(typeof key==='string'?key:key.url)?.clone(),delete:async key=>items.delete(typeof key==='string'?key:key.url),put:async(key,response)=>{const bytes=await response.arrayBuffer();items.set(typeof key==='string'?key:key.url,new Response(bytes,{headers:response.headers}))}};
 let version='7:1',bytes='original',offline=false,networkCalls=0,archive=[];
 const context={URL,Request,Response,Headers,TransformStream,WritableStream,Blob,Date,Math,setTimeout,clearTimeout,AbortController,console,location:{origin:'https://pod-8083.proxy.runpod.net'},caches:{open:async()=>cache},navigator:{storage:{estimate:async()=>({quota:1e9,usage:0}),persist:async()=>true}},zip,showSaveFilePicker:async()=>({createWritable:async()=>new WritableStream({write:chunk=>archive.push(Buffer.from(chunk))})}),fetch:async url=>{networkCalls++;if(offline)throw Error('Pod terminated');if(url.includes('snapshot'))return Response.json({files:[{path:'video/сцена.mp4',size_bytes:8,version}]});return new Response(bytes,{headers:{'Content-Length':'8'}})}};
 vm.runInNewContext(fs.readFileSync('panel/static/output-backup.js','utf8'),context);const backup=new context.IunoOutputBackup();await backup.init();
 async function capture(v){backup.observe([{path:'video/сцена.mp4',size_bytes:8,version:v}]);backup.observed.get('video/сцена.mp4').stableSince-=6001;await backup.pump();while(backup.busy)await new Promise(r=>setTimeout(r,1))}
 version='8:1';await capture(version);assert.equal(backup.saved.length,1);assert.equal(await (await backup.response('video/сцена.mp4')).text(),'original');
 // A disconnected/truncated transfer must not replace the good copy.
 version='8:2';bytes='bad';await capture(version);assert.equal(await (await backup.response('video/сцена.mp4')).text(),'original');assert.equal(backup.saved[0].version,'8:1');
 // A full transfer from a changing remote file must not replace the good copy.
 bytes='modified';version='8:3';await capture('8:2');assert.equal(await (await backup.response('video/сцена.mp4')).text(),'original');
 offline=true;const before=networkCalls;await backup.export();assert.equal(networkCalls,before);
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'iuno-backup-'));try{const file=path.join(dir,'copies.zip');fs.writeFileSync(file,Buffer.concat(archive));execFileSync('python3',['-c','import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); assert z.read("video/сцена.mp4")==b"original"; assert z.testzip() is None',file])}finally{fs.rmSync(dir,{recursive:true})}
 // A new page instance can recover the existing browser copies without network.
 const reopened=new context.IunoOutputBackup();await reopened.init();assert.equal(reopened.saved.length,1);assert.equal(await (await reopened.response('video/сцена.mp4')).text(),'original');
 // Quota failure stops copying and leaves the existing complete copy intact.
 offline=false;context.navigator.storage.estimate=async()=>({quota:100,usage:99});version='8:4';await capture(version);assert.equal(backup.problem,'cacheQuota');assert.equal(backup.suspended,true);assert.equal(await (await backup.response('video/сцена.mp4')).text(),'original');
 // Offline navigation can use the cached shell, but API calls are never replayed.
 const handlers={},shell=new Map(),shellCache={addAll:async()=>{shell.set(context.location.origin+'/',new Response('<html>outputs</html>'))},match:async key=>shell.get(typeof key==='string'?key:key.url)?.clone(),put:async(key,response)=>shell.set(typeof key==='string'?key:key.url,response)};
 const sw={addEventListener:(type,fn)=>handlers[type]=fn,location:{origin:context.location.origin},registration:{scope:context.location.origin+'/'},skipWaiting:async()=>{},clients:{claim:async()=>{}}};
 const swContext={self:sw,URL,Response,AbortController,setTimeout,clearTimeout,caches:{open:async()=>shellCache},fetch:async()=>{throw Error('Pod gone')}};
 vm.runInNewContext(fs.readFileSync('panel/static/outputs-sw.js','utf8'),swContext);
 let installation;handlers.install({waitUntil:p=>installation=p});await installation;
 let navigation;handlers.fetch({request:{url:context.location.origin+'/?lang=ru',mode:'navigate',method:'GET'},respondWith:p=>navigation=p});assert.equal(await (await navigation).text(),'<html>outputs</html>');
 let intercepted=false;handlers.fetch({request:{url:context.location.origin+'/api/outputs',mode:'cors',method:'GET'},respondWith:()=>intercepted=true});assert.equal(intercepted,false);
 console.log('Browser backup passed: complete copies, truncated/changing-file protection, persisted reopen, and valid ZIP64 export after Pod termination with zero network calls.');
})().catch(e=>{console.error(e);process.exitCode=1});
