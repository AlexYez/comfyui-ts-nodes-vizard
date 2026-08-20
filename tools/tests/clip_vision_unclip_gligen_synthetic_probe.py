from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path


def compile_named(path: Path, names: set[str]):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    body = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name in names
    ]
    return compile(ast.Module(body=body, type_ignores=[]), str(path), "exec")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: clip_vision_unclip_gligen_synthetic_probe.py <pinned-comfyui-source>"
        )

    source = Path(sys.argv[1]).resolve()
    calls: dict[str, object] = {"paths": []}

    def filename_list(group: str):
        return [f"{group}-fixture.safetensors"]

    def full_path(group: str, name: str):
        path = f"/models/{group}/{name}"
        calls["paths"].append([group, name, path])
        return path

    def folder_paths_for(group: str):
        calls["folderPathsGroup"] = group
        return [f"/models/{group}"]

    vision_result: object | None = "vision-model"

    def load_vision(path: str):
        calls["visionPath"] = path
        return vision_result

    unclip_result = ("model", "clip", "vae", "embedded-vision")

    def load_checkpoint(path: str, **kwargs):
        calls["checkpointPath"] = path
        calls["checkpointKwargs"] = kwargs
        return unclip_result

    def load_gligen(path: str):
        calls["gligenPath"] = path
        return "gligen-patcher"

    folder_paths = types.SimpleNamespace(
        get_filename_list=filename_list,
        get_full_path_or_raise=full_path,
        get_folder_paths=folder_paths_for,
    )
    comfy = types.SimpleNamespace(
        clip_vision=types.SimpleNamespace(load=load_vision),
        sd=types.SimpleNamespace(
            load_checkpoint_guess_config=load_checkpoint,
            load_gligen=load_gligen,
        ),
    )
    namespace = {
        "folder_paths": folder_paths,
        "comfy": comfy,
        "MAX_RESOLUTION": 16384,
    }
    exec(
        compile_named(
            source / "nodes.py",
            {
                "CLIPVisionLoader",
                "unCLIPCheckpointLoader",
                "GLIGENLoader",
                "GLIGENTextBoxApply",
            },
        ),
        namespace,
    )

    vision_loader = namespace["CLIPVisionLoader"]()
    vision_output = vision_loader.load_clip("vision.safetensors")
    assert vision_output == ("vision-model",)
    vision_result = None
    invalid_error = ""
    try:
        vision_loader.load_clip("invalid.safetensors")
    except RuntimeError as exc:
        invalid_error = str(exc)
    assert invalid_error == (
        "ERROR: clip vision file is invalid and does not contain a valid vision model."
    )

    checkpoint_output = namespace["unCLIPCheckpointLoader"]().load_checkpoint(
        "sd21-unclip.safetensors",
        output_vae=False,
        output_clip=False,
    )
    assert checkpoint_output == unclip_result
    assert calls["checkpointKwargs"] == {
        "output_vae": True,
        "output_clip": True,
        "output_clipvision": True,
        "embedding_directory": ["/models/embeddings"],
    }

    gligen_output = namespace["GLIGENLoader"]().load_gligen(
        "textbox.safetensors"
    )
    assert gligen_output == ("gligen-patcher",)

    class DummyClip:
        def __init__(self):
            self.tokenized: list[str] = []
            self.return_pooled: list[str] = []

        def tokenize(self, text: str):
            self.tokenized.append(text)
            return f"tokens:{text}"

        def encode_from_tokens(self, tokens: str, return_pooled: str):
            assert tokens == "tokens:красный куб"
            self.return_pooled.append(return_pooled)
            return "unused-token-conditioning", "unprojected-pooled"

    clip = DummyClip()
    tensor_one = {"tensor": 1}
    tensor_two = {"tensor": 2}
    first_metadata = {"keep": "first"}
    old_params = [["old-pooled", 1, 2, 3, 4]]
    second_metadata = {
        "keep": "second",
        "gligen": ("position", "old-model", old_params),
    }
    conditioning = [
        [tensor_one, first_metadata],
        [tensor_two, second_metadata],
    ]
    applied = namespace["GLIGENTextBoxApply"]().append(
        conditioning,
        clip,
        "new-model",
        "красный куб",
        width=256,
        height=128,
        x=64,
        y=32,
    )[0]
    expected_new = ("unprojected-pooled", 16, 32, 4, 8)
    assert applied[0][1]["gligen"] == (
        "position",
        "new-model",
        [expected_new],
    )
    assert applied[1][1]["gligen"] == (
        "position",
        "new-model",
        old_params + [expected_new],
    )
    assert applied[0][0] is tensor_one and applied[1][0] is tensor_two
    assert applied[0][1] is not first_metadata
    assert applied[1][1] is not second_metadata
    assert "gligen" not in first_metadata
    assert second_metadata["gligen"][1] == "old-model"
    assert clip.tokenized == ["красный куб"]
    assert clip.return_pooled == ["unprojected"]

    print(
        json.dumps(
            {
                "clipVisionLoader": {
                    "output": vision_output,
                    "validPath": calls["visionPath"],
                    "invalidError": invalid_error,
                },
                "unclipCheckpointLoader": {
                    "output": checkpoint_output,
                    "path": calls["checkpointPath"],
                    "kwargs": calls["checkpointKwargs"],
                },
                "gligenLoader": {
                    "output": gligen_output,
                    "path": calls["gligenPath"],
                },
                "gligenTextBoxApply": {
                    "tokenized": clip.tokenized,
                    "returnPooled": clip.return_pooled,
                    "newParam": list(expected_new),
                    "firstGligen": applied[0][1]["gligen"],
                    "secondGligen": applied[1][1]["gligen"],
                    "tensorIdentityPreserved": (
                        applied[0][0] is tensor_one and applied[1][0] is tensor_two
                    ),
                    "metadataCopied": (
                        applied[0][1] is not first_metadata
                        and applied[1][1] is not second_metadata
                    ),
                    "sourceMetadataUnchanged": (
                        "gligen" not in first_metadata
                        and second_metadata["gligen"][1] == "old-model"
                    ),
                },
                "resolvedPaths": calls["paths"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
