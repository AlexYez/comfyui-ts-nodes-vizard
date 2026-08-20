from __future__ import annotations

import ast
import copy
import json
import logging
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


def _compile_exact_definitions(
    path: Path,
    *,
    namespace: dict[str, Any],
    functions: set[str] = frozenset(),
    classes: set[str] = frozenset(),
) -> dict[str, Any]:
    """Compile only named top-level definitions from a pinned source file."""

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

    future_annotations = ast.ImportFrom(
        module="__future__",
        names=[ast.alias(name="annotations")],
        level=0,
    )
    module = ast.Module(body=[future_annotations, *selected], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return {name: namespace[name] for name in functions | classes}


class FakeModel:
    def __init__(self, label: str) -> None:
        self.label = label


class FakePatcher:
    _next_id = 0

    def __init__(
        self,
        *,
        label: str,
        load_device: torch.device,
        offload_device: torch.device,
        model: FakeModel | None = None,
        dynamic: bool = False,
        deepclone_supported: bool = True,
        cpu_delegate_supported: bool = True,
        clone_base_uuid: str | None = None,
        event_log: list[dict[str, Any]] | None = None,
    ) -> None:
        FakePatcher._next_id += 1
        self.label = label
        self.model = model or FakeModel(f"{label}-model-{FakePatcher._next_id}")
        self.load_device = load_device
        self.offload_device = offload_device
        self.dynamic = dynamic
        self.deepclone_supported = deepclone_supported
        self.cpu_delegate_supported = cpu_delegate_supported
        self.clone_base_uuid = clone_base_uuid or f"family-{FakePatcher._next_id}"
        self.is_multigpu_base_clone = False
        self.additional_models: dict[str, list[FakePatcher]] = {}
        self.model_options: dict[str, Any] = {}
        self.compute_dtype: Any = None
        self.registered_devices: list[torch.device] = []
        self.match_calls = 0
        self.event_log = event_log if event_log is not None else []

    def clone(self, disable_dynamic: bool = False) -> "FakePatcher":
        if disable_dynamic and self.dynamic and not self.cpu_delegate_supported:
            raise RuntimeError("cached_patcher_init is not initialized")
        model = self.model
        if disable_dynamic and self.dynamic:
            model = FakeModel(f"{self.label}-plain-delegate")
        result = FakePatcher(
            label=f"{self.label}-clone",
            load_device=self.load_device,
            offload_device=self.offload_device,
            model=model,
            dynamic=False if disable_dynamic else self.dynamic,
            deepclone_supported=self.deepclone_supported,
            cpu_delegate_supported=self.cpu_delegate_supported,
            clone_base_uuid=self.clone_base_uuid,
            event_log=self.event_log,
        )
        result.is_multigpu_base_clone = self.is_multigpu_base_clone
        result.additional_models = {
            key: [patcher.clone() for patcher in values]
            for key, values in self.additional_models.items()
        }
        result.model_options = copy.deepcopy(self.model_options)
        result.compute_dtype = self.compute_dtype
        return result

    def is_dynamic(self) -> bool:
        return self.dynamic

    def deepclone_multigpu(self, new_load_device: torch.device | None = None) -> "FakePatcher":
        if not self.deepclone_supported:
            raise RuntimeError("cached_patcher_init is not initialized")
        target = new_load_device if new_load_device is not None else self.load_device
        result = FakePatcher(
            label=f"{self.label}-deep",
            load_device=target,
            offload_device=self.offload_device,
            model=FakeModel(f"{self.label}-fresh-{target}"),
            dynamic=self.dynamic,
            deepclone_supported=self.deepclone_supported,
            cpu_delegate_supported=self.cpu_delegate_supported,
            clone_base_uuid=self.clone_base_uuid,
            event_log=self.event_log,
        )
        # The pinned ModelPatcher.deepclone_multigpu removes inherited
        # "multigpu" additional models from the fresh deepclone.
        result.model_options = copy.deepcopy(self.model_options)
        result.compute_dtype = self.compute_dtype
        self.event_log.append({"event": "deepclone", "device": str(target)})
        return result

    def get_additional_models_with_key(self, key: str) -> list["FakePatcher"]:
        return list(self.additional_models.get(key, []))

    def set_additional_models(self, key: str, values: list["FakePatcher"]) -> None:
        self.additional_models[key] = list(values)

    def match_multigpu_clones(self) -> None:
        self.match_calls += 1

    def register_load_device(self, device: torch.device) -> None:
        self.registered_devices.append(device)

    def model_dtype(self) -> str:
        return "float16"

    def set_model_compute_dtype(self, dtype: Any) -> None:
        self.compute_dtype = dtype


class FakeCLIP:
    def __init__(self, patcher: FakePatcher) -> None:
        self.patcher = patcher
        self.cond_stage_model = patcher.model

    def clone(self) -> "FakeCLIP":
        result = FakeCLIP.__new__(FakeCLIP)
        result.patcher = self.patcher.clone()
        result.cond_stage_model = self.cond_stage_model
        return result


class FakeVAE:
    def __init__(self, patcher: FakePatcher) -> None:
        self.patcher = patcher
        self.first_stage_model = patcher.model
        self.device = patcher.load_device


def _device_list(values: list[torch.device]) -> list[str]:
    return [str(value) for value in values]


def run_probe(source_root: Path) -> dict[str, Any]:
    source_root = source_root.resolve()
    nodes_path = source_root / "comfy_extras" / "nodes_multigpu.py"
    multigpu_path = source_root / "comfy" / "multigpu.py"
    management_path = source_root / "comfy" / "model_management.py"
    for path in (nodes_path, multigpu_path, management_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    cuda0 = torch.device("cuda", 0)
    cuda1 = torch.device("cuda", 1)
    cuda2 = torch.device("cuda", 2)
    cpu = torch.device("cpu")
    available_devices: list[torch.device] = [cuda0]

    def get_all_torch_devices(exclude_current: bool = True) -> list[torch.device]:
        del exclude_current
        return list(available_devices)

    management_namespace: dict[str, Any] = {
        "torch": torch,
        "get_all_torch_devices": get_all_torch_devices,
    }
    device_definitions = _compile_exact_definitions(
        management_path,
        namespace=management_namespace,
        functions={
            "get_gpu_device_options",
            "get_gpu_device_options_no_cpu",
            "resolve_gpu_device_option",
        },
    )
    get_options = device_definitions["get_gpu_device_options"]
    get_options_no_cpu = device_definitions["get_gpu_device_options_no_cpu"]
    resolve_option = device_definitions["resolve_gpu_device_option"]

    one_device_options = list(get_options())
    one_device_vae_options = list(get_options_no_cpu())
    available_devices[:] = [cuda0, cuda1, cuda2]
    three_device_options = list(get_options())
    three_device_vae_options = list(get_options_no_cpu())
    resolved_options = {
        name: None if value is None else str(value)
        for name, value in {
            "default": resolve_option("default"),
            "cpu": resolve_option("cpu"),
            "gpu:1": resolve_option("gpu:1"),
            "gpu:9": resolve_option("gpu:9"),
            "gpu:bad": resolve_option("gpu:bad"),
        }.items()
    }

    class ModelManagementStub:
        loaded: list[FakePatcher] = []

        @staticmethod
        def get_all_torch_devices(exclude_current: bool = True) -> list[torch.device]:
            del exclude_current
            return list(available_devices)

        @staticmethod
        def loaded_models() -> list[FakePatcher]:
            return list(ModelManagementStub.loaded)

        @staticmethod
        def resolve_gpu_device_option(option: str) -> torch.device | None:
            return resolve_option(option)

        @staticmethod
        def unet_manual_cast(weight_dtype: Any, device: torch.device) -> Any:
            del weight_dtype
            return torch.float32 if device in (cpu, cuda1) else None

        @staticmethod
        def vae_offload_device() -> torch.device:
            return cpu

    comfy_stub = SimpleNamespace(model_management=ModelManagementStub)
    multigpu_namespace: dict[str, Any] = {
        "comfy": comfy_stub,
        "logging": logging,
        "torch": torch,
        "ModelPatcher": FakePatcher,
    }
    multigpu_definitions = _compile_exact_definitions(
        multigpu_path,
        namespace=multigpu_namespace,
        functions={"create_multigpu_deepclones"},
        classes={"GPUOptions", "GPUOptionsGroup"},
    )
    create_multigpu_deepclones = multigpu_definitions["create_multigpu_deepclones"]
    comfy_stub.multigpu = SimpleNamespace(
        create_multigpu_deepclones=create_multigpu_deepclones
    )

    node_namespace: dict[str, Any] = {
        "comfy": comfy_stub,
        "copy": copy,
        "io": IO,
        "logging": logging,
        "torch": torch,
        "ModelPatcher": FakePatcher,
        "CLIP": FakeCLIP,
        "VAE": FakeVAE,
        "cleandoc": lambda value: value,
    }
    node_definitions = _compile_exact_definitions(
        nodes_path,
        namespace=node_namespace,
        functions={
            "_force_supported_compute_dtype",
            "_remember_base_devices",
            "_propagate_base_devices",
            "_retarget_patcher",
            "_apply_patcher_device",
            "_prune_multigpu_collision",
        },
        classes={
            "MultiGPUCFGSplitNode",
            "SelectModelDeviceNode",
            "SelectCLIPDeviceNode",
            "SelectVAEDeviceNode",
        },
    )
    work_units_node = node_definitions["MultiGPUCFGSplitNode"]
    select_model_node = node_definitions["SelectModelDeviceNode"]
    select_clip_node = node_definitions["SelectCLIPDeviceNode"]
    select_vae_node = node_definitions["SelectVAEDeviceNode"]

    # Work-unit preparation: max_gpus counts the primary device and fresh
    # deepclones exclude the primary patcher's actual load device.
    available_devices[:] = [cuda0, cuda1, cuda2]
    primary = FakePatcher(label="primary", load_device=cuda1, offload_device=cpu)
    prepared = work_units_node.execute(primary, 2).values[0]
    prepared_extras = prepared.get_additional_models_with_key("multigpu")
    assert prepared is not primary
    assert prepared.load_device == cuda1
    assert [item.load_device for item in prepared_extras] == [cuda0]
    assert all(item.is_multigpu_base_clone for item in prepared_extras)

    inherited = FakePatcher(label="inherited", load_device=cuda0, offload_device=cpu)
    inherited.set_additional_models(
        "multigpu",
        [
            FakePatcher(label="old-1", load_device=cuda1, offload_device=cpu),
            FakePatcher(label="old-2", load_device=cuda2, offload_device=cpu),
        ],
    )
    pruned_two = work_units_node.execute(inherited, 2).values[0]
    pruned_one = work_units_node.execute(inherited, 1).values[0]
    assert _device_list(
        [item.load_device for item in pruned_two.get_additional_models_with_key("multigpu")]
    ) == ["cuda:1"]
    assert pruned_one.get_additional_models_with_key("multigpu") == []

    reusable_input = FakePatcher(
        label="reuse-input",
        load_device=cuda0,
        offload_device=cpu,
        clone_base_uuid="reuse-family",
    )
    wrong_candidate = FakePatcher(
        label="wrong-loaded",
        load_device=cuda1,
        offload_device=cpu,
        clone_base_uuid="reuse-family",
    )
    right_candidate = FakePatcher(
        label="right-loaded",
        load_device=cuda1,
        offload_device=cpu,
        clone_base_uuid="reuse-family",
    )
    right_candidate.is_multigpu_base_clone = True
    ModelManagementStub.loaded = [wrong_candidate, right_candidate]
    available_devices[:] = [cuda0, cuda1]
    reused = work_units_node.execute(reusable_input, 2).values[0]
    reused_extra = reused.get_additional_models_with_key("multigpu")[0]
    assert reused_extra.model is right_candidate.model
    assert reused_extra.model is not wrong_candidate.model

    unsupported_work_units = FakePatcher(
        label="unsupported-work-units",
        load_device=cuda0,
        offload_device=cpu,
        deepclone_supported=False,
    )
    ModelManagementStub.loaded = []
    work_units_missing_factory_raised = False
    try:
        work_units_node.execute(unsupported_work_units, 2)
    except RuntimeError:
        work_units_missing_factory_raised = True
    assert work_units_missing_factory_raised

    # MODEL selection: explicit GPU creates a fresh model, default returns to
    # the loader pair, CPU pins both routes, and unsupported/unknown targets
    # return a clone with the old routing.
    available_devices[:] = [cuda0, cuda1]
    input_model = FakePatcher(label="model", load_device=cuda0, offload_device=cpu)
    selected_model = select_model_node.execute(input_model, "gpu:1").values[0]
    assert selected_model.load_device == cuda1
    assert selected_model.offload_device == cpu
    assert selected_model.model is not input_model.model
    assert selected_model.compute_dtype is torch.float32
    assert input_model.model._select_base_load_device == cuda0
    assert input_model.model._select_base_offload_device == cpu
    restored_model = select_model_node.execute(selected_model, "default").values[0]
    assert restored_model.load_device == cuda0
    assert restored_model.offload_device == cpu

    cpu_input = FakePatcher(label="model-cpu", load_device=cuda0, offload_device=cuda1)
    cpu_model = select_model_node.execute(cpu_input, "cpu").values[0]
    assert cpu_model.load_device == cpu_model.offload_device == cpu
    assert cpu_model.model is cpu_input.model
    assert cpu_model.compute_dtype is torch.float32
    assert cpu_input.load_device == cuda0 and cpu_input.offload_device == cuda1

    unavailable_input = FakePatcher(
        label="model-unavailable", load_device=cuda0, offload_device=cpu
    )
    unavailable_model = select_model_node.execute(unavailable_input, "gpu:9").values[0]
    assert unavailable_model is not unavailable_input
    assert unavailable_model.model is unavailable_input.model
    assert unavailable_model.load_device == cuda0
    assert not hasattr(unavailable_input.model, "_select_base_load_device")

    missing_model_factory_input = FakePatcher(
        label="model-no-factory",
        load_device=cuda0,
        offload_device=cpu,
        deepclone_supported=False,
    )
    missing_model_factory = select_model_node.execute(
        missing_model_factory_input, "gpu:1"
    ).values[0]
    assert missing_model_factory.load_device == cuda0
    assert missing_model_factory.model is missing_model_factory_input.model

    colliding = FakePatcher(label="model-collision", load_device=cuda1, offload_device=cpu)
    colliding.set_additional_models(
        "multigpu",
        [FakePatcher(label="collision-clone", load_device=cuda1, offload_device=cpu)],
    )
    collision_result = select_model_node.execute(colliding, "gpu:1").values[0]
    assert collision_result.get_additional_models_with_key("multigpu") == []
    assert collision_result.match_calls == 1

    dynamic_no_factory = FakePatcher(
        label="dynamic-no-factory",
        load_device=cuda0,
        offload_device=cpu,
        dynamic=True,
        cpu_delegate_supported=False,
    )
    dynamic_cpu_fallback = select_model_node.execute(dynamic_no_factory, "cpu").values[0]
    assert dynamic_cpu_fallback.load_device == cuda0
    assert dynamic_cpu_fallback.offload_device == cpu

    # CLIP follows the exact node's wrapper clone and patcher routing. The
    # source currently does not resynchronize cond_stage_model after a fresh
    # deepclone; record that source-level boundary explicitly.
    clip_input = FakeCLIP(
        FakePatcher(label="clip", load_device=cuda0, offload_device=cpu)
    )
    selected_clip = select_clip_node.execute(clip_input, "gpu:1").values[0]
    assert selected_clip is not clip_input
    assert selected_clip.patcher.load_device == cuda1
    assert selected_clip.patcher.offload_device == cpu
    assert selected_clip.patcher.model is not clip_input.patcher.model
    assert selected_clip.cond_stage_model is clip_input.cond_stage_model
    assert selected_clip.cond_stage_model is not selected_clip.patcher.model
    restored_clip = select_clip_node.execute(selected_clip, "default").values[0]
    assert restored_clip.patcher.load_device == cuda0
    assert restored_clip.patcher.offload_device == cpu

    clip_cpu_input = FakeCLIP(
        FakePatcher(label="clip-cpu", load_device=cuda0, offload_device=cuda1)
    )
    clip_cpu = select_clip_node.execute(clip_cpu_input, "cpu").values[0]
    assert clip_cpu.patcher.load_device == clip_cpu.patcher.offload_device == cpu

    clip_unavailable_input = FakeCLIP(
        FakePatcher(label="clip-unavailable", load_device=cuda0, offload_device=cpu)
    )
    clip_unavailable = select_clip_node.execute(
        clip_unavailable_input, "gpu:9"
    ).values[0]
    assert clip_unavailable is not clip_unavailable_input
    assert clip_unavailable.patcher.load_device == cuda0
    assert clip_unavailable.patcher.model is clip_unavailable_input.patcher.model

    clip_missing_input = FakeCLIP(
        FakePatcher(
            label="clip-no-factory",
            load_device=cuda0,
            offload_device=cpu,
            deepclone_supported=False,
        )
    )
    clip_missing = select_clip_node.execute(clip_missing_input, "gpu:1").values[0]
    assert clip_missing.patcher.load_device == cuda0
    assert clip_missing.patcher.model is clip_missing_input.patcher.model

    # VAE uses a shallow wrapper copy, rejects CPU before retargeting, applies
    # the standard VAE offload device, and explicitly synchronizes the model
    # pointer after a successful deepclone/default restoration.
    vae_input = FakeVAE(
        FakePatcher(label="vae", load_device=cuda0, offload_device=cuda1)
    )
    selected_vae = select_vae_node.execute(vae_input, "gpu:1").values[0]
    assert selected_vae is not vae_input
    assert vae_input.device == cuda0 and vae_input.patcher.load_device == cuda0
    assert selected_vae.device == cuda1
    assert selected_vae.patcher.load_device == cuda1
    assert selected_vae.patcher.offload_device == cpu
    assert selected_vae.first_stage_model is selected_vae.patcher.model
    assert selected_vae._select_base_device == cuda0
    restored_vae = select_vae_node.execute(selected_vae, "default").values[0]
    assert restored_vae.device == cuda0
    assert restored_vae.patcher.load_device == cuda0
    assert restored_vae.patcher.offload_device == cpu
    assert restored_vae.first_stage_model is restored_vae.patcher.model

    vae_cpu_input = FakeVAE(
        FakePatcher(label="vae-cpu-reject", load_device=cuda0, offload_device=cuda1)
    )
    vae_cpu = select_vae_node.execute(vae_cpu_input, "cpu").values[0]
    assert vae_cpu is not vae_cpu_input
    assert vae_cpu.device == cuda0
    assert vae_cpu.patcher.load_device == cuda0
    assert vae_cpu.patcher.offload_device == cuda1
    assert not hasattr(vae_cpu, "_select_base_device")

    vae_unavailable_input = FakeVAE(
        FakePatcher(label="vae-unavailable", load_device=cuda0, offload_device=cuda1)
    )
    vae_unavailable = select_vae_node.execute(
        vae_unavailable_input, "gpu:9"
    ).values[0]
    assert vae_unavailable is not vae_unavailable_input
    assert vae_unavailable.device == cuda0
    assert vae_unavailable.patcher.load_device == cuda0
    assert vae_unavailable.patcher.offload_device == cuda1

    vae_missing_input = FakeVAE(
        FakePatcher(
            label="vae-no-factory",
            load_device=cuda0,
            offload_device=cuda1,
            deepclone_supported=False,
        )
    )
    vae_missing = select_vae_node.execute(vae_missing_input, "gpu:1").values[0]
    assert vae_missing.device == cuda0
    assert vae_missing.patcher.load_device == cuda0

    return {
        "workflowExampleExecuted": False,
        "hardware": "no hardware query or tensor/model allocation; torch.device labels only",
        "deviceOptions": {
            "oneDevice": one_device_options,
            "oneDeviceVAE": one_device_vae_options,
            "threeDevices": three_device_options,
            "threeDevicesVAE": three_device_vae_options,
            "resolved": resolved_options,
        },
        "workUnits": {
            "inputUnchanged": primary.get_additional_models_with_key("multigpu") == [],
            "primary": str(prepared.load_device),
            "maxTwoExtras": _device_list(
                [item.load_device for item in prepared_extras]
            ),
            "prunedToTwoExtras": _device_list(
                [
                    item.load_device
                    for item in pruned_two.get_additional_models_with_key("multigpu")
                ]
            ),
            "prunedToOneExtras": _device_list(
                [
                    item.load_device
                    for item in pruned_one.get_additional_models_with_key("multigpu")
                ]
            ),
            "reusedEligibleLoadedModel": reused_extra.model is right_candidate.model,
            "rejectedUnflaggedLoadedModel": reused_extra.model
            is not wrong_candidate.model,
            "missingFactoryRaised": work_units_missing_factory_raised,
        },
        "selectModel": {
            "gpu": {
                "load": str(selected_model.load_device),
                "offload": str(selected_model.offload_device),
                "freshModel": selected_model.model is not input_model.model,
                "computeDtype": str(selected_model.compute_dtype),
            },
            "default": {
                "load": str(restored_model.load_device),
                "offload": str(restored_model.offload_device),
            },
            "cpu": {
                "load": str(cpu_model.load_device),
                "offload": str(cpu_model.offload_device),
                "inputRoutingUnchanged": cpu_input.load_device == cuda0
                and cpu_input.offload_device == cuda1,
            },
            "unavailable": {
                "clonedWrapper": unavailable_model is not unavailable_input,
                "sameModel": unavailable_model.model is unavailable_input.model,
                "load": str(unavailable_model.load_device),
            },
            "missingFactoryLoad": str(missing_model_factory.load_device),
            "collisionExtras": _device_list(
                [
                    item.load_device
                    for item in collision_result.get_additional_models_with_key("multigpu")
                ]
            ),
            "dynamicCpuMissingFactoryLoad": str(dynamic_cpu_fallback.load_device),
        },
        "selectCLIP": {
            "gpuLoad": str(selected_clip.patcher.load_device),
            "defaultLoad": str(restored_clip.patcher.load_device),
            "cpuLoad": str(clip_cpu.patcher.load_device),
            "unavailableLoad": str(clip_unavailable.patcher.load_device),
            "missingFactoryLoad": str(clip_missing.patcher.load_device),
            "freshPatcherModel": selected_clip.patcher.model is not clip_input.patcher.model,
            "wrapperPointsToPatcherModel": selected_clip.cond_stage_model
            is selected_clip.patcher.model,
            "wrapperStillPointsToInputModel": selected_clip.cond_stage_model
            is clip_input.cond_stage_model,
        },
        "selectVAE": {
            "gpu": {
                "load": str(selected_vae.patcher.load_device),
                "offload": str(selected_vae.patcher.offload_device),
                "wrapperDevice": str(selected_vae.device),
                "modelSynchronized": selected_vae.first_stage_model
                is selected_vae.patcher.model,
            },
            "default": {
                "load": str(restored_vae.patcher.load_device),
                "offload": str(restored_vae.patcher.offload_device),
                "wrapperDevice": str(restored_vae.device),
                "modelSynchronized": restored_vae.first_stage_model
                is restored_vae.patcher.model,
            },
            "cpuRejected": {
                "load": str(vae_cpu.patcher.load_device),
                "offload": str(vae_cpu.patcher.offload_device),
                "wrapperDevice": str(vae_cpu.device),
            },
            "unavailableLoad": str(vae_unavailable.patcher.load_device),
            "missingFactoryLoad": str(vae_missing.patcher.load_device),
            "inputUnchanged": vae_input.device == cuda0
            and vae_input.patcher.load_device == cuda0,
        },
    }


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".comfyui-source-0.32.0")
    print(json.dumps(run_probe(root), ensure_ascii=False, sort_keys=True))
