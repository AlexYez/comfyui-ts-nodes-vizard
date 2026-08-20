from __future__ import annotations

import __future__
import ast
import enum
import json
import math
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0"
HOOKS_SOURCE = SOURCE / "comfy" / "hooks.py"
NODES_SOURCE = SOURCE / "comfy_extras" / "nodes_hooks.py"


class EnumHookType(enum.Enum):
    Weight = "weight"
    Other = "other"


class EnumWeightTarget(enum.Enum):
    Clip = "clip"


class FakeKeyframe:
    def __init__(self, strength: float, start_percent: float) -> None:
        self.strength = strength
        self.start_percent = start_percent


class FakeHookKeyframeGroup:
    def __init__(self, keyframes: list[FakeKeyframe] | None = None) -> None:
        self.keyframes = list(keyframes or [])

    def clone(self) -> FakeHookKeyframeGroup:
        return FakeHookKeyframeGroup(
            [FakeKeyframe(item.strength, item.start_percent) for item in self.keyframes]
        )


class FakeHook:
    def __init__(
        self,
        ref: str,
        hook_type: EnumHookType = EnumHookType.Other,
        keyframes: list[FakeKeyframe] | None = None,
    ) -> None:
        self.ref = ref
        self.hook_ref = ref
        self.hook_type = hook_type
        self.hook_keyframe = FakeHookKeyframeGroup(keyframes)

    def clone(self) -> FakeHook:
        clone = self.__class__(self.ref, self.hook_type)
        # Mirror Hook.clone in the pinned source: clones initially share the keyframe group.
        clone.hook_keyframe = self.hook_keyframe
        return clone

    def reset(self) -> None:
        return None

    def __eq__(self, other: object) -> bool:
        return self.__class__ is other.__class__ and self.ref == other.ref

    def __hash__(self) -> int:
        return hash(self.ref)


def extract_classes(
    path: Path,
    names: set[str],
    namespace: dict[str, object],
) -> dict[str, type]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected = [
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in names
    ]
    found = {node.name for node in selected}
    if found != names:
        raise AssertionError(f"missing exact classes in {path}: {sorted(names - found)}")
    module = ast.Module(body=selected, type_ignores=[])
    code = compile(
        module,
        str(path),
        "exec",
        flags=__future__.annotations.compiler_flag,
        dont_inherit=True,
    )
    exec(code, namespace)
    return {name: namespace[name] for name in names}


def create_target_dict(target: EnumWeightTarget | None = None, **kwargs: object) -> dict[str, object]:
    result: dict[str, object] = {}
    if target is not None:
        result["target"] = target
    result.update(kwargs)
    return result


def load_definitions() -> tuple[type, dict[str, type]]:
    hooks_namespace: dict[str, object] = {
        "math": math,
        "itertools": __import__("itertools"),
        "Hook": FakeHook,
        "WeightHook": FakeHook,
        "HookKeyframe": FakeKeyframe,
        "HookKeyframeGroup": FakeHookKeyframeGroup,
        "EnumHookType": EnumHookType,
    }
    HookGroup = extract_classes(HOOKS_SOURCE, {"HookGroup"}, hooks_namespace)["HookGroup"]

    comfy_hooks = SimpleNamespace(
        HookGroup=HookGroup,
        EnumWeightTarget=EnumWeightTarget,
        create_target_dict=create_target_dict,
    )
    nodes_namespace: dict[str, object] = {
        "comfy": SimpleNamespace(hooks=comfy_hooks),
        "CLIP": object,
    }
    node_classes = extract_classes(
        NODES_SOURCE,
        {"SetClipHooks", "CombineHooks", "CombineHooksFour", "CombineHooksEight"},
        nodes_namespace,
    )
    return HookGroup, node_classes


def make_group(HookGroup: type, *hooks: FakeHook) -> object:
    group = HookGroup()
    for hook in hooks:
        group.add(hook)
    return group


class FakePatcher:
    def __init__(self) -> None:
        self.forced_hooks = None
        self.register_calls: list[tuple[object, dict[str, object]]] = []

    def register_all_hook_patches(self, hooks: object, target: dict[str, object]) -> None:
        self.register_calls.append((hooks, target))


class FakeClip:
    def __init__(self, apply_hooks_to_conds: object = None) -> None:
        self.patcher = FakePatcher()
        self.apply_hooks_to_conds = apply_hooks_to_conds
        self.use_clip_schedule = False
        self.clone_calls: list[bool] = []

    def clone(self, disable_dynamic: bool = False) -> FakeClip:
        self.clone_calls.append(disable_dynamic)
        clone = FakeClip(apply_hooks_to_conds=self.apply_hooks_to_conds)
        clone.use_clip_schedule = self.use_clip_schedule
        return clone


def refs(group: object | None) -> list[str] | None:
    if group is None:
        return None
    return [hook.ref for hook in group.hooks]


def schedule_ranges(group: object) -> list[list[object]]:
    result: list[list[object]] = []
    for time_range, values in group.get_hooks_for_clip_schedule():
        result.append(
            [
                [float(time_range[0]), float(time_range[1])],
                [[hook.ref, None if keyframe is None else keyframe.strength] for hook, keyframe in values],
            ]
        )
    return result


def run_combine_probe(HookGroup: type, classes: dict[str, type]) -> dict[str, object]:
    group_a = make_group(HookGroup, FakeHook("A"), FakeHook("shared"))
    group_b = make_group(HookGroup, FakeHook("shared"), FakeHook("B"))

    combine_two = classes["CombineHooks"]()
    none_result = combine_two.combine_hooks()[0]
    one_result = combine_two.combine_hooks(hooks_A=group_a)[0]
    two_result = combine_two.combine_hooks(hooks_A=group_a, hooks_B=group_b)[0]
    empty_group = make_group(HookGroup)
    empty_result = combine_two.combine_hooks(hooks_B=empty_group)[0]

    class OtherFakeHook(FakeHook):
        pass

    same_ref_distinct_classes = combine_two.combine_hooks(
        hooks_A=make_group(HookGroup, FakeHook("same-ref")),
        hooks_B=make_group(HookGroup, OtherFakeHook("same-ref")),
    )[0]

    groups = {
        letter: make_group(HookGroup, FakeHook(letter))
        for letter in "ABCDEFGH"
    }
    four_result = classes["CombineHooksFour"]().combine_hooks(
        hooks_A=groups["A"],
        hooks_C=groups["C"],
        hooks_D=groups["D"],
    )[0]
    eight_result = classes["CombineHooksEight"]().combine_hooks(
        hooks_A=groups["A"],
        hooks_D=groups["D"],
        hooks_H=groups["H"],
    )[0]

    return {
        "noneIsNone": none_result is None,
        "oneReturnsInputIdentity": one_result is group_a,
        "oneEmptyGroupReturnsInputIdentity": empty_result is empty_group,
        "twoCreatesNewGroup": two_result is not group_a and two_result is not group_b,
        "twoOrderAndDedup": refs(two_result),
        "sameRefDifferentClassesRetained": len(same_ref_distinct_classes.hooks) == 2,
        "inputAUnchanged": refs(group_a),
        "inputBUnchanged": refs(group_b),
        "fourSparseOrder": refs(four_result),
        "eightSparseOrder": refs(eight_result),
    }


def run_set_clip_probe(HookGroup: type, classes: dict[str, type]) -> dict[str, object]:
    SetClipHooks = classes["SetClipHooks"]
    node = SetClipHooks()

    plain = FakeClip()
    no_hooks = node.apply_hooks(
        clip=plain,
        schedule_clip=True,
        apply_to_conds=True,
        hooks=None,
    )[0]

    original_keyframes = [FakeKeyframe(0.25, 0.0), FakeKeyframe(1.0, 0.5)]
    source_hooks = make_group(
        HookGroup,
        FakeHook("weight", EnumHookType.Weight, original_keyframes),
        FakeHook("other", EnumHookType.Other),
    )
    base = FakeClip()
    unscheduled = node.apply_hooks(
        clip=base,
        schedule_clip=False,
        apply_to_conds=True,
        hooks=source_hooks,
    )[0]

    inherited_marker = make_group(HookGroup, FakeHook("old-conditioning-hook"))
    already_marked = FakeClip(apply_hooks_to_conds=inherited_marker)
    scheduled = node.apply_hooks(
        clip=already_marked,
        schedule_clip=True,
        apply_to_conds=False,
        hooks=source_hooks,
    )[0]

    non_weight_only = make_group(HookGroup, FakeHook("non-weight", EnumHookType.Other))
    one_weight_no_keyframes = make_group(
        HookGroup,
        FakeHook("static-weight", EnumHookType.Weight),
    )
    same_strength_keyframes = make_group(
        HookGroup,
        FakeHook(
            "same-strength",
            EnumHookType.Weight,
            [FakeKeyframe(0.75, 0.0), FakeKeyframe(0.75, 0.5)],
        ),
    )
    delayed_first_keyframe = make_group(
        HookGroup,
        FakeHook(
            "delayed-first",
            EnumHookType.Weight,
            [FakeKeyframe(0.4, 0.25)],
        ),
    )
    empty_hooks = make_group(HookGroup)
    empty_base = FakeClip()
    empty_scheduled = node.apply_hooks(
        clip=empty_base,
        schedule_clip=True,
        apply_to_conds=True,
        hooks=empty_hooks,
    )[0]

    target = unscheduled.patcher.register_calls[0][1]["target"]
    return {
        "noHooksReturnsInputIdentity": no_hooks is plain,
        "noHooksCloneCalls": plain.clone_calls,
        "clonedDisableDynamic": base.clone_calls,
        "applyToCondsUsesOriginalGroup": unscheduled.apply_hooks_to_conds is source_hooks,
        "unscheduledUseClipSchedule": unscheduled.use_clip_schedule,
        "unscheduledForcedRefs": refs(unscheduled.patcher.forced_hooks),
        "unscheduledForcedKeyframeCounts": [
            len(hook.hook_keyframe.keyframes) for hook in unscheduled.patcher.forced_hooks.hooks
        ],
        "sourceKeyframeCountsUnchanged": [
            len(hook.hook_keyframe.keyframes) for hook in source_hooks.hooks
        ],
        "registrationUsesOriginalGroup": unscheduled.patcher.register_calls[0][0] is source_hooks,
        "registrationTarget": target.value,
        "scheduledUseClipSchedule": scheduled.use_clip_schedule,
        "applyFalseDoesNotClearInheritedHooks": scheduled.apply_hooks_to_conds is inherited_marker,
        "scheduledForcedKeyframeCounts": [
            len(hook.hook_keyframe.keyframes) for hook in scheduled.patcher.forced_hooks.hooks
        ],
        "scheduledForcedSharesKeyframeGroups": [
            forced.hook_keyframe is source.hook_keyframe
            for forced, source in zip(scheduled.patcher.forced_hooks.hooks, source_hooks.hooks)
        ],
        "unscheduledForcedSeparatesKeyframeGroups": [
            forced.hook_keyframe is not source.hook_keyframe
            for forced, source in zip(unscheduled.patcher.forced_hooks.hooks, source_hooks.hooks)
        ],
        "nonWeightSchedule": schedule_ranges(non_weight_only),
        "emptyHooksStillClones": empty_base.clone_calls,
        "emptyHooksGroupIsFalsy": not bool(empty_scheduled.apply_hooks_to_conds),
        "emptyHooksSchedule": schedule_ranges(empty_scheduled.patcher.forced_hooks),
        "staticWeightSchedule": schedule_ranges(one_weight_no_keyframes),
        "sameStrengthDoesNotAddBoundary": schedule_ranges(same_strength_keyframes),
        "delayedFirstKeyframeSchedule": schedule_ranges(delayed_first_keyframe),
        "keyframedWeightSchedule": schedule_ranges(source_hooks),
    }


def run() -> dict[str, object]:
    HookGroup, classes = load_definitions()
    return {
        "combine": run_combine_probe(HookGroup, classes),
        "setClip": run_set_clip_probe(HookGroup, classes),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
