from __future__ import annotations

import ast
import json
import math
import sys
import types
from pathlib import Path

import torch


class _IO:
    ComfyNode = object

    @staticmethod
    def NodeOutput(*values):
        return values


def selected_definitions(path: Path, names: set[str]) -> list[ast.stmt]:
    """Read only the requested definitions from the pinned source module."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names
    ]


def execute_definitions(path: Path, names: set[str], namespace: dict) -> dict:
    module = ast.Module(body=selected_definitions(path, names), type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


class OverrideModelSampling:
    @staticmethod
    def percent_to_sigma(percent):
        return 10.0 * (1.0 - float(percent))


class OverrideModel:
    def __init__(self, model_sampling=None):
        self.model_sampling = model_sampling or OverrideModelSampling()
        self.wrapper = None

    def get_model_object(self, name):
        if name != "model_sampling":
            raise AssertionError(name)
        return self.model_sampling

    def clone(self):
        return OverrideModel(self.model_sampling)

    def add_wrapper(self, wrapper_type, wrapper):
        if wrapper_type != "PREDICT_NOISE":
            raise AssertionError(wrapper_type)
        self.wrapper = wrapper


class RecordingExecutor:
    def __init__(self, cfg=9.0, fail=False):
        self.class_obj = types.SimpleNamespace(cfg=float(cfg))
        self.fail = fail
        self.seen: list[float] = []

    def __call__(self, *args, **kwargs):
        del args, kwargs
        self.seen.append(float(self.class_obj.cfg))
        if self.fail:
            raise RuntimeError("synthetic executor failure")
        return float(self.class_obj.cfg)


class PatchableModel:
    def __init__(self, cfg_function=None):
        self.cfg_function = cfg_function
        self.set_count = 0

    def clone(self):
        return PatchableModel(self.cfg_function)

    def set_model_sampler_cfg_function(self, function):
        self.cfg_function = function
        self.set_count += 1


class StubCFGGuider:
    def __init__(self, model):
        self.inner_model = model
        self.conds = {}

    def inner_set_conds(self, conds):
        self.conds = conds


def schedule(function, count: int, cond_scale: float = 5.0) -> list[float]:
    cond = torch.ones((count, 1, 1, 1), dtype=torch.float32)
    uncond = torch.zeros_like(cond)
    result = function(
        {"cond": cond, "uncond": uncond, "cond_scale": float(cond_scale)}
    )
    return [float(value) for value in result.flatten()]


def main() -> None:
    source_root = Path(sys.argv[1]).resolve()
    override_path = source_root / "comfy_extras" / "nodes_custom_sampler.py"
    video_path = source_root / "comfy_extras" / "nodes_video_model.py"
    perp_path = source_root / "comfy_extras" / "nodes_perpneg.py"

    override_ns = {
        "torch": torch,
        "io": _IO,
        "comfy": types.SimpleNamespace(
            patcher_extension=types.SimpleNamespace(
                WrappersMP=types.SimpleNamespace(PREDICT_NOISE="PREDICT_NOISE")
            )
        ),
    }
    execute_definitions(override_path, {"CFGOverride"}, override_ns)
    override_class = override_ns["CFGOverride"]

    patched = override_class.execute(OverrideModel(), 3.0, 0.2, 0.8)[0]
    if patched.wrapper is None:
        raise AssertionError("CFGOverride did not register the predict-noise wrapper")

    outside = RecordingExecutor()
    outside_result = patched.wrapper(
        outside, object(), torch.tensor([9.0]), {}, 0
    )
    inside = RecordingExecutor()
    inside_result = patched.wrapper(
        inside, object(), torch.tensor([5.0]), {}, 0
    )
    lower_endpoint = RecordingExecutor()
    patched.wrapper(lower_endpoint, object(), torch.tensor([2.0]), {}, 0)
    upper_endpoint = RecordingExecutor()
    patched.wrapper(upper_endpoint, object(), torch.tensor([8.0]), {}, 0)

    failing = RecordingExecutor(fail=True)
    try:
        patched.wrapper(failing, object(), torch.tensor([5.0]), {}, 0)
    except RuntimeError as error:
        failure_message = str(error)
    else:
        raise AssertionError("the synthetic failure did not propagate")

    reversed_patch = override_class.execute(OverrideModel(), 3.0, 0.8, 0.2)[0]
    reversed_executor = RecordingExecutor()
    reversed_result = reversed_patch.wrapper(
        reversed_executor, object(), torch.tensor([5.0]), {}, 0
    )

    video_ns = {"torch": torch}
    execute_definitions(
        video_path,
        {"VideoLinearCFGGuidance", "VideoTriangleCFGGuidance"},
        video_ns,
    )
    linear_class = video_ns["VideoLinearCFGGuidance"]
    triangle_class = video_ns["VideoTriangleCFGGuidance"]

    sentinel = lambda args: args["cond"]  # noqa: E731 - identity is inspected below
    original_video_model = PatchableModel(sentinel)
    linear_model = linear_class().patch(original_video_model, 1.0)[0]
    triangle_model = triangle_class().patch(original_video_model, 1.0)[0]

    chained_model = triangle_class().patch(linear_model, 1.0)[0]

    comfy_stub = types.SimpleNamespace(
        samplers=types.SimpleNamespace(CFGGuider=StubCFGGuider)
    )
    node_helpers_stub = types.SimpleNamespace(
        conditioning_set_values=lambda conditioning, values: [conditioning, dict(values)]
    )
    perp_ns = {
        "torch": torch,
        "math": math,
        "io": _IO,
        "comfy": comfy_stub,
        "node_helpers": node_helpers_stub,
    }
    execute_definitions(
        perp_path,
        {"perp_neg", "Guider_PerpNeg", "PerpNegGuider"},
        perp_ns,
    )

    perp_function = perp_ns["perp_neg"]
    normal = perp_function(
        torch.zeros(2),
        torch.tensor([2.0, 0.0]),
        torch.tensor([1.0, 1.0]),
        torch.tensor([0.0, 0.0]),
        0.5,
        2.0,
    )
    zero_norm = perp_function(
        torch.zeros(2),
        torch.tensor([0.0, 0.0]),
        torch.tensor([1.0, 1.0]),
        torch.tensor([0.0, 0.0]),
        1.0,
        8.0,
    )
    guider = perp_ns["PerpNegGuider"].execute(
        object(), "positive", "negative", "empty", 8.0, 1.0
    )[0]

    print(
        json.dumps(
            {
                "override": {
                    "sigmaBounds": [2.0, 8.0],
                    "outsideResult": outside_result,
                    "outsideSeen": outside.seen,
                    "outsideRestored": outside.class_obj.cfg,
                    "insideResult": inside_result,
                    "insideSeen": inside.seen,
                    "insideRestored": inside.class_obj.cfg,
                    "endpointSeen": lower_endpoint.seen + upper_endpoint.seen,
                    "failureSeen": failing.seen,
                    "failureRestored": failing.class_obj.cfg,
                    "failureMessage": failure_message,
                    "reversedResult": reversed_result,
                    "reversedSeen": reversed_executor.seen,
                    "reversedRestored": reversed_executor.class_obj.cfg,
                },
                "video": {
                    "originalUnchanged": original_video_model.cfg_function is sentinel,
                    "linearSetCount": linear_model.set_count,
                    "triangleSetCount": triangle_model.set_count,
                    "linear": {
                        str(count): schedule(linear_model.cfg_function, count)
                        for count in (1, 2, 4, 5)
                    },
                    "triangle": {
                        str(count): schedule(triangle_model.cfg_function, count)
                        for count in (1, 2, 4, 5)
                    },
                    "chainedLinearStillLinear": schedule(linear_model.cfg_function, 5),
                    "chainedFinalTriangle": schedule(chained_model.cfg_function, 5),
                    "chainedSetCount": chained_model.set_count,
                },
                "perpNeg": {
                    "normal": [float(value) for value in normal],
                    "zeroNorm": [float(value) for value in zero_norm],
                    "zeroNormAllNan": bool(torch.isnan(zero_norm).all()),
                    "constructor": {
                        "cfg": float(guider.cfg),
                        "negScale": float(guider.neg_scale),
                        "condKeys": sorted(guider.conds),
                        "emptyPromptType": guider.conds["empty_negative_prompt"][1][
                            "prompt_type"
                        ],
                    },
                },
            },
            ensure_ascii=False,
            allow_nan=True,
        )
    )


if __name__ == "__main__":
    main()
