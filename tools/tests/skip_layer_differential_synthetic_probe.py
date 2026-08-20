from __future__ import annotations

import ast
import copy
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch


class DummyComfyNode:
    pass


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


IO = SimpleNamespace(ComfyNode=DummyComfyNode, NodeOutput=DummyNodeOutput)


def selected_top_level_definitions(
    path: Path,
    *,
    functions: set[str] = frozenset(),
    classes: set[str] = frozenset(),
) -> list[ast.stmt]:
    """Parse a pinned module and return only the requested exact definitions."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    selected: list[ast.stmt] = []
    found_functions: set[str] = set()
    found_classes: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in functions:
            selected.append(node)
            found_functions.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name in classes:
            selected.append(node)
            found_classes.add(node.name)
    if found_functions != functions or found_classes != classes:
        raise AssertionError(
            f"missing exact definitions in {path}: "
            f"functions={sorted(functions - found_functions)}, "
            f"classes={sorted(classes - found_classes)}"
        )
    return selected


def execute_selected(
    path: Path,
    *,
    namespace: dict[str, Any],
    functions: set[str] = frozenset(),
    classes: set[str] = frozenset(),
) -> dict[str, Any]:
    module = ast.Module(
        body=selected_top_level_definitions(path, functions=functions, classes=classes),
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return {name: namespace[name] for name in functions | classes}


def execute_model_patcher_methods(path: Path, namespace: dict[str, Any]) -> type:
    """Build a tiny class from three exact ModelPatcher setter methods."""

    wanted = {
        "set_model_sampler_post_cfg_function",
        "set_model_sampler_calc_cond_batch_function",
        "set_model_denoise_mask_function",
    }
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    source_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ModelPatcher"
    )
    methods = [
        node
        for node in source_class.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    found = {node.name for node in methods}
    if found != wanted:
        raise AssertionError(f"missing ModelPatcher setters: {sorted(wanted - found)}")
    tiny_class = ast.ClassDef(
        name="ExactModelPatcherSetters",
        bases=[],
        keywords=[],
        body=methods,
        decorator_list=[],
    )
    module = ast.Module(body=[tiny_class], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace["ExactModelPatcherSetters"]


class LinearSampling:
    sigma_min = 0.0

    @staticmethod
    def percent_to_sigma(percent: float) -> float:
        return 10.0 * (1.0 - float(percent))

    @staticmethod
    def timestep(sigma: Any) -> Any:
        return sigma


class BatchRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.single_value = torch.tensor([0.0, 1.0, 2.0, 4.0])

    def clear(self) -> None:
        self.calls.clear()

    def __call__(
        self,
        model: object,
        conds: list[object | None],
        x: torch.Tensor,
        sigma: torch.Tensor,
        model_options: dict[str, Any],
    ) -> tuple[torch.Tensor, ...]:
        self.calls.append(
            {
                "model": model,
                "conds": list(conds),
                "sigma": float(sigma[0]),
                "options": model_options,
            }
        )
        if len(conds) == 1:
            return (self.single_value.to(dtype=x.dtype, device=x.device).reshape_as(x),)

        values: list[torch.Tensor] = []
        for cond in conds:
            if cond is None:
                value = -100.0
            elif cond == "cond":
                value = 11.0
            elif cond == "uncond":
                value = 22.0
            else:
                value = 33.0
            values.append(torch.full_like(x, value))
        return tuple(values)


def patch_keys(options: dict[str, Any]) -> dict[str, list[int]]:
    patches = (
        options.get("transformer_options", {})
        .get("patches_replace", {})
        .get("dit", {})
    )
    return {
        "double": sorted(
            int(key[1])
            for key in patches
            if isinstance(key, tuple) and key[0] == "double_block"
        ),
        "single": sorted(
            int(key[1])
            for key in patches
            if isinstance(key, tuple) and key[0] == "single_block"
        ),
    }


def tensor_values(value: torch.Tensor) -> list[float]:
    return [float(item) for item in value.flatten()]


def run() -> dict[str, Any]:
    source_root = Path(sys.argv[1]).resolve()
    slg_path = source_root / "comfy_extras" / "nodes_slg.py"
    sd3_path = source_root / "comfy_extras" / "nodes_sd3.py"
    differential_path = source_root / "comfy_extras" / "nodes_differential_diffusion.py"
    patcher_path = source_root / "comfy" / "model_patcher.py"
    for path in (slg_path, sd3_path, differential_path, patcher_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    patcher_namespace: dict[str, Any] = {}
    patcher_functions = execute_selected(
        patcher_path,
        namespace=patcher_namespace,
        functions={"set_model_options_patch_replace", "set_model_options_post_cfg_function"},
    )
    exact_setters = execute_model_patcher_methods(patcher_path, patcher_namespace)
    set_patch = patcher_functions["set_model_options_patch_replace"]

    class PatchableModel(exact_setters):
        def __init__(
            self,
            sampling: LinearSampling | None = None,
            model_options: dict[str, Any] | None = None,
        ) -> None:
            self.sampling = sampling or LinearSampling()
            self.model_options = (
                copy.deepcopy(model_options)
                if model_options is not None
                else {"transformer_options": {}}
            )

        def get_model_object(self, name: str) -> LinearSampling:
            if name != "model_sampling":
                raise AssertionError(name)
            return self.sampling

        def clone(self) -> "PatchableModel":
            return PatchableModel(self.sampling, self.model_options)

    recorder = BatchRecorder()
    comfy_stub = SimpleNamespace(
        model_patcher=SimpleNamespace(set_model_options_patch_replace=set_patch),
        samplers=SimpleNamespace(calc_cond_batch=recorder),
    )
    node_namespace: dict[str, Any] = {
        "comfy": comfy_stub,
        "io": IO,
        "re": re,
        "torch": torch,
    }
    slg_definitions = execute_selected(
        slg_path,
        namespace=node_namespace,
        classes={"SkipLayerGuidanceDiT", "SkipLayerGuidanceDiTSimple"},
    )
    dit_class = slg_definitions["SkipLayerGuidanceDiT"]
    simple_class = slg_definitions["SkipLayerGuidanceDiTSimple"]

    sd3_namespace = dict(node_namespace)
    sd3_namespace["SkipLayerGuidanceDiT"] = dit_class
    sd3_class = execute_selected(
        sd3_path,
        namespace=sd3_namespace,
        classes={"SkipLayerGuidanceSD3"},
    )["SkipLayerGuidanceSD3"]

    differential_namespace = {"io": IO, "torch": torch}
    differential_class = execute_selected(
        differential_path,
        namespace=differential_namespace,
        classes={"DifferentialDiffusion"},
    )["DifferentialDiffusion"]

    original = PatchableModel()
    empty_output = dit_class.execute(
        original,
        scale=3.0,
        start_percent=0.2,
        end_percent=0.8,
        double_layers="none",
        single_layers="-",
    ).values[0]
    assert empty_output is original

    parsed = dit_class.execute(
        original,
        scale=2.0,
        start_percent=0.2,
        end_percent=0.8,
        double_layers="-1, x2, 03, 4.5, 2",
        single_layers="none 007",
        rescaling_scale=0.0,
    ).values[0]
    parsed_hook = parsed.model_options["sampler_post_cfg_function"][-1]
    x = torch.zeros(4)
    cond_pred = torch.tensor([1.0, 3.0, 6.0, 10.0])
    cfg_result = torch.tensor([2.0, 4.0, 5.0, 9.0])

    def post_args(sigma: float) -> dict[str, Any]:
        return {
            "model": object(),
            "cond_denoised": cond_pred,
            "cond": "cond",
            "denoised": cfg_result,
            "sigma": torch.tensor([sigma]),
            "input": x,
            "model_options": {"transformer_options": {}, "preserved": "yes"},
        }

    recorder.clear()
    upper_result = parsed_hook(post_args(8.0))
    after_upper = len(recorder.calls)
    lower_result = parsed_hook(post_args(2.0))
    after_lower = len(recorder.calls)
    outside_result = parsed_hook(post_args(9.0))
    after_outside = len(recorder.calls)
    parsed_keys = patch_keys(recorder.calls[0]["options"])
    assert parsed_keys == {"double": [1, 2, 3, 4, 5], "single": [7]}
    assert (after_upper, after_lower, after_outside) == (1, 2, 2)
    assert torch.equal(outside_result, cfg_result)

    scale_zero = dit_class.execute(
        original,
        scale=0.0,
        start_percent=0.2,
        end_percent=0.8,
        double_layers="1",
        single_layers="",
    ).values[0]
    recorder.clear()
    scale_zero_result = scale_zero.model_options["sampler_post_cfg_function"][-1](post_args(5.0))
    assert not recorder.calls and scale_zero_result is cfg_result
    scale_zero_bypasses = not recorder.calls and scale_zero_result is cfg_result

    reversed_window = dit_class.execute(
        original,
        scale=3.0,
        start_percent=0.8,
        end_percent=0.2,
        double_layers="1",
        single_layers="",
    ).values[0]
    recorder.clear()
    reversed_result = reversed_window.model_options["sampler_post_cfg_function"][-1](post_args(5.0))
    assert not recorder.calls and reversed_result is cfg_result
    reversed_window_bypasses = not recorder.calls and reversed_result is cfg_result

    rescaled = dit_class.execute(
        original,
        scale=2.0,
        start_percent=0.2,
        end_percent=0.8,
        double_layers="1",
        single_layers="",
        rescaling_scale=1.0,
    ).values[0]
    recorder.clear()
    rescaled_result = rescaled.model_options["sampler_post_cfg_function"][-1](post_args(5.0))
    raw_result = cfg_result + (cond_pred - recorder.single_value) * 2.0
    expected_factor = cond_pred.std() / raw_result.std()
    assert torch.allclose(rescaled_result, raw_result * expected_factor)
    assert torch.allclose(rescaled_result.std(), cond_pred.std())

    first_patch = lambda args, extra: ("first", args, extra)
    second_patch = lambda args, extra: ("second", args, extra)
    other_patch = lambda args, extra: ("other", args, extra)
    untouched = {
        "transformer_options": {
            "kept": "yes",
            "patches_replace": {
                "dit": {("double_block", 2): first_patch},
                "other": {("block", 9): other_patch},
            },
        }
    }
    working = untouched.copy()
    replaced = set_patch(working, second_patch, "dit", "double_block", 2)
    replaced_patches = replaced["transformer_options"]["patches_replace"]
    original_patches = untouched["transformer_options"]["patches_replace"]
    assert replaced_patches["dit"][("double_block", 2)] is second_patch
    assert original_patches["dit"][("double_block", 2)] is first_patch
    assert replaced_patches["other"][("block", 9)] is other_patch
    assert replaced["transformer_options"]["kept"] == "yes"

    sentinel_post = lambda args: args
    post_base = PatchableModel(
        model_options={
            "transformer_options": {},
            "sampler_post_cfg_function": [sentinel_post],
        }
    )
    post_once = dit_class.execute(
        post_base, 1.0, 0.2, 0.8, double_layers="1", single_layers=""
    ).values[0]
    post_twice = dit_class.execute(
        post_once, 1.0, 0.2, 0.8, double_layers="2", single_layers=""
    ).values[0]
    post_hooks = post_twice.model_options["sampler_post_cfg_function"]
    assert len(post_hooks) == 3 and post_hooks[0] is sentinel_post

    simple = simple_class.execute(
        original,
        start_percent=0.2,
        end_percent=0.8,
        double_layers="3",
        single_layers="",
    ).values[0]
    simple_hook = simple.model_options["sampler_calc_cond_batch_function"]

    def simple_args(sigma: float, uncond: object | None = "uncond") -> dict[str, Any]:
        return {
            "input": torch.zeros(1),
            "model": object(),
            "conds": ["cond", uncond],
            "sigma": torch.tensor([sigma]),
            "model_options": {"transformer_options": {}, "preserved": "yes"},
        }

    recorder.clear()
    simple_upper = simple_hook(simple_args(8.0))
    upper_patterns = [call["conds"] for call in recorder.calls]
    upper_patch_keys = [patch_keys(call["options"]) for call in recorder.calls]
    assert upper_patterns == [["cond", None], [None, "uncond"]]
    assert upper_patch_keys == [
        {"double": [], "single": []},
        {"double": [3], "single": []},
    ]
    assert [float(value) for value in simple_upper] == [11.0, 22.0]

    recorder.clear()
    simple_hook(simple_args(2.0))
    simple_lower_calls = len(recorder.calls)
    recorder.clear()
    simple_outside = simple_hook(simple_args(9.0))
    outside_patterns = [call["conds"] for call in recorder.calls]
    assert simple_lower_calls == 2
    assert outside_patterns == [["cond", "uncond"]]
    assert [float(value) for value in simple_outside] == [11.0, 22.0]

    simple_reversed = simple_class.execute(
        original,
        start_percent=0.8,
        end_percent=0.2,
        double_layers="3",
        single_layers="",
    ).values[0]
    recorder.clear()
    simple_reversed.model_options["sampler_calc_cond_batch_function"](simple_args(5.0))
    reversed_simple_patterns = [call["conds"] for call in recorder.calls]
    assert reversed_simple_patterns == [["cond", "uncond"]]

    recorder.clear()
    cfg_one_result = simple_hook(simple_args(5.0, None))
    cfg_one_patterns = [call["conds"] for call in recorder.calls]
    cfg_one_keys = [patch_keys(call["options"]) for call in recorder.calls]
    assert cfg_one_patterns == [["cond", None]]
    assert cfg_one_keys == [{"double": [], "single": []}]
    assert [float(value) for value in cfg_one_result] == [11.0, -100.0]

    simple_empty = simple_class.execute(
        original,
        start_percent=0.0,
        end_percent=1.0,
        double_layers="none",
        single_layers="none",
    ).values[0]
    assert simple_empty is original

    simple_once = simple_class.execute(
        original, 0.0, 1.0, double_layers="1", single_layers=""
    ).values[0]
    first_calc_hook = simple_once.model_options["sampler_calc_cond_batch_function"]
    simple_twice = simple_class.execute(
        simple_once, 0.0, 1.0, double_layers="2", single_layers=""
    ).values[0]
    second_calc_hook = simple_twice.model_options["sampler_calc_cond_batch_function"]
    assert callable(second_calc_hook) and second_calc_hook is not first_calc_hook
    assert not isinstance(second_calc_hook, list)

    sd3 = sd3_class.execute(
        original,
        layers="4,6",
        scale=1.0,
        start_percent=0.2,
        end_percent=0.8,
    ).values[0]
    recorder.clear()
    sd3.model_options["sampler_post_cfg_function"][-1](post_args(5.0))
    sd3_keys = patch_keys(recorder.calls[0]["options"])
    assert sd3_keys == {"double": [4, 6], "single": []}

    sampling = LinearSampling()
    inner_model = SimpleNamespace(model_sampling=sampling)
    sampler_model = SimpleNamespace(inner_model=inner_model)
    mask = torch.tensor([0.25, 0.5, 0.75])
    extra_options = {"model": sampler_model, "sigmas": torch.tensor([10.0, 0.0])}
    binary = differential_class.forward(
        torch.tensor([5.0]), mask, extra_options, strength=1.0
    )
    strength_zero = differential_class.forward(
        torch.tensor([5.0]), mask, extra_options, strength=0.0
    )
    half = differential_class.forward(
        torch.tensor([5.0]), mask, extra_options, strength=0.5
    )
    upper_mask = differential_class.forward(
        torch.tensor([10.0]), mask, extra_options, strength=1.0
    )
    lower_mask = differential_class.forward(
        torch.tensor([0.0]), mask, extra_options, strength=1.0
    )
    assert torch.equal(binary, torch.tensor([0.0, 1.0, 1.0]))
    assert torch.equal(strength_zero, binary)
    assert torch.allclose(half, torch.tensor([0.125, 0.75, 0.875]))
    assert torch.equal(upper_mask, torch.tensor([0.0, 0.0, 0.0]))
    assert torch.equal(lower_mask, torch.tensor([1.0, 1.0, 1.0]))

    adjusted_options = {
        "model": SimpleNamespace(
            inner_model=SimpleNamespace(
                model_sampling=SimpleNamespace(
                    sigma_min=1.0,
                    timestep=lambda sigma: sigma,
                )
            )
        ),
        "sigmas": torch.tensor([10.0, 2.0]),
    }
    adjusted_mask = differential_class.forward(
        torch.tensor([4.0]),
        torch.tensor([0.20, 0.25, 0.30]),
        adjusted_options,
        strength=1.0,
    )
    assert torch.equal(adjusted_mask, torch.tensor([0.0, 1.0, 1.0]))

    sentinel_mask = lambda *args, **kwargs: (args, kwargs)
    differential_base = PatchableModel(
        model_options={
            "transformer_options": {},
            "denoise_mask_function": sentinel_mask,
        }
    )
    differential_once = differential_class.execute(differential_base, 0.5).values[0]
    first_mask_hook = differential_once.model_options["denoise_mask_function"]
    differential_twice = differential_class.execute(differential_once, 0.25).values[0]
    second_mask_hook = differential_twice.model_options["denoise_mask_function"]
    assert differential_base.model_options["denoise_mask_function"] is sentinel_mask
    assert callable(second_mask_hook) and second_mask_hook is not first_mask_hook
    assert not isinstance(second_mask_hook, list)
    quarter = second_mask_hook(torch.tensor([5.0]), mask, extra_options)
    assert torch.allclose(quarter, torch.tensor([0.1875, 0.625, 0.8125]))

    combined = dit_class.execute(
        PatchableModel(), 1.0, 0.2, 0.8, double_layers="1", single_layers=""
    ).values[0]
    combined = simple_class.execute(
        combined, 0.2, 0.8, double_layers="2", single_layers=""
    ).values[0]
    combined = differential_class.execute(combined, 0.5).values[0]
    assert len(combined.model_options["sampler_post_cfg_function"]) == 1
    assert callable(combined.model_options["sampler_calc_cond_batch_function"])
    assert callable(combined.model_options["denoise_mask_function"])

    return {
        "sourceDefinitions": {
            "classes": sorted(
                [
                    "DifferentialDiffusion",
                    "SkipLayerGuidanceDiT",
                    "SkipLayerGuidanceDiTSimple",
                    "SkipLayerGuidanceSD3",
                ]
            ),
            "patcherFunctions": sorted(patcher_functions),
            "patcherSetters": sorted(
                [
                    "set_model_denoise_mask_function",
                    "set_model_sampler_calc_cond_batch_function",
                    "set_model_sampler_post_cfg_function",
                ]
            ),
        },
        "dit": {
            "emptyReturnsIdentity": empty_output is original,
            "parsedKeys": parsed_keys,
            "inclusiveCallCounts": [after_upper, after_lower],
            "outsideCallCount": after_outside,
            "upperResult": tensor_values(upper_result),
            "lowerResult": tensor_values(lower_result),
            "outsideIsIdentity": outside_result is cfg_result,
            "scaleZeroBypasses": scale_zero_bypasses,
            "reversedWindowBypasses": reversed_window_bypasses,
            "rescaled": tensor_values(rescaled_result),
            "rescaledStd": float(rescaled_result.std()),
            "conditionalStd": float(cond_pred.std()),
            "replacementOverwritesSameKey": replaced_patches["dit"][("double_block", 2)]
            is second_patch,
            "replacementLeavesOriginalNestedMap": original_patches["dit"][("double_block", 2)]
            is first_patch,
            "replacementPreservesOtherNamespaces": replaced_patches["other"][("block", 9)]
            is other_patch,
            "postHookCountAfterTwo": len(post_hooks),
            "preexistingPostHookPreserved": post_hooks[0] is sentinel_post,
        },
        "simple": {
            "emptyReturnsIdentity": simple_empty is original,
            "upperPatterns": upper_patterns,
            "upperPatchKeys": upper_patch_keys,
            "upperResult": [float(value) for value in simple_upper],
            "lowerCallCount": simple_lower_calls,
            "outsidePatterns": outside_patterns,
            "reversedPatterns": reversed_simple_patterns,
            "cfgOnePatterns": cfg_one_patterns,
            "cfgOnePatchKeys": cfg_one_keys,
            "cfgOneResult": [float(value) for value in cfg_one_result],
            "calcHookIsSingletonOverwrite": callable(second_calc_hook)
            and second_calc_hook is not first_calc_hook
            and not isinstance(second_calc_hook, list),
        },
        "sd3": {"delegatedPatchKeys": sd3_keys},
        "differential": {
            "binaryAtHalfway": tensor_values(binary),
            "strengthZero": tensor_values(strength_zero),
            "halfBlend": tensor_values(half),
            "upperBoundary": tensor_values(upper_mask),
            "lowerBoundary": tensor_values(lower_mask),
            "terminalSigmaAdjustment": tensor_values(adjusted_mask),
            "quarterBlendAfterOverwrite": tensor_values(quarter),
            "maskHookIsSingletonOverwrite": callable(second_mask_hook)
            and second_mask_hook is not first_mask_hook
            and not isinstance(second_mask_hook, list),
            "originalMaskHookPreserved": differential_base.model_options[
                "denoise_mask_function"
            ]
            is sentinel_mask,
        },
        "combined": {
            "postHooks": len(combined.model_options["sampler_post_cfg_function"]),
            "calcHookCallable": callable(
                combined.model_options["sampler_calc_cond_batch_function"]
            ),
            "maskHookCallable": callable(combined.model_options["denoise_mask_function"]),
        },
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
