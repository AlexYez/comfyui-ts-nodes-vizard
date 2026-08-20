from __future__ import annotations

import ast
import json
import math
import sys
import types
from pathlib import Path


def compile_named(path: Path, names: set[str]):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    body = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name in names
    ]
    return compile(ast.Module(body=body, type_ignores=[]), str(path), "exec")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: latent_arithmetic_synthetic_probe.py <pinned-comfyui-source>")

    source = Path(sys.argv[1]).resolve()
    import torch

    utils_namespace = {"torch": torch, "math": math}
    exec(
        compile_named(
            source / "comfy" / "utils.py",
            {"repeat_to_batch_size", "common_upscale"},
        ),
        utils_namespace,
    )
    comfy = types.SimpleNamespace(
        utils=types.SimpleNamespace(
            repeat_to_batch_size=utils_namespace["repeat_to_batch_size"],
            common_upscale=utils_namespace["common_upscale"],
        )
    )

    class DummyIo:
        class ComfyNode:
            pass

        @staticmethod
        def NodeOutput(*args):
            return types.SimpleNamespace(args=args)

    latent_namespace = {"torch": torch, "comfy": comfy, "io": DummyIo}
    exec(
        compile_named(
            source / "comfy_extras" / "nodes_latent.py",
            {
                "reshape_latent_to",
                "LatentAdd",
                "LatentSubtract",
                "LatentMultiply",
                "LatentInterpolate",
            },
        ),
        latent_namespace,
    )

    marker = {"identity": "samples1"}
    noise_mask = torch.tensor([[[0.0, 1.0], [1.0, 0.0]]])
    batch_index = [7, 8, 9]
    s1 = torch.arange(3 * 4 * 2 * 2, dtype=torch.float32).reshape(3, 4, 2, 2)
    s2 = torch.stack(
        [torch.full((4, 3, 4), 10.0), torch.full((4, 3, 4), 20.0)]
    )
    first = {
        "samples": s1,
        "noise_mask": noise_mask,
        "batch_index": batch_index,
        "custom": marker,
    }
    second = {
        "samples": s2,
        "noise_mask": torch.ones((2, 3, 4)),
        "batch_index": [90, 91],
        "second_only": True,
    }

    add = latent_namespace["LatentAdd"].execute(first, second).args[0]
    subtract = latent_namespace["LatentSubtract"].execute(first, second).args[0]
    assert tuple(add["samples"].shape) == (3, 4, 2, 2)
    assert tuple(subtract["samples"].shape) == (3, 4, 2, 2)
    assert add["samples"][:, 0, 0, 0].tolist() == [10.0, 36.0, 42.0]
    assert subtract["samples"][:, 0, 0, 0].tolist() == [-10.0, -4.0, 22.0]
    for output in (add, subtract):
        assert output["noise_mask"] is noise_mask
        assert output["batch_index"] is batch_index
        assert output["custom"] is marker
        assert "second_only" not in output

    multiply = latent_namespace["LatentMultiply"].execute(first, -2.0).args[0]
    assert multiply["samples"][0, 0, 0, :].tolist() == [-0.0, -2.0]
    assert multiply["noise_mask"] is noise_mask
    assert multiply["batch_index"] is batch_index
    assert multiply["custom"] is marker

    x = {
        "samples": torch.tensor([[[[3.0]], [[0.0]]]]),
        "noise_mask": noise_mask,
        "custom": marker,
    }
    y = {
        "samples": torch.tensor([[[[0.0]], [[4.0]]]]),
        "second_only": True,
    }
    interpolate = latent_namespace["LatentInterpolate"]
    endpoint_zero = interpolate.execute(x, y, 0.0).args[0]
    endpoint_one = interpolate.execute(x, y, 1.0).args[0]
    midpoint = interpolate.execute(x, y, 0.5).args[0]
    assert torch.allclose(endpoint_zero["samples"], y["samples"])
    assert torch.allclose(endpoint_one["samples"], x["samples"])
    assert torch.allclose(
        midpoint["samples"].flatten(),
        torch.tensor([3.5 / math.sqrt(2.0), 3.5 / math.sqrt(2.0)]),
    )
    assert midpoint["noise_mask"] is noise_mask
    assert midpoint["custom"] is marker
    assert "second_only" not in midpoint

    opposite = {"samples": torch.tensor([[[[-3.0]], [[0.0]]]])}
    cancelled = interpolate.execute(x, opposite, 0.5).args[0]
    assert torch.count_nonzero(cancelled["samples"]).item() == 0

    batch_two = {"samples": torch.ones((2, 4, 2, 2))}
    batch_two_error = None
    try:
        interpolate.execute(batch_two, batch_two, 0.5)
    except RuntimeError as exc:
        batch_two_error = str(exc)
    assert batch_two_error is not None

    batch_four = {
        "samples": torch.arange(1, 1 + 4 * 4 * 2 * 2, dtype=torch.float32).reshape(4, 4, 2, 2)
    }
    batch_four_ratio_one = interpolate.execute(batch_four, batch_four, 1.0).args[0]
    assert not torch.allclose(batch_four_ratio_one["samples"], batch_four["samples"])

    broadcast_first = {"samples": torch.ones((2, 4, 2, 2))}
    broadcast_second = {"samples": torch.ones((1, 1, 2, 2))}
    broadcast_add = latent_namespace["LatentAdd"].execute(
        broadcast_first, broadcast_second
    ).args[0]
    assert tuple(broadcast_add["samples"].shape) == (2, 4, 2, 2)

    print(
        json.dumps(
            {
                "add": {
                    "shape": list(add["samples"].shape),
                    "firstChannelOrigin": add["samples"][:, 0, 0, 0].tolist(),
                    "metadataFromFirst": add["custom"] is marker,
                },
                "subtract": {
                    "shape": list(subtract["samples"].shape),
                    "firstChannelOrigin": subtract["samples"][:, 0, 0, 0].tolist(),
                    "metadataFromFirst": subtract["custom"] is marker,
                },
                "multiply": {
                    "shape": list(multiply["samples"].shape),
                    "firstValues": multiply["samples"][0, 0, 0, :].tolist(),
                    "metadataFromInput": multiply["custom"] is marker,
                },
                "interpolate": {
                    "ratioZero": endpoint_zero["samples"].flatten().tolist(),
                    "ratioOne": endpoint_one["samples"].flatten().tolist(),
                    "midpoint": midpoint["samples"].flatten().tolist(),
                    "oppositeMidpointNonzero": int(
                        torch.count_nonzero(cancelled["samples"]).item()
                    ),
                    "batchTwoError": batch_two_error,
                    "batchFourRatioOneIdentity": bool(
                        torch.allclose(
                            batch_four_ratio_one["samples"], batch_four["samples"]
                        )
                    ),
                    "metadataFromFirst": midpoint["custom"] is marker,
                },
                "broadcast": {"channelOneToFourShape": list(broadcast_add["samples"].shape)},
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
