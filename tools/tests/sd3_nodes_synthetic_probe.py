from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy_extras" / "nodes_sd3.py"


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyComfyNode:
    pass


class FolderPathsProbe:
    def __init__(self) -> None:
        self.resolved: list[tuple[str, str]] = []

    def get_full_path_or_raise(self, category: str, name: str) -> str:
        self.resolved.append((category, name))
        if name == "missing.safetensors":
            raise FileNotFoundError(name)
        return f"/models/{category}/{name}"

    @staticmethod
    def get_folder_paths(category: str) -> list[str]:
        if category != "embeddings":
            raise AssertionError(category)
        return ["/models/embeddings", "/extra/embeddings"]


class SDProbe:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.result = object()

    def load_clip(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.result


class ModelManagementProbe:
    @staticmethod
    def intermediate_device() -> torch.device:
        return torch.device("cpu")

    @staticmethod
    def intermediate_dtype() -> torch.dtype:
        return torch.float16


def extract_classes(folder_paths: FolderPathsProbe, sd: SDProbe) -> dict[str, type]:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    wanted = {
        "TripleCLIPLoader",
        "EmptySD3LatentImage",
        "CLIPTextEncodeSD3",
        "ControlNetApplySD3",
    }
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in wanted
    ]
    found = {node.name for node in selected}
    if found != wanted:
        raise AssertionError(f"missing exact classes: {sorted(wanted - found)}")

    io = SimpleNamespace(ComfyNode=DummyComfyNode, NodeOutput=DummyNodeOutput)
    namespace: dict[str, object] = {
        "io": io,
        "folder_paths": folder_paths,
        "comfy": SimpleNamespace(
            sd=sd,
            model_management=ModelManagementProbe,
        ),
        "nodes": SimpleNamespace(MAX_RESOLUTION=16384),
        "torch": torch,
    }
    module = ast.Module(body=selected, type_ignores=[])
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return {name: namespace[name] for name in wanted}  # type: ignore[return-value]


class FakeClip:
    def __init__(self) -> None:
        self.tokenize_calls: list[str] = []
        self.encoded: list[dict[str, list[str]]] = []
        self.encode_result: list[object] | None = None

    def tokenize(self, text: str) -> dict[str, list[str]]:
        self.tokenize_calls.append(text)
        if text == "G two chunks":
            return {"g": ["g1", "g2"], "l": ["unused-l"], "t5xxl": ["unused-t5"]}
        if text == "L one chunk":
            return {"g": ["unused-g"], "l": ["l1"], "t5xxl": ["unused-t5"]}
        if text == "T three chunks":
            return {"g": ["unused-g"], "l": ["unused-l"], "t5xxl": ["t1", "t2", "t3"]}
        if text == "":
            return {"g": ["g-empty"], "l": ["l-empty"], "t5xxl": ["t-empty"]}
        raise AssertionError(text)

    def encode_from_tokens_scheduled(self, tokens: dict[str, list[str]]) -> list[object]:
        snapshot = {key: list(value) for key, value in tokens.items()}
        self.encoded.append(snapshot)
        self.encode_result = ["conditioning", snapshot]
        return self.encode_result


class FakeControl:
    def __init__(self, serial: int) -> None:
        self.serial = serial
        self.hint: torch.Tensor | None = None
        self.strength: float | None = None
        self.percent_range: tuple[float, float] | None = None
        self.vae: object | None = None
        self.extra_concat: list[object] | None = None
        self.previous: object | None = None

    def set_cond_hint(
        self,
        hint: torch.Tensor,
        strength: float,
        percent_range: tuple[float, float],
        *,
        vae: object,
        extra_concat: list[object],
    ) -> "FakeControl":
        self.hint = hint
        self.strength = strength
        self.percent_range = percent_range
        self.vae = vae
        self.extra_concat = extra_concat
        return self

    def set_previous_controlnet(self, previous: object | None) -> "FakeControl":
        self.previous = previous
        return self


class FakeControlTemplate:
    def __init__(self) -> None:
        self.copies: list[FakeControl] = []

    def copy(self) -> FakeControl:
        result = FakeControl(len(self.copies) + 1)
        self.copies.append(result)
        return result


def probe_triple(classes: dict[str, type], folder_paths: FolderPathsProbe, sd: SDProbe) -> dict[str, object]:
    output = classes["TripleCLIPLoader"].execute(
        "clip_l.safetensors",
        "clip_g.safetensors",
        "t5xxl_fp16.safetensors",
    )
    missing_raised = False
    try:
        classes["TripleCLIPLoader"].execute(
            "clip_l.safetensors",
            "missing.safetensors",
            "t5xxl_fp16.safetensors",
        )
    except FileNotFoundError:
        missing_raised = True
    return {
        "resolved": folder_paths.resolved,
        "loadCall": sd.calls[0],
        "resultIdentityPreserved": output.values[0] is sd.result,
        "missingRaisesBeforeLoad": missing_raised and len(sd.calls) == 1,
    }


def latent_payload(output: DummyNodeOutput) -> dict[str, Any]:
    payload = output.values[0]
    if not isinstance(payload, dict):
        raise AssertionError(payload)
    return payload


def probe_empty(classes: dict[str, type]) -> dict[str, object]:
    regular = latent_payload(classes["EmptySD3LatentImage"].execute(80, 96, 2))
    direct_odd = latent_payload(classes["EmptySD3LatentImage"].execute(65, 79, 1))
    samples = regular["samples"]
    odd_samples = direct_odd["samples"]
    return {
        "shape": list(samples.shape),
        "dtype": str(samples.dtype),
        "device": str(samples.device),
        "allZero": bool(torch.count_nonzero(samples) == 0),
        "downscaleRatio": regular["downscale_ratio_spacial"],
        "directOddShape": list(odd_samples.shape),
    }


def probe_encode(classes: dict[str, type]) -> dict[str, object]:
    aligned_clip = FakeClip()
    aligned_output = classes["CLIPTextEncodeSD3"].execute(
        aligned_clip,
        "L one chunk",
        "G two chunks",
        "T three chunks",
        "none",
    )

    none_clip = FakeClip()
    classes["CLIPTextEncodeSD3"].execute(none_clip, "", "", "", "none")

    padded_clip = FakeClip()
    classes["CLIPTextEncodeSD3"].execute(padded_clip, "", "", "", "empty_prompt")
    return {
        "alignedCalls": aligned_clip.tokenize_calls,
        "alignedTokens": aligned_clip.encoded[0],
        "scheduledResultPreserved": aligned_output.values[0] is aligned_clip.encode_result,
        "noneCalls": none_clip.tokenize_calls,
        "noneTokens": none_clip.encoded[0],
        "emptyPromptCalls": padded_clip.tokenize_calls,
        "emptyPromptTokens": padded_clip.encoded[0],
    }


def probe_control(classes: dict[str, type]) -> dict[str, object]:
    embedding_a = object()
    embedding_b = object()
    previous = object()
    nested = {"keep": "same shallow object"}
    positive = [
        [embedding_a, {"control": previous, "nested": nested, "positive": True}],
        [embedding_b, {"nested": nested, "positive": True}],
    ]
    negative = [
        [embedding_a, {"control": previous, "nested": nested, "negative": True}],
        [embedding_b, {"nested": nested, "negative": True}],
    ]
    original_metadata = [item[1].copy() for item in positive + negative]
    image = torch.arange(2 * 4 * 5 * 3, dtype=torch.float32).reshape(2, 4, 5, 3)
    control_template = FakeControlTemplate()
    vae = object()
    output = classes["ControlNetApplySD3"].execute(
        positive,
        negative,
        control_template,
        image,
        0.75,
        0.2,
        0.8,
        vae,
    )
    out_positive, out_negative = output.values
    attached = [item[1]["control"] for item in out_positive + out_negative]

    zero_template = FakeControlTemplate()
    zero_output = classes["ControlNetApplySD3"].execute(
        positive,
        negative,
        zero_template,
        image,
        0.0,
        0.4,
        0.1,
        vae,
    )
    return {
        "copyCountForTwoPreviousChains": len(control_template.copies),
        "sharedPreviousReusesCopy": attached[0] is attached[2],
        "sharedNoneReusesCopy": attached[1] is attached[3],
        "differentPreviousUsesDifferentCopy": attached[0] is not attached[1],
        "hintShape": list(control_template.copies[0].hint.shape),
        "hintEqualsNCHW": bool(torch.equal(control_template.copies[0].hint, image.movedim(-1, 1))),
        "strength": control_template.copies[0].strength,
        "percentRange": control_template.copies[0].percent_range,
        "vaeIdentityPreserved": control_template.copies[0].vae is vae,
        "extraConcat": control_template.copies[0].extra_concat,
        "previousIdentityPreserved": control_template.copies[0].previous is previous,
        "metadataNotMutated": all(
            item[1] == before
            for item, before in zip(positive + negative, original_metadata)
        ),
        "metadataCopied": all(
            out_item[1] is not in_item[1]
            for out_item, in_item in zip(out_positive + out_negative, positive + negative)
        ),
        "nestedMetadataIsShallow": all(
            out_item[1]["nested"] is nested
            for out_item in out_positive + out_negative
        ),
        "embeddingsPreserved": [
            out_positive[0][0] is embedding_a,
            out_positive[1][0] is embedding_b,
            out_negative[0][0] is embedding_a,
            out_negative[1][0] is embedding_b,
        ],
        "applyToUncondFlags": [
            item[1]["control_apply_to_uncond"]
            for item in out_positive + out_negative
        ],
        "zeroReturnsOriginalLists": (
            zero_output.values[0] is positive and zero_output.values[1] is negative
        ),
        "zeroAvoidsCopy": len(zero_template.copies) == 0,
    }


def run() -> dict[str, object]:
    folder_paths = FolderPathsProbe()
    sd = SDProbe()
    classes = extract_classes(folder_paths, sd)
    return {
        "triple": probe_triple(classes, folder_paths, sd),
        "empty": probe_empty(classes),
        "encode": probe_encode(classes),
        "control": probe_control(classes),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
