from __future__ import annotations

import ast
import contextlib
import enum
import json
import logging
import math
from pathlib import Path
from types import SimpleNamespace
import uuid

import torch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0"


def load_definitions(path: Path, names: set[str], namespace: dict, kinds: tuple[type, ...]) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    selected = [node for node in tree.body if isinstance(node, kinds) and getattr(node, "name", None) in names]
    missing = names - {node.name for node in selected}
    if missing:
        raise AssertionError(f"missing exact source definitions in {path}: {sorted(missing)}")
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.Module(body=[future, *selected], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


def load_methods(path: Path, class_name: str, names: set[str], namespace: dict) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    class_node = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        ),
        None,
    )
    if class_node is None:
        raise AssertionError(f"missing exact source class {class_name} in {path}")
    selected = [
        node
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    missing = names - {node.name for node in selected}
    if missing:
        raise AssertionError(
            f"missing exact source methods in {path}:{class_name}: {sorted(missing)}"
        )
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.Module(body=[future, *selected], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


class FakeStateModel:
    def __init__(self, state):
        self._state = state

    def state_dict(self):
        return dict(self._state)


class FakeModelPatcher:
    def __init__(self, state):
        self.model = FakeStateModel(state)


class FakeClip:
    def __init__(self, state):
        self.patcher = FakeModelPatcher(state)


class FakeFolderPaths:
    def __init__(self):
        self.full_path_calls = []

    def get_filename_list(self, category):
        return [f"demo-{category}.safetensors"]

    def get_full_path(self, category, name):
        value = f"/{category}/{name}"
        self.full_path_calls.append((category, name, value))
        return value

    def get_folder_paths(self, category):
        return [f"/{category}"]


class FakeUtils:
    def __init__(self):
        self.load_calls = []

    def load_torch_file(self, path, safe_load=False):
        payload = {"lora_key": torch.tensor([len(self.load_calls) + 1.0])}
        self.load_calls.append((path, safe_load, payload))
        return payload


class FakeSD:
    def __init__(self):
        self.load_calls = []

    def load_checkpoint_guess_config(self, path, **kwargs):
        self.load_calls.append((path, dict(kwargs)))
        load_number = float(len(self.load_calls))
        model = FakeModelPatcher(
            {
                "diffusion.weight": torch.tensor([5.0, load_number]),
                "model_sampling.sigma_data": torch.tensor([0.5]),
            }
        )
        clip = None if "no-clip" in path else FakeClip(
            {"clip.weight": torch.tensor([7.0, load_number])}
        )
        return model, clip, SimpleNamespace(kind="temporary-vae")


class DummyAdapter:
    pass


class FakeModelManagement:
    @staticmethod
    def cast_to_device(value, device, dtype, copy=False):
        result = value.to(device=device, dtype=dtype)
        return result.clone() if copy else result


def main() -> None:
    lora_ns = {
        "torch": torch,
        "logging": logging,
        "weight_adapter": SimpleNamespace(WeightAdapterBase=DummyAdapter, adapters=[]),
        "comfy": SimpleNamespace(model_management=FakeModelManagement()),
    }
    load_definitions(
        SOURCE / "comfy" / "lora.py",
        {"load_lora", "calculate_weight"},
        lora_ns,
        (ast.FunctionDef,),
    )
    load_lora = lora_ns["load_lora"]
    calculate_weight = lora_ns["calculate_weight"]

    class RecordedLoraApi:
        def __init__(self):
            self.load_arguments = []

        @staticmethod
        def model_lora_keys_unet(model, key_map):
            key_map["demo"] = "base.weight"
            return key_map

        @staticmethod
        def model_lora_keys_clip(model, key_map):
            key_map["demo"] = "base.weight"
            return key_map

        def load_lora(self, raw_lora, key_map, log_missing=True):
            self.load_arguments.append(log_missing)
            return load_lora(raw_lora, key_map, log_missing=log_missing)

    recorded_lora_api = RecordedLoraApi()
    hooks_ns = {
        "enum": enum,
        "math": math,
        "torch": torch,
        "comfy": SimpleNamespace(lora=recorded_lora_api),
    }
    load_definitions(
        SOURCE / "comfy" / "hooks.py",
        {
            "EnumHookType",
            "EnumWeightTarget",
            "EnumHookScope",
            "_HookRef",
            "default_should_register",
            "Hook",
            "WeightHook",
            "HookGroup",
            "HookKeyframe",
            "HookKeyframeGroup",
            "create_hook_lora",
            "create_hook_model_as_lora",
            "get_patch_weights_from_model",
        },
        hooks_ns,
        (ast.ClassDef, ast.FunctionDef),
    )
    HookGroup = hooks_ns["HookGroup"]
    WeightHook = hooks_ns["WeightHook"]
    HookKeyframe = hooks_ns["HookKeyframe"]
    EnumWeightTarget = hooks_ns["EnumWeightTarget"]

    folder_paths = FakeFolderPaths()
    utils = FakeUtils()
    sd = FakeSD()
    comfy_hooks = SimpleNamespace(
        HookGroup=HookGroup,
        create_hook_lora=hooks_ns["create_hook_lora"],
        create_hook_model_as_lora=hooks_ns["create_hook_model_as_lora"],
        get_patch_weights_from_model=hooks_ns["get_patch_weights_from_model"],
    )
    nodes_ns = {
        "folder_paths": folder_paths,
        "comfy": SimpleNamespace(hooks=comfy_hooks, utils=utils, sd=sd),
    }
    load_definitions(
        SOURCE / "comfy_extras" / "nodes_hooks.py",
        {
            "CreateHookLora",
            "CreateHookLoraModelOnly",
            "CreateHookModelAsLora",
            "CreateHookModelAsLoraModelOnly",
        },
        nodes_ns,
        (ast.ClassDef,),
    )

    prior_hook = WeightHook(strength_model=0.1, strength_clip=0.2)
    prior = HookGroup()
    prior.add(prior_hook)
    lora_node = nodes_ns["CreateHookLora"]()
    first_lora = lora_node.create_hook("style-a.safetensors", 0.8, 0.4, prior)[0]
    first_weight_hook = first_lora.hooks[-1]
    second_lora = lora_node.create_hook("style-a.safetensors", 0.2, -0.3, prior)[0]
    second_weight_hook = second_lora.hooks[-1]
    zero_lora = lora_node.create_hook("not-loaded.safetensors", 0.0, 0.0, prior)[0]

    lora_model_only_node = nodes_ns["CreateHookLoraModelOnly"]()
    before_model_only_loads = len(utils.load_calls)
    zero_lora_model_only = lora_model_only_node.create_hook_model_only(
        "also-not-loaded.safetensors", 0.0, prior
    )[0]
    model_only_load_delta = len(utils.load_calls) - before_model_only_loads

    model_as_node = nodes_ns["CreateHookModelAsLora"]()
    before_model_as = len(sd.load_calls)
    zero_model_as = model_as_node.create_hook("target.ckpt", 0.0, 0.0, prior)[0]
    zero_model_hook = zero_model_as.hooks[-1]
    first_model_as_load_delta = len(sd.load_calls) - before_model_as
    second_model_as = model_as_node.create_hook("target.ckpt", 1.0, 0.5, prior)[0]
    second_model_hook = second_model_as.hooks[-1]
    same_path_load_delta = len(sd.load_calls) - before_model_as
    before_changed_path = len(sd.load_calls)
    model_as_node.create_hook("target-b.ckpt", 1.0, 1.0, prior)
    changed_path_load_delta = len(sd.load_calls) - before_changed_path

    model_only_node = nodes_ns["CreateHookModelAsLoraModelOnly"]()
    before_checkpoint_model_only = len(sd.load_calls)
    zero_checkpoint_model_only = model_only_node.create_hook_model_only("target.ckpt", 0.0, prior)[0]
    checkpoint_model_only_delta = len(sd.load_calls) - before_checkpoint_model_only
    checkpoint_model_only_hook = zero_checkpoint_model_only.hooks[-1]

    no_clip_node = nodes_ns["CreateHookModelAsLora"]()
    no_clip_group = no_clip_node.create_hook("no-clip.ckpt", 1.0, 1.0, prior)[0]
    no_clip_hook = no_clip_group.hooks[-1]

    base = torch.tensor([1.0, 3.0])
    target = torch.tensor([5.0, 1.0])

    def model_as_value(strength, current=None, target_value=None):
        current = base.clone() if current is None else current.clone()
        target_value = target if target_value is None else target_value
        patch = (strength, ("model_as_lora", (target_value,)), 1.0, None, None)
        original = {"w": [(base.clone(), lambda value, **kwargs: value)]}
        return calculate_weight([patch], current, "w", original_weights=original).tolist()

    diff_patch = load_lora(
        {"demo.diff": torch.tensor([2.0, -1.0]), "unused.diff": torch.tensor([9.0])},
        {"demo": "w"},
        log_missing=False,
    )["w"]
    set_patch = load_lora(
        {"demo.set_weight": torch.tensor([9.0, 8.0])},
        {"demo": "w"},
        log_missing=False,
    )["w"]

    def calculate_simple(patch, strength, value=None):
        value = base.clone() if value is None else value.clone()
        wrapped = (strength, patch, 1.0, None, None)
        return calculate_weight([wrapped], value, "w").tolist()

    set_then_diff = calculate_weight(
        [
            (0.0, set_patch, 1.0, None, None),
            (1.0, diff_patch, 1.0, None, None),
        ],
        base.clone(),
        "w",
    ).tolist()
    diff_then_set = calculate_weight(
        [
            (1.0, diff_patch, 1.0, None, None),
            (0.0, set_patch, 1.0, None, None),
        ],
        base.clone(),
        "w",
    ).tolist()

    shape_error = None
    try:
        model_as_value(1.0, target_value=torch.tensor([1.0, 2.0, 3.0]))
    except RuntimeError as exc:
        shape_error = type(exc).__name__

    method_ns = {"uuid": uuid, "math": math}
    load_methods(
        SOURCE / "comfy" / "model_patcher.py",
        "ModelPatcher",
        {"add_hook_patches", "get_combined_hook_patches"},
        method_ns,
    )

    class ExactMethodPatcher:
        add_hook_patches = method_ns["add_hook_patches"]
        get_combined_hook_patches = method_ns["get_combined_hook_patches"]

        def __init__(self):
            self.model = FakeStateModel({"base.weight": torch.tensor([1.0, 3.0])})
            self.hook_patches = {}
            self.patches_uuid = None

        @staticmethod
        def use_ejected():
            return contextlib.nullcontext()

    patcher = ExactMethodPatcher()
    registered = HookGroup()
    adapter_hook = WeightHook(strength_model=0.8, strength_clip=0.0)
    adapter_hook.weights = {
        "demo.diff": torch.tensor([2.0, -1.0]),
        "unused.diff": torch.tensor([7.0]),
    }
    adapter_hook.add_hook_patches(
        patcher,
        {},
        {"target": EnumWeightTarget.Model},
        registered,
    )

    target_hook = WeightHook(strength_model=0.6, strength_clip=0.0)
    target_hook.weights = {
        "base.weight": ("model_as_lora", (torch.tensor([5.0, 1.0]),)),
        "target.only": ("model_as_lora", (torch.tensor([4.0]),)),
    }
    target_hook.weights_clip = None
    target_hook.need_weight_init = False
    target_hook.hook_keyframe._current_keyframe = HookKeyframe(strength=0.25)
    target_hook.add_hook_patches(
        patcher,
        {},
        {"target": EnumWeightTarget.Model},
        registered,
    )

    prior_exact = HookGroup()
    prior_exact.add(adapter_hook)
    added_exact = HookGroup()
    added_exact.add(target_hook)
    ordered_group = prior_exact.clone_and_combine(added_exact)
    deduplicated_group = prior_exact.clone_and_combine(prior_exact)
    combined_patches = patcher.get_combined_hook_patches(ordered_group)

    set_patcher = ExactMethodPatcher()
    zero_set_hook = WeightHook(strength_model=0.0, strength_clip=0.0)
    zero_set_hook.weights = {"demo.set_weight": torch.tensor([9.0, 8.0])}
    zero_set_registered = HookGroup()
    zero_set_hook.add_hook_patches(
        set_patcher,
        {},
        {"target": EnumWeightTarget.Model},
        zero_set_registered,
    )
    zero_set_group = HookGroup()
    zero_set_group.add(zero_set_hook)
    zero_set_patches = set_patcher.get_combined_hook_patches(zero_set_group)["base.weight"]
    zero_set_result = calculate_weight(
        zero_set_patches,
        base.clone(),
        "base.weight",
    ).tolist()

    result = {
        "lora": {
            "loadCalls": len(utils.load_calls),
            "sameFileLoadedOnce": len(utils.load_calls) == 1,
            "safeLoad": utils.load_calls[0][1],
            "cachedPayloadIdentity": first_weight_hook.weights is second_weight_hook.weights,
            "firstStrengths": [first_weight_hook._strength_model, first_weight_hook._strength_clip],
            "secondStrengths": [second_weight_hook._strength_model, second_weight_hook._strength_clip],
            "priorPreserved": (
                first_lora.hooks[0].hook_ref is prior_hook.hook_ref
                and len(prior.hooks) == 1
                and prior.hooks[0] is prior_hook
            ),
            "zeroReturnsPriorIdentity": zero_lora is prior,
            "zeroDoesNotResolveNewPath": not any(call[1] == "not-loaded.safetensors" for call in folder_paths.full_path_calls),
            "modelOnlyZeroReturnsPriorIdentity": zero_lora_model_only is prior,
            "modelOnlyZeroLoadDelta": model_only_load_delta,
        },
        "modelAsLora": {
            "zeroStillLoaded": first_model_as_load_delta == 1,
            "sameCheckpointLoadedOnce": same_path_load_delta == 1,
            "changedPathReloaded": changed_path_load_delta == 1,
            "zeroStrengths": [zero_model_hook._strength_model, zero_model_hook._strength_clip],
            "secondStrengths": [second_model_hook._strength_model, second_model_hook._strength_clip],
            "modelKeys": sorted(zero_model_hook.weights),
            "samplingKeysRemoved": not any(key.startswith("model_sampling") for key in zero_model_hook.weights),
            "clipKeys": sorted(zero_model_hook.weights_clip),
            "patchType": zero_model_hook.weights["diffusion.weight"][0],
            "needWeightInit": zero_model_hook.need_weight_init,
            "targetTensorSharedAcrossCalls": (
                zero_model_hook.weights["diffusion.weight"][1][0]
                is second_model_hook.weights["diffusion.weight"][1][0]
            ),
            "loaderRequestedVaeAndClip": sd.load_calls[0][1]["output_vae"] and sd.load_calls[0][1]["output_clip"],
            "modelOnlyZeroStillLoads": checkpoint_model_only_delta == 1,
            "modelOnlyClipStrength": checkpoint_model_only_hook._strength_clip,
            "modelOnlyStillStoresClipPatches": checkpoint_model_only_hook.weights_clip is not None,
            "clipMayBeAbsent": no_clip_hook.weights_clip is None,
            "vaeNotCached": len(no_clip_node.loaded_weights) == 3,
        },
        "modelAsLoraFormula": {
            "strength0": model_as_value(0.0),
            "strengthHalf": model_as_value(0.5),
            "strength1": model_as_value(1.0),
            "strengthNegative": model_as_value(-1.0),
            "keepsExistingPatch": model_as_value(
                1.0,
                current=base + torch.tensor([10.0, 10.0]),
            ),
            "broadcastShape": model_as_value(
                1.0,
                target_value=torch.tensor([5.0]),
            ),
            "incompatibleShapeError": shape_error,
        },
        "rawLoraPatchSemantics": {
            "diffStrength0": calculate_simple(diff_patch, 0.0),
            "diffStrengthNegative": calculate_simple(diff_patch, -1.0),
            "setStrength0": calculate_simple(set_patch, 0.0),
            "setThenDiff": set_then_diff,
            "diffThenSet": diff_then_set,
        },
        "exactRegistration": {
            "loadLoraLogMissingFlags": recorded_lora_api.load_arguments,
            "missingTargetKeyFiltered": "target.only" not in patcher.hook_patches[target_hook.hook_ref],
            "registeredKeys": sorted(patcher.hook_patches[target_hook.hook_ref]),
            "priorThenNew": [
                ordered_group.hooks[0].hook_ref is adapter_hook.hook_ref,
                ordered_group.hooks[1].hook_ref is target_hook.hook_ref,
            ],
            "cloneSharesWeightDictionary": ordered_group.hooks[0].weights is adapter_hook.weights,
            "duplicateHookRefRemoved": len(deduplicated_group.hooks) == 1,
            "combinedStrengths": [patch[0] for patch in combined_patches["base.weight"]],
            "effectiveTargetStrength": target_hook.strength_model,
            "zeroSetStillApplies": zero_set_result,
        },
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
