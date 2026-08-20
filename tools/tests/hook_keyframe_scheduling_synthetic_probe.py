from __future__ import annotations

import ast
import itertools
import json
import logging
import math
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Union

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".comfyui-source-0.32.0"
HOOKS_SOURCE = SOURCE / "comfy" / "hooks.py"
NODES_SOURCE = SOURCE / "comfy_extras" / "nodes_hooks.py"


def source_object(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    raise RuntimeError(f"{name} not found in {path}")


hooks_namespace = {
    "torch": torch,
    "np": np,
    "Hook": object,
    "EnumHookType": SimpleNamespace(Weight="weight"),
    "WeightHook": object,
    "itertools": itertools,
    "math": math,
}
for name in ("HookKeyframe", "HookKeyframeGroup", "InterpolationMethod", "get_sorted_list_via_attr", "HookGroup"):
    exec("from __future__ import annotations\n" + source_object(HOOKS_SOURCE, name), hooks_namespace)

HookKeyframe = hooks_namespace["HookKeyframe"]
HookKeyframeGroup = hooks_namespace["HookKeyframeGroup"]
InterpolationMethod = hooks_namespace["InterpolationMethod"]
HookGroup = hooks_namespace["HookGroup"]


class FakeHook:
    def __init__(self, label: str, hook_keyframe=None):
        self.label = label
        self.hook_type = "weight"
        self.hook_keyframe = hook_keyframe if hook_keyframe is not None else HookKeyframeGroup()

    def clone(self):
        return FakeHook(self.label, self.hook_keyframe)


class FakeSampling:
    @staticmethod
    def percent_to_sigma(percent: float) -> float:
        return 10.0 * (1.0 - float(percent))


comfy = SimpleNamespace(
    hooks=SimpleNamespace(
        HookGroup=HookGroup,
        HookKeyframe=HookKeyframe,
        HookKeyframeGroup=HookKeyframeGroup,
        InterpolationMethod=InterpolationMethod,
    )
)
node_namespace = {
    "comfy": comfy,
    "logging": logging,
    "Union": Union,
    "Iterable": Iterable,
}
for name in ("SetHookKeyframes", "CreateHookKeyframe", "CreateHookKeyframesInterpolated", "CreateHookKeyframesFromFloats"):
    exec("from __future__ import annotations\n" + source_object(NODES_SOURCE, name), node_namespace)

SetHookKeyframes = node_namespace["SetHookKeyframes"]
CreateHookKeyframe = node_namespace["CreateHookKeyframe"]
CreateHookKeyframesInterpolated = node_namespace["CreateHookKeyframesInterpolated"]
CreateHookKeyframesFromFloats = node_namespace["CreateHookKeyframesFromFloats"]


def values(group):
    return [
        [float(frame.start_percent), float(frame.strength), int(frame.guarantee_steps)]
        for frame in group.keyframes
    ]


def make_group(*frames):
    group = HookKeyframeGroup()
    for strength, percent, guarantee in frames:
        group.add(HookKeyframe(strength=strength, start_percent=percent, guarantee_steps=guarantee))
    return group


def sampling_trace(group, timesteps, sample_sigmas=(8.0, 6.0, 4.0, 2.0)):
    model = SimpleNamespace(model_sampling=FakeSampling())
    transformer_options = {"sample_sigmas": torch.tensor(sample_sigmas)}
    group.initialize_timesteps(model)
    group.reset()
    trace = []
    for timestep in timesteps:
        changed = group.prepare_current_keyframe(
            curr_t=torch.tensor(float(timestep)),
            transformer_options=transformer_options,
        )
        trace.append(
            {
                "sigma": float(timestep),
                "index": int(group._current_index),
                "strength": float(group.strength),
                "usedSteps": int(group._current_used_steps),
                "changed": bool(changed),
            }
        )
    return {
        "startSigmas": [float(frame.start_t) for frame in group.keyframes],
        "trace": trace,
    }


def floats_edge_result(value):
    try:
        group = CreateHookKeyframesFromFloats().create_hook_keyframes(
            floats_strength=value,
            start_percent=0.0,
            end_percent=1.0,
            print_keyframes=False,
        )[0]
        return {"ok": True, "values": values(group)}
    except Exception as exc:
        return {"ok": False, "errorType": type(exc).__name__, "message": str(exc)}


def main() -> None:
    base_schedule_a = make_group((0.25, 0.0, 1))
    base_schedule_b = make_group((0.75, 0.0, 1))
    hooks = HookGroup()
    first = FakeHook("first", base_schedule_a)
    second = FakeHook("second", base_schedule_b)
    hooks.add(first)
    hooks.add(second)

    setter = SetHookKeyframes()
    no_schedule = setter.set_hook_keyframes(hooks=hooks, hook_kf=None)[0]
    supplied = make_group((0.1, 0.0, 1), (0.9, 0.6, 0))
    scheduled = setter.set_hook_keyframes(hooks=hooks, hook_kf=supplied)[0]
    source_before_mutation = values(supplied)
    supplied.keyframes[0].strength = 9.0
    scheduled_after_mutation = values(scheduled.hooks[0].hook_keyframe)
    empty_applied = setter.set_hook_keyframes(hooks=hooks, hook_kf=HookKeyframeGroup())[0]

    shared_schedule = scheduled.hooks[0].hook_keyframe
    shared_schedule.initialize_timesteps(SimpleNamespace(model_sampling=FakeSampling()))
    shared_schedule.reset()
    shared_options = {"sample_sigmas": torch.tensor([8.0, 6.0, 4.0, 2.0])}
    first_hook_changed = scheduled.hooks[0].hook_keyframe.prepare_current_keyframe(
        curr_t=torch.tensor(4.0), transformer_options=shared_options
    )
    used_after_first_hook = shared_schedule._current_used_steps
    second_hook_changed = scheduled.hooks[1].hook_keyframe.prepare_current_keyframe(
        curr_t=torch.tensor(4.0), transformer_options=shared_options
    )
    used_after_second_hook = shared_schedule._current_used_steps

    advanced_source = make_group((1.0, 0.0, 1), (2.0, 0.5, 1))
    sampling_trace(advanced_source, [8.0, 5.0])
    advanced_clone = setter.set_hook_keyframes(hooks=hooks, hook_kf=advanced_source)[0].hooks[0].hook_keyframe

    single = CreateHookKeyframe()
    previous = make_group((8.0, 0.8, 1))
    single_out = single.create_hook_keyframe(strength_mult=-2.0, start_percent=0.2, prev_hook_kf=previous)[0]
    equal_out = single.create_hook_keyframe(strength_mult=3.0, start_percent=0.8, prev_hook_kf=previous)[0]
    equal_model = single.create_hook_keyframe(strength_mult=1.0, start_percent=0.5)[0]
    equal_model = single.create_hook_keyframe(strength_mult=2.0, start_percent=0.5, prev_hook_kf=equal_model)[0]
    equal_model = single.create_hook_keyframe(strength_mult=3.0, start_percent=0.5, prev_hook_kf=equal_model)[0]
    equal_model_trace = sampling_trace(equal_model, [8.0, 7.0, 5.0, 4.0])

    partial_range = single.create_hook_keyframe(strength_mult=1.0, start_percent=0.0)[0]
    partial_range = single.create_hook_keyframe(strength_mult=2.0, start_percent=0.1, prev_hook_kf=partial_range)[0]
    partial_range = single.create_hook_keyframe(strength_mult=3.0, start_percent=0.3, prev_hook_kf=partial_range)[0]
    partial_range_trace = sampling_trace(partial_range, [8.0, 7.0, 6.0])

    clip_group = HookGroup()
    clip_group.add(FakeHook("clip", equal_model))
    clip_ranges = []
    for percent_range, hook_frames in clip_group.get_hooks_for_clip_schedule():
        clip_ranges.append(
            {
                "range": [float(percent_range[0]), float(percent_range[1])],
                "frames": [
                    None if frame is None else [float(frame.start_percent), float(frame.strength)]
                    for _, frame in hook_frames
                ],
            }
        )

    interpolated = CreateHookKeyframesInterpolated()
    linear = interpolated.create_hook_keyframes(
        strength_start=1.0,
        strength_end=3.0,
        interpolation="linear",
        start_percent=0.0,
        end_percent=1.0,
        keyframes_count=5,
        print_keyframes=False,
    )[0]
    ease = {}
    for method in ("ease_in", "ease_out", "ease_in_out"):
        ease[method] = values(
            interpolated.create_hook_keyframes(
                strength_start=0.0,
                strength_end=1.0,
                interpolation=method,
                start_percent=0.0,
                end_percent=1.0,
                keyframes_count=3,
                print_keyframes=False,
            )[0]
        )
    descending = interpolated.create_hook_keyframes(
        strength_start=1.0,
        strength_end=3.0,
        interpolation="linear",
        start_percent=0.8,
        end_percent=0.2,
        keyframes_count=3,
        print_keyframes=False,
    )[0]
    interpolated_equal = interpolated.create_hook_keyframes(
        strength_start=1.0,
        strength_end=3.0,
        interpolation="linear",
        start_percent=0.5,
        end_percent=0.5,
        keyframes_count=3,
        print_keyframes=False,
    )[0]
    interpolated_equal_trace = sampling_trace(interpolated_equal, [8.0, 7.0, 5.0, 4.0])

    from_floats = CreateHookKeyframesFromFloats()
    listed = from_floats.create_hook_keyframes(
        floats_strength=[0.2, 0.4, 0.8],
        start_percent=0.1,
        end_percent=0.9,
        print_keyframes=False,
    )[0]
    scalar = from_floats.create_hook_keyframes(
        floats_strength=0.6,
        start_percent=0.3,
        end_percent=0.9,
        print_keyframes=False,
    )[0]
    seed_group = make_group((4.0, 0.4, 1))
    empty = from_floats.create_hook_keyframes(
        floats_strength=[],
        start_percent=0.0,
        end_percent=1.0,
        prev_hook_kf=seed_group,
        print_keyframes=False,
    )[0]
    floats_descending = from_floats.create_hook_keyframes(
        floats_strength=[1.0, 2.0, 3.0],
        start_percent=0.8,
        end_percent=0.2,
        print_keyframes=False,
    )[0]
    floats_equal = from_floats.create_hook_keyframes(
        floats_strength=[1.0, 2.0, 3.0],
        start_percent=0.5,
        end_percent=0.5,
        print_keyframes=False,
    )[0]
    floats_equal_trace = sampling_trace(floats_equal, [8.0, 7.0, 5.0, 4.0])

    payload = {
        "set": {
            "noneReturnsInputIdentity": no_schedule is hooks,
            "providedCreatesClone": scheduled is not hooks,
            "inputHooksUnchanged": first.hook_keyframe is base_schedule_a and second.hook_keyframe is base_schedule_b,
            "outputHooksAreClones": scheduled.hooks[0] is not first and scheduled.hooks[1] is not second,
            "outputHooksShareOneSchedule": scheduled.hooks[0].hook_keyframe is scheduled.hooks[1].hook_keyframe,
            "scheduleWasCloned": scheduled.hooks[0].hook_keyframe is not supplied,
            "sourceBeforeMutation": source_before_mutation,
            "outputAfterSourceMutation": scheduled_after_mutation,
            "emptyStillClonesHooks": empty_applied is not hooks,
            "emptyClearsSchedule": values(empty_applied.hooks[0].hook_keyframe),
            "emptyStrengthDefaultsToOne": float(empty_applied.hooks[0].hook_keyframe.strength),
            "sharedRuntime": {
                "firstHookChanged": bool(first_hook_changed),
                "secondHookChanged": bool(second_hook_changed),
                "usedAfterFirstHook": int(used_after_first_hook),
                "usedAfterSecondHook": int(used_after_second_hook),
                "currentIndex": int(shared_schedule._current_index),
            },
            "cloneResetsRuntimeState": {
                "sourceIndex": int(advanced_source._current_index),
                "cloneIndex": int(advanced_clone._current_index),
                "sourceUsedSteps": int(advanced_source._current_used_steps),
                "cloneUsedSteps": int(advanced_clone._current_used_steps),
            },
        },
        "single": {
            "previousUnchanged": values(previous),
            "sortedOutput": values(single_out),
            "outputIsClone": single_out is not previous,
            "equalPercentStable": values(equal_out),
            "equalPercentModelTrace": equal_model_trace,
            "partialRangeTrace": partial_range_trace,
            "equalPercentClipRanges": clip_ranges,
        },
        "interpolated": {
            "linear": values(linear),
            "ease": ease,
            "descendingSorted": values(descending),
            "allowedMethods": list(InterpolationMethod._LIST),
            "equalPercent": values(interpolated_equal),
            "equalPercentModelTrace": interpolated_equal_trace,
            "reverseHelper": [
                float(value)
                for value in InterpolationMethod.get_weights(
                    num_from=1.0,
                    num_to=3.0,
                    length=3,
                    method=InterpolationMethod.LINEAR,
                    reverse=True,
                )
            ],
        },
        "fromFloats": {
            "listed": values(listed),
            "scalarUsesStart": values(scalar),
            "emptyReturnsClonedPrevious": values(empty),
            "emptyIsClone": empty is not seed_group,
            "descendingSorted": values(floats_descending),
            "equalPercent": values(floats_equal),
            "equalPercentModelTrace": floats_equal_trace,
            "edgeInputs": {
                "emptyTuple": floats_edge_result(()),
                "generator": floats_edge_result(iter([1.0, 2.0])),
                "zeroDimTensor": floats_edge_result(torch.tensor(0.5)),
                "string": floats_edge_result("12"),
            },
        },
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
