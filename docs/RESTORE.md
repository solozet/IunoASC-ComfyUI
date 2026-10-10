# Restoring an IunoASC session

[README](../README.md) · [Русский](RESTORE.ru.md)

## Save a session

1. Open **Outputs · 8083**.
2. Select the outputs to include. Enable **Include inputs** if you also need source images or other input media.
3. Click **Save session · ZIP** and wait for the browser download to finish.

| Archive entry | Contents |
| --- | --- |
| `workflows/` | Saved ComfyUI workflows |
| `settings/comfy.settings.json` | UI settings, when available |
| `inputs/` | Input media, when selected |
| `outputs/` | Selected output files |
| `session.json` | File list and component versions |

Model weights, custom-node packages, HF tokens and Manager configuration are not included.

## Restore on a new Pod

1. Start IunoASC and install the same preset weights and custom nodes. Restart ComfyUI through Manager after installing Spectrum.
2. Extract the session ZIP on your computer.
3. Upload its contents to the following Pod locations. Review existing files before replacing them; keep a copy of current UI settings.

| Archive source | Pod destination |
| --- | --- |
| Contents of `workflows/` | `/opt/ComfyUI/user/default/workflows/` |
| Contents of `inputs/` | `/data/inputs/` |
| Contents of `outputs/` | `/data/outputs/` |
| `settings/comfy.settings.json` | `/opt/ComfyUI/user/default/comfy.settings.json` |

4. Refresh ComfyUI, open the restored workflow and check the selected model and input filenames.

Workflows and UI settings are restored manually; use `session.json` to identify the original component versions if dependencies differ.

## Browser backup

Browser backup on the outputs page stores output copies separately from a session ZIP. After the Pod is offline, use the red download button or the saved-file list on the same page. These copies do not contain workflows or UI settings.
