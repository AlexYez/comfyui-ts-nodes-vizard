from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import torch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0"


def load_exact_classes(*names: str) -> dict[str, type]:
    tree = ast.parse((SOURCE / "nodes.py").read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in names
    ]
    if {node.name for node in selected} != set(names):
        raise AssertionError("not all requested classes were found in pinned nodes.py")

    helper_tree = ast.parse((SOURCE / "node_helpers.py").read_text(encoding="utf-8"))
    helper = next(
        node
        for node in helper_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "conditioning_set_values"
    )
    helper_ns: dict[str, object] = {}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "node_helpers.py", "exec"), helper_ns)

    namespace: dict[str, object] = {
        "torch": torch,
        "node_helpers": SimpleNamespace(
            conditioning_set_values=helper_ns["conditioning_set_values"]
        ),
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), "nodes.py", "exec"), namespace)
    return {name: namespace[name] for name in names}  # type: ignore[return-value]


class RecordingVisionEncoder:
    def __init__(self) -> None:
        self.calls: list[tuple[torch.Tensor, bool]] = []

    def encode_image(self, image: torch.Tensor, crop: bool) -> object:
        self.calls.append((image, crop))
        return SimpleNamespace(marker=len(self.calls))


class FixedStyleModel:
    def __init__(self, value: torch.Tensor) -> None:
        self.value = value
        self.inputs: list[object] = []

    def get_cond(self, clip_vision_output: object) -> torch.Tensor:
        self.inputs.append(clip_vision_output)
        return self.value.clone()


class RecordingControlNet:
    copies: list["RecordingControlNet"] = []

    def __init__(self, name: str = "root") -> None:
        self.name = name
        self.hint_calls: list[dict[str, object]] = []
        self.previous: object = "not-called"

    def copy(self) -> "RecordingControlNet":
        clone = RecordingControlNet(f"copy-{len(self.copies)}")
        self.copies.append(clone)
        return clone

    def set_cond_hint(
        self,
        hint: torch.Tensor,
        strength: float,
        percent_range: tuple[float, float] | None = None,
        *,
        vae: object | None = None,
        extra_concat: list[object] | None = None,
    ) -> "RecordingControlNet":
        self.hint_calls.append(
            {
                "hint": hint,
                "strength": strength,
                "percent_range": percent_range,
                "vae": vae,
                "extra_concat": extra_concat,
            }
        )
        return self

    def set_previous_controlnet(self, previous: object) -> None:
        self.previous = previous


def run() -> dict[str, object]:
    classes = load_exact_classes(
        "CLIPVisionEncode",
        "StyleModelApply",
        "unCLIPConditioning",
        "ControlNetApply",
        "ControlNetApplyAdvanced",
    )

    image = torch.arange(2 * 5 * 7 * 3, dtype=torch.float32).reshape(2, 5, 7, 3)
    vision = RecordingVisionEncoder()
    center = classes["CLIPVisionEncode"]().encode(vision, image, "center")[0]
    none = classes["CLIPVisionEncode"]().encode(vision, image, "none")[0]
    assert [call[1] for call in vision.calls] == [True, False]
    assert all(call[0] is image for call in vision.calls)
    assert (center.marker, none.marker) == (1, 2)

    text = torch.arange(8, dtype=torch.float32).reshape(1, 2, 4)
    nested = {"kept": True}
    conditioning = [[text, {"pooled_output": nested}]]
    clip_output = object()
    style_value = torch.ones((1, 3, 4), dtype=torch.float32)
    multiply_style = FixedStyleModel(style_value)
    multiply = classes["StyleModelApply"]().apply_stylemodel(
        conditioning, multiply_style, clip_output, 0.5, "multiply"
    )[0]
    assert multiply_style.inputs == [clip_output]
    assert tuple(multiply[0][0].shape) == (1, 5, 4)
    assert torch.equal(multiply[0][0][:, :2], text)
    assert torch.equal(multiply[0][0][:, 2:], torch.full((1, 3, 4), 0.5))
    assert multiply[0][1] is not conditioning[0][1]
    assert multiply[0][1]["pooled_output"] is nested
    assert "attention_mask" not in multiply[0][1]

    zero_multiply = classes["StyleModelApply"]().apply_stylemodel(
        conditioning, FixedStyleModel(style_value), clip_output, 0.0, "multiply"
    )[0]
    assert tuple(zero_multiply[0][0].shape) == (1, 5, 4)
    assert torch.count_nonzero(zero_multiply[0][0][:, 2:]) == 0

    bias = classes["StyleModelApply"]().apply_stylemodel(
        conditioning,
        FixedStyleModel(torch.ones((1, 2, 4), dtype=torch.float32)),
        clip_output,
        0.25,
        "attn_bias",
    )[0]
    bias_mask = bias[0][1]["attention_mask"]
    assert tuple(bias[0][0].shape) == (1, 4, 4)
    assert tuple(bias_mask.shape) == (1, 5, 5)
    expected_bias = torch.tensor(0.25).log().to(torch.float16)
    assert torch.all(bias_mask[:, :2, 2:4] == expected_bias)
    assert torch.all(bias_mask[:, 4:, 2:4] == expected_bias)
    assert torch.count_nonzero(bias_mask[:, 2:4]) == 0

    no_bias_mask = classes["StyleModelApply"]().apply_stylemodel(
        conditioning,
        FixedStyleModel(torch.ones((1, 1, 4), dtype=torch.float32)),
        clip_output,
        1.0,
        "attn_bias",
    )[0]
    assert "attention_mask" not in no_bias_mask[0][1]

    old_bool_mask = torch.tensor(
        [[[True, False, True, True], [True, True, True, True],
          [False, True, True, True], [True, True, True, False]]]
    )
    masked_conditioning = [[
        text,
        {"attention_mask": old_bool_mask, "attention_mask_img_shape": (1, 2)},
    ]]
    masked = classes["StyleModelApply"]().apply_stylemodel(
        masked_conditioning,
        FixedStyleModel(torch.ones((1, 2, 4), dtype=torch.float32)),
        clip_output,
        0.5,
        "multiply",
    )[0]
    assert masked[0][1]["attention_mask"].dtype == torch.float16
    assert tuple(masked[0][1]["attention_mask"].shape) == (1, 6, 6)
    assert torch.isneginf(masked[0][1]["attention_mask"][0, 0, 1])

    batch_error = False
    try:
        classes["StyleModelApply"]().apply_stylemodel(
            [[torch.zeros((2, 2, 4)), {}]],
            FixedStyleModel(torch.ones((1, 1, 4))),
            clip_output,
            1.0,
            "multiply",
        )
    except RuntimeError:
        batch_error = True
    assert batch_error

    original_unclip = [
        [text, {"tag": "first"}],
        [text, {"unclip_conditioning": [{"marker": "old"}]}],
    ]
    new_clip_output = object()
    unclip = classes["unCLIPConditioning"]().apply_adm(
        original_unclip, new_clip_output, -0.75, 0.2
    )[0]
    assert unclip is not original_unclip
    assert unclip[0][0] is text and unclip[0][1] is not original_unclip[0][1]
    assert "unclip_conditioning" not in original_unclip[0][1]
    assert len(unclip[0][1]["unclip_conditioning"]) == 1
    assert len(unclip[1][1]["unclip_conditioning"]) == 2
    assert unclip[1][1]["unclip_conditioning"][0]["marker"] == "old"
    appended = unclip[1][1]["unclip_conditioning"][1]
    assert appended == {
        "clip_vision_output": new_clip_output,
        "strength": -0.75,
        "noise_augmentation": 0.2,
    }
    assert classes["unCLIPConditioning"]().apply_adm(
        original_unclip, new_clip_output, 0.0, 1.0
    )[0] is original_unclip

    RecordingControlNet.copies.clear()
    previous_control = object()
    legacy_conditioning = [
        [text, {"control": previous_control, "tag": nested}],
        [text, {"tag": nested}],
    ]
    legacy_root = RecordingControlNet()
    legacy = classes["ControlNetApply"]().apply_controlnet(
        legacy_conditioning, legacy_root, image, 0.7
    )[0]
    assert len(RecordingControlNet.copies) == 2
    first_control = legacy[0][1]["control"]
    second_control = legacy[1][1]["control"]
    assert first_control is not second_control
    assert first_control.previous is previous_control
    assert second_control.previous == "not-called"
    assert all(entry[1]["control_apply_to_uncond"] is True for entry in legacy)
    assert all(tuple(c.hint_calls[0]["hint"].shape) == (2, 3, 5, 7) for c in RecordingControlNet.copies)
    assert all(c.hint_calls[0]["hint"].data_ptr() == image.data_ptr() for c in RecordingControlNet.copies)
    assert legacy[0][0] is text and legacy[0][1]["tag"] is nested
    assert "control_apply_to_uncond" not in legacy_conditioning[0][1]
    assert classes["ControlNetApply"]().apply_controlnet(
        legacy_conditioning, legacy_root, image, 0.0
    )[0] is legacy_conditioning

    RecordingControlNet.copies.clear()
    shared_previous = object()
    positive = [[text, {"control": shared_previous}], [text, {}]]
    negative = [[text, {"control": shared_previous}]]
    vae = object()
    advanced_root = RecordingControlNet()
    advanced_positive, advanced_negative = classes["ControlNetApplyAdvanced"]().apply_controlnet(
        positive,
        negative,
        advanced_root,
        image,
        0.66,
        0.1,
        0.8,
        vae=vae,
    )
    assert len(RecordingControlNet.copies) == 2
    assert advanced_positive[0][1]["control"] is advanced_negative[0][1]["control"]
    assert advanced_positive[0][1]["control"] is not advanced_positive[1][1]["control"]
    assert all(
        entry[1]["control_apply_to_uncond"] is False
        for group in (advanced_positive, advanced_negative)
        for entry in group
    )
    for clone in RecordingControlNet.copies:
        call = clone.hint_calls[0]
        assert call["percent_range"] == (0.1, 0.8)
        assert call["vae"] is vae
        assert call["extra_concat"] == []

    return {
        "clipVisionEncode": {
            "cropFlags": [call[1] for call in vision.calls],
            "inputIdentityPreserved": True,
        },
        "styleModelApply": {
            "multiplyShape": list(multiply[0][0].shape),
            "attnBiasMaskShape": list(bias_mask.shape),
            "zeroMultiplyStillAppendsTokens": True,
            "batchMismatchRaises": batch_error,
        },
        "unCLIPConditioning": {
            "appendCount": len(unclip[1][1]["unclip_conditioning"]),
            "zeroStrengthIdentity": True,
        },
        "controlNetApply": {
            "legacyCopiesPerEntry": 2,
            "hintShape": list(first_control.hint_calls[0]["hint"].shape),
            "legacyApplyToUncond": True,
            "advancedCopiesPerPreviousControl": 2,
            "advancedApplyToUncond": False,
        },
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
