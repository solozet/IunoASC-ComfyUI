import { app } from '../../../scripts/app.js';
app.registerExtension({
 name: 'IunoASC.OpenWorkflow',
 async setup() {
  const url = new URL(location.href), name = url.searchParams.get('iuno_workflow');
  const allowed = ['iunoasc-native-h3.json','lightspeed-h3.json','lightspeed-h3-light-vae.json'];
  if (!allowed.includes(name)) return;
  try {
   const response = await fetch('/userdata/' + encodeURIComponent('workflows/IunoASC/' + name));
   if (!response.ok) throw new Error('Workflow not found');
   await app.loadGraphData(await response.json(), true, true, name);
   url.searchParams.delete('iuno_workflow'); history.replaceState(null, '', url);
  } catch (error) {
   console.error('IunoASC: open workflow', error);
   app.dialog?.show('IunoASC: open the workflow from Workflows → IunoASC.');
  }
 }
});
