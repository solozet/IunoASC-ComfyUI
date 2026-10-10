import { app } from '../../../scripts/app.js';
app.registerExtension({
 name: 'IunoASC.OpenWorkflow',
 setup() {
  const name = new URL(location.href).searchParams.get('iuno_workflow');
  const allowed = ['iunoasc-native-h3.json','lightspeed-h3.json','lightspeed-h3-light-vae.json'];
  if (!allowed.includes(name)) return;
  // setup must return immediately: ComfyUI restores its tabs after extension setup.
  void (async () => {
   try {
    const deadline = Date.now() + 120000;
    while (window.app !== app || app.extensionManager.spinner) {
     if (Date.now() > deadline) throw new Error('ComfyUI startup timed out');
     await new Promise(resolve => setTimeout(resolve, 100));
    }
    const path = 'workflows/IunoASC/' + name;
    const response = await fetch('/userdata/' + encodeURIComponent(path));
    if (!response.ok) throw new Error('Workflow not found');
    const workflow = app.extensionManager.workflow.getWorkflowByPath(path);
    await app.loadGraphData(await response.json(), true, true, workflow || name);
    const url = new URL(location.href);
    url.searchParams.delete('iuno_workflow'); history.replaceState(null, '', url);
   } catch (error) {
    console.error('IunoASC: open workflow', error);
    app.dialog?.show('IunoASC: open the workflow from Workflows → IunoASC.');
   }
  })();
 }
});
