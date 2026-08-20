from __future__ import annotations

import ast
import json
import math
import sys
import types
from pathlib import Path
from typing import Any


SAMPLING_FUNCTION = None


def compile_named(path: Path, names: set[str]):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    body = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name in names
    ]
    found = {node.name for node in body}
    if found != names:
        raise AssertionError(f"missing source definitions: {sorted(names - found)}")
    return compile(ast.Module(body=body, type_ignores=[]), str(path), "exec")


def condition(value: float | None, **metadata: Any) -> list[list[Any]]:
    return [[value, metadata]]


def condition_value(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, list) and value and isinstance(value[0], list):
        scalar = value[0][0]
        return 0.0 if scalar is None else float(scalar)
    return float(value)


class StubCFGGuider:
    def __init__(self, model_patcher: Any):
        self.model_patcher = model_patcher
        self.inner_model = model_patcher
        self.cfg = 1.0
        self.conds: dict[str, Any] = {}

    def inner_set_conds(self, conds: dict[str, Any]) -> None:
        self.conds = dict(conds)

    def set_conds(self, positive: Any, negative: Any) -> None:
        self.inner_set_conds({"positive": positive, "negative": negative})

    def set_cfg(self, cfg: float) -> None:
        self.cfg = cfg

    def predict_noise(
        self,
        x: float,
        timestep: float,
        model_options: dict[str, Any] | None = None,
        seed: int | None = None,
    ) -> float:
        assert SAMPLING_FUNCTION is not None
        return SAMPLING_FUNCTION(
            self.inner_model,
            x,
            timestep,
            self.conds.get("negative"),
            self.conds.get("positive"),
            self.cfg,
            model_options={} if model_options is None else model_options,
            seed=seed,
        )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: guider_synthetic_probe.py <pinned-comfyui-source>")

    source = Path(sys.argv[1]).resolve()
    sampler_source = source / "comfy" / "samplers.py"
    node_source = source / "comfy_extras" / "nodes_custom_sampler.py"
    calls: list[dict[str, Any]] = []

    def calc_cond_batch(
        model: Any,
        conds: list[Any],
        x: float,
        timestep: float,
        model_options: dict[str, Any],
    ) -> list[float]:
        calls.append(
            {
                "model": str(model),
                "present": [item is not None for item in conds],
                "values": [condition_value(item) for item in conds],
            }
        )
        return [condition_value(item) for item in conds]

    sampler_namespace: dict[str, Any] = {
        "math": math,
        "calc_cond_batch": calc_cond_batch,
    }
    exec(
        compile_named(sampler_source, {"cfg_function", "sampling_function"}),
        sampler_namespace,
    )

    global SAMPLING_FUNCTION
    SAMPLING_FUNCTION = sampler_namespace["sampling_function"]

    def conditioning_set_values(
        conditioning: list[list[Any]], values: dict[str, Any]
    ) -> list[list[Any]]:
        result: list[list[Any]] = []
        for tensor, metadata in conditioning:
            copied = dict(metadata)
            copied.update(values)
            result.append([tensor, copied])
        return result

    comfy_samplers = types.SimpleNamespace(
        CFGGuider=StubCFGGuider,
        calc_cond_batch=calc_cond_batch,
        cfg_function=sampler_namespace["cfg_function"],
    )
    comfy = types.SimpleNamespace(
        samplers=comfy_samplers,
        sampler_helpers=types.SimpleNamespace(),
    )
    io = types.SimpleNamespace(
        ComfyNode=object,
        NodeOutput=lambda *items: tuple(items),
    )
    node_namespace: dict[str, Any] = {
        "comfy": comfy,
        "io": io,
        "math": math,
        "node_helpers": types.SimpleNamespace(
            conditioning_set_values=conditioning_set_values
        ),
    }
    exec(
        compile_named(
            node_source,
            {
                "Guider_Basic",
                "BasicGuider",
                "CFGGuider",
                "Guider_DualCFG",
                "DualCFGGuider",
                "Guider_DualModel",
                "DualModelGuider",
            },
        ),
        node_namespace,
    )

    positive = condition(30.0, role="positive")
    negative = condition(10.0, role="negative")
    middle_source = condition(20.0, keep="middle-source")

    basic = node_namespace["BasicGuider"].execute("main-model", positive)[0]
    assert isinstance(basic, node_namespace["Guider_Basic"])
    assert basic.cfg == 1.0
    assert set(basic.conds) == {"positive"}
    calls.clear()
    assert basic.predict_noise(0.0, 1.0) == 30.0
    basic_call = calls[-1]
    assert basic_call["present"] == [True, False]

    cfg = node_namespace["CFGGuider"].execute(
        "main-model", positive, negative, 4.0
    )[0]
    assert type(cfg) is StubCFGGuider
    calls.clear()
    assert cfg.predict_noise(0.0, 1.0) == 90.0
    cfg_formula_call = calls[-1]
    assert cfg_formula_call["values"] == [30.0, 10.0]
    cfg.set_cfg(1.0)
    calls.clear()
    assert cfg.predict_noise(0.0, 1.0) == 30.0
    cfg_one_call = calls[-1]
    assert cfg_one_call["present"] == [True, False]
    calls.clear()
    assert cfg.predict_noise(
        0.0, 1.0, {"disable_cfg1_optimization": True}
    ) == 30.0
    cfg_one_disabled_call = calls[-1]
    assert cfg_one_disabled_call["present"] == [True, True]

    dual_regular = node_namespace["DualCFGGuider"].execute(
        "main-model",
        positive,
        middle_source,
        negative,
        2.0,
        3.0,
        "regular",
    )[0]
    assert middle_source[0][1] == {"keep": "middle-source"}
    assert dual_regular.conds["middle"][0][1] == {
        "keep": "middle-source",
        "prompt_type": "negative",
    }
    calls.clear()
    regular_result = dual_regular.predict_noise(0.0, 1.0)
    assert regular_result == 60.0
    regular_call = calls[-1]
    assert regular_call["values"] == [10.0, 20.0, 30.0]

    dual_nested = node_namespace["DualCFGGuider"].execute(
        "main-model", positive, middle_source, negative, 2.0, 3.0, "nested"
    )[0]
    calls.clear()
    nested_result = dual_nested.predict_noise(0.0, 1.0)
    assert nested_result == 100.0
    nested_call = calls[-1]
    assert nested_call["present"] == [True, True, True]

    dual_regular.set_cfg(1.0, 1.0, nested=False)
    calls.clear()
    assert dual_regular.predict_noise(0.0, 1.0) == 30.0
    regular_one_call = calls[-1]
    assert regular_one_call["present"] == [False, False, True]
    dual_regular.set_cfg(1.0, 1.0, nested=False)
    calls.clear()
    assert dual_regular.predict_noise(
        0.0, 1.0, {"disable_cfg1_optimization": True}
    ) == 30.0
    regular_one_disabled_call = calls[-1]
    assert regular_one_disabled_call["present"] == [True, True, True]

    fallback = node_namespace["DualModelGuider"].execute(
        "main-model", positive, 4.0, model_negative=None, negative=None
    )[0]
    assert type(fallback) is StubCFGGuider
    assert fallback.conds["negative"] == [[None, {}]]
    dual_model = node_namespace["DualModelGuider"].execute(
        "main-model",
        positive,
        4.0,
        model_negative="negative-model",
        negative=negative,
    )[0]
    assert isinstance(dual_model, node_namespace["Guider_DualModel"])
    assert dual_model.uncond_model_patcher == "negative-model"
    dual_model.inner_model = "positive-inner"
    dual_model.uncond_inner = "negative-inner"
    dual_model._uncond_conds = negative
    calls.clear()
    dual_model_result = dual_model.predict_noise(0.0, 1.0)
    assert dual_model_result == 90.0
    assert [item["model"] for item in calls] == [
        "positive-inner",
        "negative-inner",
    ]
    dual_model.set_cfg(1.0)
    calls.clear()
    assert dual_model.predict_noise(0.0, 1.0) == 30.0
    assert [item["model"] for item in calls] == ["positive-inner"]
    calls.clear()
    assert dual_model.predict_noise(
        0.0, 1.0, {"disable_cfg1_optimization": True}
    ) == 30.0
    assert [item["model"] for item in calls] == [
        "positive-inner",
        "negative-inner",
    ]

    print(
        json.dumps(
            {
                "basic": {
                    "cfg": basic.cfg,
                    "conditions": sorted(basic.conds),
                    "result": 30.0,
                    "batchPresence": basic_call["present"],
                },
                "cfg": {
                    "cfg4Result": 90.0,
                    "cfg1BatchPresence": cfg_one_call["present"],
                    "cfg1DisabledBatchPresence": cfg_one_disabled_call["present"],
                },
                "dualCfg": {
                    "regularResult": regular_result,
                    "nestedResult": nested_result,
                    "middleMetadata": dual_regular.conds["middle"][0][1],
                    "regularCfg1Presence": regular_one_call["present"],
                    "regularCfg1DisabledPresence": regular_one_disabled_call["present"],
                    "nestedPresence": nested_call["present"],
                },
                "dualModel": {
                    "fallbackClass": type(fallback).__name__,
                    "nullNegative": fallback.conds["negative"],
                    "separateClass": type(dual_model).__name__,
                    "cfg4Result": dual_model_result,
                    "cfg1Models": ["positive-inner"],
                    "cfg1DisabledModels": ["positive-inner", "negative-inner"],
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
