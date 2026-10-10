// Cache only the outputs UI. API calls always use the network; output copies are
// written explicitly by output-backup.js after full-body/version validation.
const SHELL='iunoasc-outputs-shell-v1';
const ASSETS=['./','./style.css','./app.js','./i18n.json','./output-backup.js','./zip-native.min.js'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(SHELL).then(cache=>cache.addAll(ASSETS)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',event=>{event.waitUntil(self.clients.claim())});
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);
 if(request.method!=='GET'||url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;
 const isShell=request.mode==='navigate'||ASSETS.slice(1).some(path=>new URL(path,self.registration.scope).pathname===url.pathname);
 if(!isShell)return;
 event.respondWith((async()=>{
  const cache=await caches.open(SHELL),key=request.mode==='navigate'?new URL('./',self.registration.scope).href:request;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);
  try{const response=await fetch(request,{signal:controller.signal});if(!response.ok)throw new Error('offline');await cache.put(key,response.clone());return response}
  catch(error){const saved=await cache.match(key);if(saved)return saved;throw error}finally{clearTimeout(timer)}
 })());
});
