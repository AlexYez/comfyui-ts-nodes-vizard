from __future__ import annotations

import ast
import collections
import json
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0"


def load_functions(path: Path, names: set[str], namespace: dict) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    selected = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    missing = names - {node.name for node in selected}
    if missing:
        raise AssertionError(f"missing exact source functions in {path}: {sorted(missing)}")
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.Module(body=[future, *selected], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


class FakeHookGroup:
    def __init__(self, labels: list[str], truthy: bool = True):
        self.labels = list(labels)
        self.truthy = truthy
        self.clone_calls = 0

    def __bool__(self) -> bool:
        return self.truthy

    def clone_and_combine(self, other: "FakeHookGroup") -> "FakeHookGroup":
        self.clone_calls += 1
        return FakeHookGroup([*self.labels, *other.labels])


class FakePatcher:
    def prepare_hook_patches_current_keyframe(self, timestep, hooks, model_options) -> None:
        raise AssertionError("the sampler probe does not attach hooks to default conditions")


class FakeModel:
    def __init__(self) -> None:
        self.current_patcher = FakePatcher()


class FakeModelSampling:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def percent_to_sigma(self, value: float) -> float:
        self.calls.append(value)
        return 1.0 - value


class FakeSamplingModel:
    def __init__(self) -> None:
        self.model_sampling = FakeModelSampling()


def entry(value: float, **metadata):
    return [torch.tensor([[value]], dtype=torch.float32), dict(metadata)]


def sampler_entry(label: str, **metadata) -> dict:
    return {"model_conds": {}, "uuid": label, **metadata}


def main() -> None:
    helper_ns: dict = {}
    load_functions(SOURCE / "node_helpers.py", {"conditioning_set_values"}, helper_ns)

    function_names = {
        "_combine_hooks_from_values",
        "conditioning_set_values_with_hooks",
        "set_hooks_for_conditioning",
        "set_timesteps_for_conditioning",
        "set_mask_for_conditioning",
        "combine_conditioning",
        "set_conds_props",
        "set_conds_props_and_combine",
        "set_default_conds_and_combine",
    }
    hooks_ns = {
        "torch": torch,
        "HookGroup": FakeHookGroup,
        "conditioning_set_values": helper_ns["conditioning_set_values"],
    }
    load_functions(SOURCE / "comfy" / "hooks.py", function_names, hooks_ns)

    sampler_ns = {"collections": collections, "torch": torch}
    load_functions(
        SOURCE / "comfy" / "samplers.py",
        {
            "add_area_dims",
            "calculate_start_end_timesteps",
            "finalize_default_conds",
            "get_area_and_mult",
            "get_mask_aabb",
            "resolve_areas_and_cond_masks_multidim",
        },
        sampler_ns,
    )

    set_props = hooks_ns["set_conds_props"]
    set_props_and_combine = hooks_ns["set_conds_props_and_combine"]
    set_default_and_combine = hooks_ns["set_default_conds_and_combine"]
    calculate_timesteps = sampler_ns["calculate_start_end_timesteps"]
    finalize_default_conds = sampler_ns["finalize_default_conds"]
    get_area_and_mult = sampler_ns["get_area_and_mult"]
    resolve_masks = sampler_ns["resolve_areas_and_cond_masks_multidim"]

    pos_a = [entry(1.0, source="pos-a")]
    neg_a = [entry(-1.0, source="neg-a")]
    pos_b = [entry(2.0, source="pos-b"), entry(3.0, source="pos-b-2")]
    neg_b = [entry(-2.0, source="neg-b")]
    combined_pos, combined_neg = set_props_and_combine([pos_a, neg_a], [pos_b, neg_b])

    no_op_pos = [entry(4.0, source="no-op-pos")]
    no_op_neg = [entry(-4.0, source="no-op-neg")]
    no_op_out = set_props(
        [no_op_pos, no_op_neg],
        strength=9.75,
        set_cond_area="mask bounds",
        mask=None,
        hooks=None,
        timesteps_range=None,
    )

    old_hooks = FakeHookGroup(["old"])
    new_hooks = FakeHookGroup(["new"])
    pos_new = [entry(5.0, source="pos-new", hooks=old_hooks)]
    neg_new = [entry(-5.0, source="neg-new", hooks=old_hooks)]
    mask = torch.tensor([[0.0, 1.0], [1.0, 0.0]], dtype=torch.float32)
    props_pos, props_neg = set_props(
        [pos_new, neg_new],
        strength=0.6,
        set_cond_area="mask bounds",
        mask=mask,
        hooks=new_hooks,
        timesteps_range=(0.2, 0.8),
    )

    base_pos = [entry(10.0, source="base-pos")]
    base_neg = [entry(-10.0, source="base-neg")]
    added_pos = [entry(11.0, source="added-pos")]
    added_neg = [entry(-11.0, source="added-neg")]
    merged_pos, merged_neg = set_props_and_combine(
        [base_pos, base_neg],
        [added_pos, added_neg],
        strength=0.25,
        set_cond_area="default",
        mask=mask,
        hooks=None,
        timesteps_range=(0.1, 0.9),
    )
    merge_old_hooks = FakeHookGroup(["merge-old"])
    merge_new_hooks = FakeHookGroup(["merge-new"])
    hook_added_pos = [entry(12.0, source="hook-added-pos", hooks=merge_old_hooks)]
    hook_added_neg = [entry(-12.0, source="hook-added-neg", hooks=merge_old_hooks)]
    hook_merged_pos, hook_merged_neg = set_props_and_combine(
        [base_pos, base_neg],
        [hook_added_pos, hook_added_neg],
        strength=1.0,
        set_cond_area="default",
        hooks=merge_new_hooks,
    )

    inherited = FakeHookGroup(["inherited"])
    default_hook = FakeHookGroup(["default"])
    default_pos = [entry(20.0, source="default-pos", hooks=inherited, default=False)]
    default_neg = [entry(-20.0, source="default-neg", hooks=inherited)]
    fallback_pos, fallback_neg = set_default_and_combine(
        [base_pos, base_neg],
        [default_pos, default_neg],
        hooks=default_hook,
    )

    empty_hooks = FakeHookGroup([], truthy=False)
    empty_hook_cond = [entry(30.0, source="empty-hook")]
    (empty_hook_out,) = set_props(
        [empty_hook_cond],
        strength=1.0,
        set_cond_area="default",
        hooks=empty_hooks,
    )

    old_mask = torch.ones((2, 2), dtype=torch.float32)
    overwrite_source = [
        entry(
            31.0,
            source="overwrite",
            mask=old_mask,
            mask_strength=9.0,
            set_area_to_bounds=False,
            start_percent=0.0,
            end_percent=1.0,
            strength=7.0,
        )
    ]
    (overwrite_out,) = set_props(
        [overwrite_source],
        strength=0.4,
        set_cond_area="mask bounds",
        mask=mask,
        timesteps_range=(0.25, 0.75),
    )
    (reversed_timesteps,) = set_props(
        [[entry(32.0, source="reversed")]],
        strength=1.0,
        set_cond_area="default",
        timesteps_range=(0.9, 0.1),
    )

    sampling_model = FakeSamplingModel()
    converted = [sampler_entry("converted", start_percent=0.9, end_percent=0.1)]
    calculate_timesteps(sampling_model, converted)

    x_in = torch.zeros((1, 2, 8, 8), dtype=torch.float32)
    timestep = torch.tensor([0.5], dtype=torch.float32)
    reversed_range_inactive = all(
        get_area_and_mult(converted[0], x_in, torch.tensor([sigma], dtype=torch.float32)) is None
        for sigma in (0.0, 0.1, 0.5, 0.9, 1.0)
    )
    sampler_mask = torch.zeros((1, 8, 8), dtype=torch.float32)
    sampler_mask[:, 2:6, 1:7] = 1.0
    masked_normal = get_area_and_mult(
        sampler_entry("masked-normal", mask=sampler_mask, mask_strength=0.5),
        x_in,
        timestep,
    )
    expected_mask_mult = sampler_mask.unsqueeze(1).repeat(1, 2, 1, 1) * 0.5
    weighted_normal = get_area_and_mult(
        sampler_entry("weighted-normal", mask=sampler_mask, mask_strength=0.5, strength=0.25),
        x_in,
        timestep,
    )
    expected_weighted_mult = expected_mask_mult * 0.25

    own_default_mask = torch.zeros((1, 8, 8), dtype=torch.float32)
    default_cond = sampler_entry(
        "default",
        default=True,
        mask=own_default_mask,
        mask_strength=0.0,
    )
    masked_runs = {None: [(masked_normal, 0)]}
    finalize_default_conds(FakeModel(), masked_runs, [[default_cond]], x_in, timestep, {})
    masked_default = masked_runs[None][-1][0]
    expected_residual = torch.ones_like(x_in) - expected_mask_mult

    full_normal = get_area_and_mult(sampler_entry("full-normal"), x_in, timestep)
    full_runs = {None: [(full_normal, 0)]}
    finalize_default_conds(
        FakeModel(),
        full_runs,
        [[sampler_entry("full-default", default=True)]],
        x_in,
        timestep,
        {},
    )

    overlap_normal = get_area_and_mult(
        sampler_entry("overlap-normal", mask=sampler_mask, mask_strength=0.75),
        x_in,
        timestep,
    )
    overlap_runs = {None: [(overlap_normal, 0), (overlap_normal, 0)]}
    finalize_default_conds(
        FakeModel(),
        overlap_runs,
        [[sampler_entry("overlap-default", default=True)]],
        x_in,
        timestep,
        {},
    )
    overlap_default = overlap_runs[None][-1][0]

    area_default_cond = sampler_entry("area-default", default=True, area=(4, 4, 2, 2))
    area_runs: dict = {}
    finalize_default_conds(FakeModel(), area_runs, [[area_default_cond]], x_in, timestep, {})
    area_default = area_runs[None][0][0]

    bounds_mask = torch.zeros((2, 16, 16), dtype=torch.float32)
    bounds_mask[0, 3, 4] = 1.0
    bounds_mask[1, 12, 14] = -0.5
    bounded = [{"mask": bounds_mask, "set_area_to_bounds": True}]
    resolve_masks(bounded, (16, 16), "cpu")
    unbounded = [{"mask": bounds_mask, "set_area_to_bounds": False}]
    resolve_masks(unbounded, (16, 16), "cpu")
    empty_bounded = [{"mask": torch.zeros((1, 16, 16)), "set_area_to_bounds": True}]
    resolve_masks(empty_bounded, (16, 16), "cpu")

    result = {
        "combine": {
            "positiveOrder": [item[1]["source"] for item in combined_pos],
            "negativeOrder": [item[1]["source"] for item in combined_neg],
            "newOutputLists": combined_pos is not pos_a and combined_neg is not neg_a,
            "entriesPreserved": combined_pos[0] is pos_a[0] and combined_pos[1] is pos_b[0],
            "inputsUnchanged": len(pos_a) == 1 and len(pos_b) == 2,
        },
        "noOptionalProperties": {
            "positiveListIdentity": no_op_out[0] is no_op_pos,
            "negativeListIdentity": no_op_out[1] is no_op_neg,
            "strengthIgnoredWithoutMask": "mask_strength" not in no_op_out[0][0][1],
            "areaIgnoredWithoutMask": "set_area_to_bounds" not in no_op_out[0][0][1],
        },
        "properties": {
            "embeddingIdentity": props_pos[0][0] is pos_new[0][0] and props_neg[0][0] is neg_new[0][0],
            "metadataCopied": props_pos[0][1] is not pos_new[0][1] and props_neg[0][1] is not neg_new[0][1],
            "sourceMetadataUnchanged": list(pos_new[0][1]) == ["source", "hooks"],
            "maskShape": list(props_pos[0][1]["mask"].shape),
            "maskSharesStorage": props_pos[0][1]["mask"].data_ptr() == mask.data_ptr(),
            "negativeMaskSharesStorage": props_neg[0][1]["mask"].data_ptr() == mask.data_ptr(),
            "maskSharedAcrossPair": props_pos[0][1]["mask"] is props_neg[0][1]["mask"],
            "maskStrength": props_pos[0][1]["mask_strength"],
            "bounds": props_pos[0][1]["set_area_to_bounds"],
            "timesteps": [props_pos[0][1]["start_percent"], props_pos[0][1]["end_percent"]],
            "combinedHookLabels": props_pos[0][1]["hooks"].labels,
            "hookCacheShared": props_pos[0][1]["hooks"] is props_neg[0][1]["hooks"],
            "cloneCalls": old_hooks.clone_calls,
        },
        "propertiesAndCombine": {
            "positiveOrder": [item[1]["source"] for item in merged_pos],
            "negativeOrder": [item[1]["source"] for item in merged_neg],
            "baseEntryIdentity": merged_pos[0] is base_pos[0] and merged_neg[0] is base_neg[0],
            "newEmbeddingIdentity": merged_pos[1][0] is added_pos[0][0],
            "baseMetadataUnchanged": base_pos[0][1] == {"source": "base-pos"},
            "newMetadataUnchanged": added_pos[0][1] == {"source": "added-pos"},
            "newMaskStrength": merged_pos[1][1]["mask_strength"],
            "newBounds": merged_pos[1][1]["set_area_to_bounds"],
            "newTimesteps": [merged_pos[1][1]["start_percent"], merged_pos[1][1]["end_percent"]],
            "hookLabels": hook_merged_pos[1][1]["hooks"].labels,
            "hookCacheShared": hook_merged_pos[1][1]["hooks"] is hook_merged_neg[1][1]["hooks"],
            "hookCloneCalls": merge_old_hooks.clone_calls,
            "hookSourcesUnchanged": (
                hook_added_pos[0][1]["hooks"] is merge_old_hooks
                and hook_added_neg[0][1]["hooks"] is merge_old_hooks
            ),
        },
        "defaultCombine": {
            "positiveOrder": [item[1]["source"] for item in fallback_pos],
            "negativeOrder": [item[1]["source"] for item in fallback_neg],
            "baseEntryIdentity": fallback_pos[0] is base_pos[0] and fallback_neg[0] is base_neg[0],
            "defaultFlags": [fallback_pos[1][1]["default"], fallback_neg[1][1]["default"]],
            "existingFalseOverwritten": fallback_pos[1][1]["default"] is True,
            "hookLabels": fallback_pos[1][1]["hooks"].labels,
            "hookCacheShared": fallback_pos[1][1]["hooks"] is fallback_neg[1][1]["hooks"],
            "sourceDefaultsUnchanged": default_pos[0][1]["default"] is False and "default" not in default_neg[0][1],
        },
        "emptyHooks": {
            "attachedDespiteFalsy": empty_hook_out[0][1]["hooks"] is empty_hooks,
            "metadataCopied": empty_hook_out[0][1] is not empty_hook_cond[0][1],
        },
        "overwriteSemantics": {
            "sourceUnchanged": (
                overwrite_source[0][1]["mask"] is old_mask
                and overwrite_source[0][1]["mask_strength"] == 9.0
                and overwrite_source[0][1]["start_percent"] == 0.0
                and overwrite_source[0][1]["end_percent"] == 1.0
            ),
            "maskReplaced": overwrite_out[0][1]["mask"].data_ptr() == mask.data_ptr(),
            "maskStrength": overwrite_out[0][1]["mask_strength"],
            "bounds": overwrite_out[0][1]["set_area_to_bounds"],
            "timesteps": [overwrite_out[0][1]["start_percent"], overwrite_out[0][1]["end_percent"]],
            "generalStrengthPreserved": overwrite_out[0][1]["strength"],
            "reversedRangePreserved": [
                reversed_timesteps[0][1]["start_percent"],
                reversed_timesteps[0][1]["end_percent"],
            ],
        },
        "samplerMask": {
            "maskStrengthApplied": torch.equal(masked_normal.mult, expected_mask_mult),
            "generalStrengthMultiplied": torch.equal(weighted_normal.mult, expected_weighted_mult),
            "boundsUnionUsesAbsoluteMask": list(bounded[0]["area"]),
            "defaultLeavesAreaUnset": "area" not in unbounded[0],
            "emptyBoundsArea": list(empty_bounded[0]["area"]),
        },
        "timestepConversion": {
            "percentCalls": sampling_model.model_sampling.calls,
            "sigmaRange": [converted[0]["timestep_start"], converted[0]["timestep_end"]],
            "reversedRangeInactive": reversed_range_inactive,
        },
        "defaultResidual": {
            "maskedResidualExact": torch.equal(masked_default.mult, expected_residual),
            "ownMaskMultiplierReplaced": torch.count_nonzero(masked_default.mult).item() > 0,
            "fullCoverageSkipsDefault": len(full_runs[None]) == 1,
            "overlapClampedToZero": float(overlap_default.mult.min()) == 0.0,
            "overlapOutsideMaskRemainsOne": float(overlap_default.mult[0, 0, 0, 0]) == 1.0,
            "areaInputShape": list(area_default.input_x.shape),
            "areaMultiplierShape": list(area_default.mult.shape),
        },
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
