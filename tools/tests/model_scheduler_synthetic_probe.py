from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import torch


class _ComfyNode:
    pass


class _Schema:
    pass


class _NodeOutput:
    def __init__(self, *args: Any) -> None:
        self.args = args
        self.result = args


IO = SimpleNamespace(ComfyNode=_ComfyNode, Schema=_Schema, NodeOutput=_NodeOutput)


def _load_source_symbols(path: Path, names: set[str]) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            selected.append(node)
            continue
        if isinstance(node, ast.Assign):
            targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if any(target in names for target in targets):
                selected.append(node)
    namespace: dict[str, Any] = {"io": IO, "np": np, "torch": torch}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def run_probe(source_root: Path) -> dict[str, Any]:
    custom_path = source_root / "comfy_extras" / "nodes_custom_sampler.py"
    ays_path = source_root / "comfy_extras" / "nodes_align_your_steps.py"
    gits_path = source_root / "comfy_extras" / "nodes_gits.py"
    optimal_path = source_root / "comfy_extras" / "nodes_optimalsteps.py"

    turbo = _load_source_symbols(custom_path, {"SDTurboScheduler"})["SDTurboScheduler"]
    ays = _load_source_symbols(
        ays_path, {"NOISE_LEVELS", "loglinear_interp", "AlignYourStepsScheduler"}
    )["AlignYourStepsScheduler"]
    gits = _load_source_symbols(
        gits_path, {"NOISE_LEVELS", "loglinear_interp", "GITSScheduler"}
    )["GITSScheduler"]
    optimal = _load_source_symbols(
        optimal_path, {"NOISE_LEVELS", "loglinear_interp", "OptimalStepsScheduler"}
    )["OptimalStepsScheduler"]

    class _ModelSampling:
        @staticmethod
        def sigma(timesteps: torch.Tensor) -> torch.Tensor:
            return timesteps.to(torch.float32) / 1000.0

    class _Model:
        @staticmethod
        def get_model_object(name: str) -> _ModelSampling:
            assert name == "model_sampling"
            return _ModelSampling()

    turbo_full = turbo.execute(_Model(), 1, 1.0).args[0]
    turbo_quantized = turbo.execute(_Model(), 1, 0.99).args[0]
    turbo_truncated = turbo.execute(_Model(), 10, 0.5).args[0]
    turbo_zero = turbo.execute(_Model(), 10, 0.0).args[0]
    torch.testing.assert_close(turbo_full, torch.tensor([0.999, 0.0]))
    torch.testing.assert_close(turbo_quantized, torch.tensor([0.899, 0.0]))
    torch.testing.assert_close(
        turbo_truncated, torch.tensor([0.499, 0.399, 0.299, 0.199, 0.099, 0.0])
    )
    torch.testing.assert_close(turbo_zero, torch.tensor([0.0]))

    ays_native = ays.execute("SDXL", 10, 1.0).args[0]
    assert len(ays_native) == 11
    torch.testing.assert_close(
        ays_native[:3], torch.tensor([14.6146412293, 6.3184485287, 3.7681790315])
    )
    assert float(ays_native[-1]) == 0.0
    ays_half = ays.execute("SDXL", 10, 0.5).args[0]
    assert len(ays_half) == 6
    assert ays.execute("SDXL", 10, 0.0).args[0].numel() == 0
    assert ays.execute("SDXL", 10, 0.01).args[0].tolist() == [0.0]
    ays_interpolated = ays.execute("SDXL", 12, 1.0).args[0]
    assert len(ays_interpolated) == 13
    assert bool(torch.all(ays_interpolated[:-2] > ays_interpolated[1:-1]))

    gits_native = gits.execute(1.2, 10, 1.0).args[0]
    assert len(gits_native) == 11
    assert float(gits_native[0]) == torch.tensor(14.61464119).item()
    assert float(gits_native[-1]) == 0.0
    gits_interpolated = gits.execute(1.2, 21, 1.0).args[0]
    assert len(gits_interpolated) == 22
    assert bool(torch.all(gits_interpolated[:-2] > gits_interpolated[1:-1]))
    assert gits.execute(1.2, 10, 0.0).args[0].numel() == 0
    assert gits.execute(1.2, 10, 0.01).args[0].tolist() == [0.0]
    try:
        gits.execute(1.23, 10, 1.0)
    except KeyError as error:
        assert error.args == (1.23,)
    else:
        raise AssertionError("GITSScheduler must reject a coefficient missing from NOISE_LEVELS")

    flux_native = optimal.execute("FLUX", 10, 1.0).args[0]
    wan_native = optimal.execute("Wan", 20, 1.0).args[0]
    chroma_native = optimal.execute("Chroma", 40, 1.0).args[0]
    assert (len(flux_native), len(wan_native), len(chroma_native)) == (11, 21, 41)
    torch.testing.assert_close(wan_native[:2], torch.tensor([1.0, 0.997]))
    assert float(wan_native[-1]) == 0.0
    flux_default = optimal.execute("FLUX", 20, 1.0).args[0]
    assert len(flux_default) == 21
    torch.testing.assert_close(flux_default[::2], flux_native)
    assert bool(torch.all(flux_default[:-2] > flux_default[1:-1]))
    assert len(optimal.execute("Wan", 20, 0.5).args[0]) == 11
    assert optimal.execute("Wan", 20, 0.0).args[0].numel() == 0
    assert optimal.execute("Wan", 20, 0.01).args[0].tolist() == [0.0]

    return {
        "sdTurbo": {
            "full": turbo_full.tolist(),
            "denoise099": turbo_quantized.tolist(),
            "denoise05Length": len(turbo_truncated),
            "denoise0": turbo_zero.tolist(),
        },
        "ays": {
            "nativeLength": len(ays_native),
            "halfLength": len(ays_half),
            "interpolatedLength": len(ays_interpolated),
        },
        "gits": {
            "nativeLength": len(gits_native),
            "interpolatedLength": len(gits_interpolated),
            "missingCoeffRejected": True,
        },
        "optimal": {
            "nativeLengths": [len(flux_native), len(wan_native), len(chroma_native)],
            "fluxDefaultLength": len(flux_default),
        },
    }


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".comfyui-source-0.32.0")
    print(json.dumps(run_probe(root), ensure_ascii=False, sort_keys=True))
