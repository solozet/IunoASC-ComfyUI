const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
(async()=>{
 let extension, fetched=false,loaded=false,errors=[];const workflow={path:'workflows/IunoASC/lightspeed-h3.json'};
 const app={extensionManager:{spinner:true,workflow:{getWorkflowByPath:path=>{assert.equal(path,workflow.path);return workflow}}},registerExtension:e=>extension=e,loadGraphData:async(data,clean,view,target)=>{assert.equal(target,workflow);loaded=true},dialog:{show:e=>errors.push(e)}};
 const context={app,window:{},location:{href:'https://test/?iuno_workflow=lightspeed-h3.json'},history:{replaceState:()=>{}},URL,Date,setTimeout,console,fetch:async url=>{fetched=true;assert.match(url,/workflows%2FIunoASC/);return {ok:true,json:async()=>({nodes:[]})}}};
 vm.runInNewContext(fs.readFileSync('custom_nodes/iunoasc_tools/web/open_workflow.js','utf8').replace(/^import[^\n]+\n/,''),context);
 assert.equal(extension.setup(),undefined);await new Promise(r=>setTimeout(r,120));assert.equal(fetched,false);
 context.window.app=app;await new Promise(r=>setTimeout(r,120));assert.equal(fetched,false);
 app.extensionManager.spinner=false;await new Promise(r=>setTimeout(r,120));assert.equal(loaded,true);assert.deepEqual(errors,[]);
 console.log('Workflow link waits for startup/tab restoration and opens the existing saved workflow.');
})().catch(e=>{console.error(e);process.exitCode=1});
