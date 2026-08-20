# Capture evidence: ComfyUI backend 0.32.0

## Upstream identity

- Repository: `https://github.com/Comfy-Org/ComfyUI`
- Tag: `v0.32.0`
- Commit returned by the official remote: `c2bcbecd82ec5ae66594340b395c24ef0217b238`
- `comfyui_version.py`: `0.32.0`
- Local pinned checkout: `.comfyui-source-0.32.0/` (ignored by Git, retained for article research)

The remote identity was checked with:

```text
git ls-remote https://github.com/Comfy-Org/ComfyUI.git refs/tags/v0.32.0 refs/tags/v0.32.0^{}
```

The checkout was created as a shallow, single-tag clone. Its detached `.git/HEAD` contains the full commit above.

## Runtime preparation

An isolated temporary Python 3.12 venv was created with `--system-site-packages` to reuse the existing Torch installation. All v0.32.0 requirements except a second copy of `torch`, `torchvision` and `torchaudio` were installed from the official `requirements.txt`. The pinned packages reported by `/system_stats` were:

- `comfyui-frontend-package==1.48.7`
- `comfyui-workflow-templates==0.11.39`
- `comfyui-embedded-docs==0.5.9`
- `comfy-kitchen==0.2.30`
- `comfy-aimdo==0.4.13`

The first launch stopped during core import because `torchaudio` was absent. `torchaudio==2.11.0` was then installed into the isolated venv; it imported successfully with the available `torch==2.12.1+cu130`. ComfyUI does not pin the Torch family in `requirements.txt`, so the exact capture runtime is recorded in the metadata rather than presented as an upstream pin.

## Clean server launch

The successful server used the official `main.py` and these material arguments:

```text
python main.py --cpu --disable-all-custom-nodes --listen 127.0.0.1 --port 8199 --base-directory <empty-temporary-base> --disable-auto-launch --preview-method none
```

`--disable-all-custom-nodes` produced the official log message `Skipping loading of custom nodes`. Built-in `comfy_extras` and `comfy_api_nodes` remained enabled. A separate `--quick-test-for-ci` run exited with code 0 and emitted no built-in import-failure warning. The OpenGL acceleration warning concerned the optional accelerator, not a node module.

The live `/system_stats` response confirmed backend `0.32.0`, frontend requirement `1.48.7`, templates `0.11.39`, embedded docs `0.5.9`, and deployment environment `local-git`.

## Snapshot and completeness checks

`content/runtime/comfyui-0.32.0.object-info.json` is the exact UTF-8 body returned by `GET /object_info`. It was not pretty-printed, filtered or otherwise rewritten. `content/runtime/comfyui-0.32.0.node-replacements.json` likewise preserves the exact response from `GET /api/node_replacements`.

The endpoint returned 840 node objects. An independent initialization of the same pinned modules produced 840 `NODE_CLASS_MAPPINGS` entries. Because the two counts match, no registered class was lost while `PromptServer.node_info` built the endpoint response.

Filtering happens only in `comfyui-0.32.0.inventory-report.json`. The raw snapshot remains the audit source. For this capture the raw and user-visible counts are both 840 because no loaded record was marked `dev_only` and no test fixture was registered.

Host RAM/device totals from `/system_stats` were deliberately not committed. They do not affect node schemas and would add machine-specific data. Relevant software versions were copied into the metadata file.

## Embedded documentation

`comfyui-embedded-docs==0.5.9` contains 873 English per-node Markdown files. It is not copied into this repository. Resolve a document from the installed distribution with:

```text
python -c "import importlib.metadata as m; print(m.distribution('comfyui-embedded-docs').locate_file('comfyui_embedded_docs/docs/KSampler/en.md'))"
```

Replace `KSampler` with the exact runtime `class_type`. These documents are an official secondary source; the pinned ComfyUI implementation and raw runtime schema remain authoritative for execution contracts.
