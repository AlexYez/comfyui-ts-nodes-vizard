from __future__ import annotations

import ast
import json
import math
from pathlib import Path
from types import SimpleNamespace

import torch


ROOT = Path(__file__).resolve().parents[2]
IDEOGRAM_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy_extras" / "nodes_ideogram4.py"
FLUX_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy_extras" / "nodes_flux.py"
LTX_SOURCE = ROOT / ".comfyui-source-0.32.0" / "comfy_extras" / "nodes_lt.py"


class DummyNodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class DummyComfyNode:
    pass


IO = SimpleNamespace(ComfyNode=DummyComfyNode, NodeOutput=DummyNodeOutput, Schema=object)


def extract(path: Path, functions: set[str], classes: set[str], namespace: dict[str, object]) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected: list[ast.stmt] = []
    found_functions: set[str] = set()
    found_classes: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in functions:
            selected.append(node)
            found_functions.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name in classes:
            selected.append(node)
            found_classes.add(node.name)
    if found_functions != functions or found_classes != classes:
        raise AssertionError(
            f"missing exact definitions in {path}: functions={functions - found_functions}, classes={classes - found_classes}"
        )
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in functions | classes}


def run() -> dict[str, object]:
    ideogram = extract(
        IDEOGRAM_SOURCE,
        {"_logit_normal_schedule", "ideogram4_sigmas"},
        {"Ideogram4Scheduler"},
        {
            "math": math,
            "torch": torch,
            "io": IO,
            "_LOGSNR_MIN": -15.0,
            "_LOGSNR_MAX": 18.0,
        },
    )
    ideogram_node = ideogram["Ideogram4Scheduler"]
    ideogram_default = ideogram_node.execute(4, 1024, 1024, 0.0, 1.75).values[0]
    ideogram_official = ideogram_node.execute(4, 1024, 1024, 0.5, 1.75).values[0]
    ideogram_one = ideogram_node.execute(1, 1024, 1024, 0.0, 1.75).values[0]
    ideogram_landscape = ideogram_node.execute(4, 1024, 512, 0.0, 1.75).values[0]
    ideogram_portrait = ideogram_node.execute(4, 512, 1024, 0.0, 1.75).values[0]
    ideogram_low_area = ideogram_node.execute(4, 512, 512, 0.0, 1.75).values[0]
    ideogram_high_area = ideogram_node.execute(4, 2048, 2048, 0.0, 1.75).values[0]
    assert ideogram_default.shape == (5,)
    assert ideogram_default.dtype == torch.float32
    assert torch.all(ideogram_default[:-1] > ideogram_default[1:])
    assert ideogram_default[-1] == 0
    assert torch.equal(ideogram_landscape, ideogram_portrait)
    assert torch.all(ideogram_high_area[:-1] >= ideogram_low_area[:-1])
    assert ideogram_one.shape == (2,) and ideogram_one[-1] == 0

    flux = extract(
        FLUX_SOURCE,
        {"generalized_time_snr_shift", "compute_empirical_mu", "get_schedule"},
        {"Flux2Scheduler"},
        {
            "math": math,
            "torch": torch,
            "io": IO,
            "nodes": SimpleNamespace(MAX_RESOLUTION=16384),
        },
    )
    flux_node = flux["Flux2Scheduler"]
    flux_default = flux_node.execute(4, 1024, 1024).values[0]
    flux_rect = flux_node.execute(20, 1248, 832).values[0]
    flux_landscape = flux_node.execute(4, 1024, 512).values[0]
    flux_portrait = flux_node.execute(4, 512, 1024).values[0]
    flux_max = flux_node.execute(4, 16384, 16384).values[0]
    mu_4096 = [flux["compute_empirical_mu"](4096, steps) for steps in (4, 20, 200)]
    mu_threshold = [flux["compute_empirical_mu"](tokens, 20) for tokens in (4300, 4301)]
    mu_above_steps = [flux["compute_empirical_mu"](4301, steps) for steps in (4, 20, 200)]
    assert flux_default.shape == (5,)
    assert flux_default[0] == 1 and flux_default[-1] == 0
    assert torch.all(flux_default[:-1] > flux_default[1:])
    assert torch.equal(flux_landscape, flux_portrait)
    assert mu_4096[0] != mu_4096[1] != mu_4096[2]
    assert mu_above_steps[0] == mu_above_steps[1] == mu_above_steps[2]
    assert torch.isnan(flux_max).all()

    ltx = extract(
        LTX_SOURCE,
        set(),
        {"LTXVScheduler"},
        {"math": math, "torch": torch, "io": IO},
    )
    ltx_node = ltx["LTXVScheduler"]
    ltx_default = ltx_node.execute(4, 2.05, 0.95, True, 0.1).values[0]
    ltx_raw = ltx_node.execute(4, 2.05, 0.95, False, 0.1).values[0]
    latent_4096 = {"samples": torch.empty(1, 128, 1, 64, 64), "noise_mask": torch.ones(1)}
    latent_768 = {"samples": torch.empty(1, 128, 3, 16, 16)}
    ltx_latent_4096 = ltx_node.execute(4, 2.05, 0.95, True, 0.1, latent_4096).values[0]
    ltx_latent_768 = ltx_node.execute(4, 2.05, 0.95, True, 0.1, latent_768).values[0]
    ltx_terminal_zero = ltx_node.execute(4, 2.05, 0.95, True, 0.0).values[0]
    ltx_one_stretched = ltx_node.execute(1, 2.05, 0.95, True, 0.1).values[0]
    ltx_one_zero_shift = ltx_node.execute(1, 0.0, 0.0, True, 0.1).values[0]
    ltx_one_raw = ltx_node.execute(1, 2.05, 0.95, False, 0.1).values[0]
    ltx_extreme = ltx_node.execute(4, 100.0, 100.0, False, 0.1).values[0]
    ltx_equal_shift_small = ltx_node.execute(4, 1.5, 1.5, False, 0.1, latent_768).values[0]
    ltx_equal_shift_default = ltx_node.execute(4, 1.5, 1.5, False, 0.1).values[0]
    assert ltx_default.shape == (5,) and torch.isclose(ltx_default[0], torch.tensor(1.0)) and ltx_default[-1] == 0
    assert torch.isclose(ltx_default[-2], torch.tensor(0.1))
    assert torch.equal(ltx_default, ltx_latent_4096)
    assert not torch.equal(ltx_default, ltx_latent_768)
    assert ltx_terminal_zero[-2:].tolist() == [0.0, 0.0]
    assert torch.isclose(ltx_one_stretched[0], torch.tensor(0.1)) and ltx_one_stretched[-1] == 0
    assert torch.isnan(ltx_one_zero_shift[0]) and ltx_one_zero_shift[-1] == 0
    assert torch.isclose(ltx_one_raw[0], torch.tensor(1.0)) and ltx_one_raw[-1] == 0
    assert torch.isnan(ltx_extreme[:-1]).all() and ltx_extreme[-1] == 0
    assert torch.equal(ltx_equal_shift_small, ltx_equal_shift_default)

    return {
        "ideogram4": {
            "defaultFour": ideogram_default.tolist(),
            "officialMuHalf": ideogram_official.tolist(),
            "oneStep": ideogram_one.tolist(),
            "areaOrderOnly": torch.equal(ideogram_landscape, ideogram_portrait),
            "lowArea": ideogram_low_area.tolist(),
            "highArea": ideogram_high_area.tolist(),
            "dtype": str(ideogram_default.dtype),
        },
        "flux2": {
            "defaultFour": flux_default.tolist(),
            "officialRectangleTwenty": flux_rect.tolist(),
            "areaOrderOnly": torch.equal(flux_landscape, flux_portrait),
            "muAt4096ForSteps4_20_200": mu_4096,
            "muAt4300And4301For20": mu_threshold,
            "muAboveThresholdForSteps4_20_200": mu_above_steps,
            "maxResolutionIsNan": torch.isnan(flux_max).tolist(),
        },
        "ltxv": {
            "defaultFourStretched": ltx_default.tolist(),
            "defaultFourRaw": ltx_raw.tolist(),
            "latent4096MatchesFallback": torch.equal(ltx_default, ltx_latent_4096),
            "latent768": ltx_latent_768.tolist(),
            "terminalZero": ltx_terminal_zero.tolist(),
            "oneStepStretched": ltx_one_stretched.tolist(),
            "oneStepZeroShift": ltx_one_zero_shift.tolist(),
            "oneStepRaw": ltx_one_raw.tolist(),
            "extremeIsNan": torch.isnan(ltx_extreme).tolist(),
            "equalShiftsIgnoreLatentSize": torch.equal(ltx_equal_shift_small, ltx_equal_shift_default),
        },
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
