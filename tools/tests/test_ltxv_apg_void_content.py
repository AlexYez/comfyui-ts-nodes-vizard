from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


ARTICLE_SPECS = {
    "core.ltxv-latent-upsampler": {
        "directory": "ltxv-latent-upsampler",
        "classType": "LTXVLatentUpsampler",
        "module": "comfy_extras.nodes_lt_upsampler",
        "fingerprint": "sha256:bffddacf566625e966b72241079a3eebde82dcb1e5be707f736a4c713bd74b48",
        "recipe": "recipe.ltxv-latent-upscale-2x",
    },
    "core.minimax-h3-sigma-shift": {
        "directory": "minimax-h3-sigma-shift",
        "classType": "MiniMaxH3SigmaShift",
        "module": "comfy_extras.nodes_minimax_h3",
        "fingerprint": "sha256:25fc0535f0b075c09d0bedfc70856ffd7ac46f9c71f5dcd7bfbb04868983cec0",
        "recipe": "recipe.minimax-h3-default-sigma-shifts",
    },
    "core.apg": {
        "directory": "apg",
        "classType": "APG",
        "module": "comfy_extras.nodes_apg",
        "fingerprint": "sha256:3d083411a43984456846f83f333087dce0ce01bc0264758d21b81e312a9f42ee",
        "recipe": "recipe.apg-controlled-baseline",
    },
    "core.void-sampler": {
        "directory": "void-sampler",
        "classType": "VOIDSampler",
        "module": "comfy_extras.nodes_void",
        "fingerprint": "sha256:53195b08cfc641e1998462fcd643188458853053218f8fa4ac790ae8af0aa1d3",
        "recipe": "recipe.void-custom-advanced-sampler",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.ltxv-latent-upscale-2x": "ltxv-latent-upscale-2x",
    "recipe.minimax-h3-default-sigma-shifts": "minimax-h3-default-sigma-shifts",
    "recipe.apg-controlled-baseline": "apg-controlled-baseline",
    "recipe.void-custom-advanced-sampler": "void-custom-advanced-sampler",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.ltxv-latent-upscale-2x": [
        (
            "LatentUpscaleModelLoader",
            {"model_name": "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"},
        ),
        ("LTXVLatentUpsampler", {}),
    ],
    "recipe.minimax-h3-default-sigma-shifts": [
        ("MiniMaxH3SigmaShift", {"shift_video": 12.0, "shift_audio": 3.0}),
    ],
    "recipe.apg-controlled-baseline": [
        ("APG", {"eta": 1.0, "norm_threshold": 5.0, "momentum": 0.0}),
    ],
    "recipe.void-custom-advanced-sampler": [
        ("VOIDSampler", {}),
        ("SamplerCustomAdvanced", {}),
    ],
}

EXPECTED_HEADINGS = [
    "Что делает нода",
    "Когда использовать и когда не использовать",
    "Короткий рецепт подключения",
    "Входы, выходы и параметры",
    "Типовые связки",
    "Практический пример",
    "Частые ошибки и способы проверки",
    "Производительность и внутреннее поведение",
    "Совместимость, изменения и устаревание",
    "Связанные ноды и источники",
]

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
SYNTHETIC_PROBE = Path(__file__).with_name("ltxv_apg_void_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def runtime_inputs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def normalized_links(graph: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            result.append(
                {
                    "origin_id": link[1],
                    "origin_slot": link[2],
                    "target_id": link[3],
                    "target_slot": link[4],
                    "type": link[5],
                }
            )
        elif isinstance(link, dict):
            result.append(link)
    return result


def workflow_graphs(payload: dict[str, Any], scope: str = "root") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield scope, payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, subgraph in enumerate(subgraphs):
        if isinstance(subgraph, dict):
            yield from workflow_graphs(subgraph, f"{scope}/subgraph:{index}")


class LtxvApgVoidContentTests(unittest.TestCase):
    def test_articles_fragment_only_recipes_and_research_validate(self) -> None:
        article_ids = all_article_ids()
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        errors: list[str] = []
        cliche_pattern = re.compile(
            r"без воды|коротко о главном|понятно и доступно|по-честному|"
            r"идеальн|революционн|уникальная возможность|в современном мире|"
            r"давайте разбер|важно отметить|стоит подчеркнуть|подводя итог|"
            r"данная нода|является незаменим|устали от|знакомо\?|успейте",
            re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            relations = article["relations"]
            targets = relations["related"] + relations["alternatives"]
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(EXPECTED_HEADINGS, re.findall(r"^## (.+)$", body, re.MULTILINE))
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliche_pattern)

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual(spec["module"], research["node"]["pythonModule"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertTrue(any("человеческ" in gap.lower() for gap in research["knownGaps"]))

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            self.assertEqual("draft", recipe["editorial"]["state"])
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliche_pattern)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )
        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_widgets_and_fragment_ports(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        expected_categories = {
            "LTXVLatentUpsampler": "model/latent/ltxv",
            "MiniMaxH3SigmaShift": "model/patch/minimax",
            "APG": "model/sampling/custom",
            "VOIDSampler": "model/sampling/samplers",
        }
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = dict(nodes[spec["classType"]])
            article = catalog.load_json(article_path(spec))
            self.assertEqual(spec["module"], runtime["python_module"])
            self.assertEqual(expected_categories[spec["classType"]], runtime["category"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("dev_only", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime["is_input_list"])

        ltx = nodes["LTXVLatentUpsampler"]
        self.assertTrue(ltx["experimental"])
        self.assertEqual(["samples", "upscale_model", "vae"], ltx["input_order"]["required"])
        self.assertEqual({"samples": ["LATENT", {}], "upscale_model": ["LATENT_UPSCALE_MODEL", {}], "vae": ["VAE", {}]}, ltx["input"]["required"])
        self.assertEqual(["LATENT"], ltx["output"])

        minimax = nodes["MiniMaxH3SigmaShift"]
        self.assertFalse(minimax["experimental"])
        self.assertEqual("ModelSamplingMiniMaxH3", minimax["display_name"])
        self.assertEqual(["sigma shift", "minimax shift"], minimax["search_aliases"])
        self.assertEqual(
            {"default": 12.0, "min": 0.01, "max": 100.0, "step": 0.01},
            minimax["input"]["required"]["shift_video"][1],
        )
        self.assertEqual(
            {"default": 3.0, "min": 0.01, "max": 100.0, "step": 0.01},
            minimax["input"]["required"]["shift_audio"][1],
        )

        apg = nodes["APG"]
        self.assertFalse(apg["experimental"])
        self.assertEqual("Adaptive Projected Guidance", apg["display_name"])
        self.assertEqual(
            {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01, "advanced": True, "tooltip": "Controls the scale of the parallel guidance vector. Default CFG behavior at a setting of 1."},
            apg["input"]["required"]["eta"][1],
        )
        self.assertEqual(5.0, apg["input"]["required"]["norm_threshold"][1]["default"])
        self.assertEqual(-5.0, apg["input"]["required"]["momentum"][1]["min"])

        void = nodes["VOIDSampler"]
        self.assertFalse(void["experimental"])
        self.assertEqual({}, void["input"]["required"])
        self.assertEqual(["SAMPLER"], void["output"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            refs = {node["ref"]: node for node in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                runtime = dict(nodes[refs[external["to"]]["classType"]])
                self.assertEqual(external["type"], runtime_inputs(runtime)[external["input"]][0])
            for node in fragment["nodes"]:
                inputs = runtime_inputs(dict(nodes[node["classType"]]))
                for name, value in node["settings"].items():
                    self.assertIn(name, inputs)
                    options = inputs[name][1]
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        self.assertGreaterEqual(value, options.get("min", value))
                        self.assertLessEqual(value, options.get("max", value))
            for connection in fragment["connections"]:
                source = dict(nodes[refs[connection["from"]]["classType"]])
                target = dict(nodes[refs[connection["to"]]["classType"]])
                output_index = source["output_name"].index(connection["output"])
                self.assertEqual(source["output"][output_index], runtime_inputs(target)[connection["input"]][0])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_contracts_math_and_replacement_absence(self) -> None:
        ltx_node = (SOURCE / "comfy_extras" / "nodes_lt_upsampler.py").read_text(encoding="utf-8")
        ltx_model = (SOURCE / "comfy" / "ldm" / "lightricks" / "latent_upsampler.py").read_text(encoding="utf-8")
        minimax_node = (SOURCE / "comfy_extras" / "nodes_minimax_h3.py").read_text(encoding="utf-8")
        sampling = (SOURCE / "comfy" / "model_sampling.py").read_text(encoding="utf-8")
        minimax_model = (SOURCE / "comfy" / "ldm" / "minimax" / "model.py").read_text(encoding="utf-8")
        apg = (SOURCE / "comfy_extras" / "nodes_apg.py").read_text(encoding="utf-8")
        samplers = (SOURCE / "comfy" / "samplers.py").read_text(encoding="utf-8")
        void = (SOURCE / "comfy_extras" / "nodes_void.py").read_text(encoding="utf-8")

        self.assertIn("memory_required = math.prod(latents.shape) * 3000.0", ltx_node)
        self.assertIn("per_channel_statistics.un_normalize(latents)", ltx_node)
        self.assertIn("per_channel_statistics.normalize(", ltx_node)
        self.assertIn('return_dict.pop("noise_mask", None)', ltx_node)
        self.assertIn('"""Upsample latents without tiling."""', ltx_node)
        self.assertIn("PixelShuffleND(2)", ltx_model)
        self.assertIn('x = rearrange(x, "(b f) c h w -> b c f h w", b=b, f=f)', ltx_model)

        self.assertIn("class ModelSamplingAdvanced(comfy.model_sampling.ModelSamplingAV, comfy.model_sampling.CONST)", minimax_node)
        self.assertIn("model_sampling.set_parameters(shift=shift_video, audio_shift=shift_audio)", minimax_node)
        self.assertIn("model_sampling.set_noise_scale(original.noise_scale)", minimax_node)
        self.assertIn('to["minimax_h3_sigma_shift_video"] = shift_video', minimax_node)
        self.assertIn("return self.shift / self.audio_shift", sampling)
        self.assertIn("return alpha * t / (1 + (alpha - 1) * t)", sampling)
        self.assertIn("base = sigma / (from_shift + sigma * (1.0 - from_shift))", minimax_model)
        self.assertIn("sigma_a = time_shift_sigma(sigma_v, shift_v, shift_a)", minimax_model)

        self.assertIn("guidance_norm = guidance.norm(p=2, dim=[-1, -2, -3], keepdim=True)", apg)
        self.assertIn("running_avg = momentum * running_avg + guidance", apg)
        self.assertIn("modified_guidance = guidance_orthogonal + eta * guidance_parallel", apg)
        self.assertIn("modified_cond = (uncond + modified_guidance) + (cond - uncond) / cond_scale", apg)
        self.assertIn("cfg_result = uncond_pred + (cond_pred - uncond_pred) * cond_scale", samplers)

        self.assertIn("x = noise.to(torch.float32)", void)
        self.assertIn("alpha_t = 1.0 / (1.0 + sigma ** 2)", void)
        self.assertIn("pred_eps = (x - (alpha_t ** 0.5) * denoised) / (1.0 - alpha_t) ** 0.5", void)
        self.assertIn("if sigma_next == 0:", void)
        self.assertIn("x = denoised", void)

        replacements_text = json.dumps(catalog.load_json(REPLACEMENTS), sort_keys=True)
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements_text)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_pinned_embedded_docs_presence_absence_and_limits(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        members = {
            "comfyui_embedded_docs/docs/LTXVLatentUpsampler/en.md": "spatial resolution of a video latent representation by a factor of two",
            "comfyui_embedded_docs/docs/LTXVLatentUpsampler/ru.md": "noise_mask",
            "comfyui_embedded_docs/docs/APG/en.md": "Default CFG behavior at a setting of 1",
            "comfyui_embedded_docs/docs/APG/ru.md": "скользящим средним",
            "comfyui_embedded_docs/docs/VOIDSampler/en.md": "without the noise scaling",
            "comfyui_embedded_docs/docs/VOIDSampler/ru.md": "RandomNoise или VOIDWarpedNoiseSource",
        }
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            names = set(archive.namelist())
            for member, marker in members.items():
                self.assertIn(marker.lower(), archive.read(member).decode("utf-8").lower())
            self.assertFalse(any("/docs/MiniMaxH3SigmaShift/" in name for name in names))

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_root_and_recursive_subgraph_census(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        records: list[dict[str, Any]] = []
        file_count = 0
        root_graph_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in sorted(archive.namelist()):
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                file_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_graph_count += 1
                for scope, graph in workflow_graphs(payload):
                    graph_nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
                    by_id = {node.get("id"): node for node in graph_nodes}
                    links = normalized_links(graph)
                    for node in graph_nodes:
                        if node.get("type") in targets:
                            records.append(
                                {
                                    "member": member,
                                    "scope": scope,
                                    "node": node,
                                    "by_id": by_id,
                                    "links": links,
                                }
                            )
        self.assertEqual(512, file_count)
        self.assertEqual(496, root_graph_count)
        self.assertEqual(Counter({"LTXVLatentUpsampler": 16, "VOIDSampler": 2}), Counter(record["node"]["type"] for record in records))

        ltx = [record for record in records if record["node"]["type"] == "LTXVLatentUpsampler"]
        self.assertEqual(14, len({record["member"] for record in ltx}))
        self.assertTrue(all(record["scope"].startswith("root/subgraph:") for record in ltx))
        self.assertTrue(all(record["node"].get("widgets_values") == [] for record in ltx))
        source_types: list[str] = []
        target_types: list[str] = []
        loader_models: list[str] = []
        for record in ltx:
            node_id = record["node"]["id"]
            incoming = [link for link in record["links"] if link.get("target_id") == node_id]
            outgoing = [link for link in record["links"] if link.get("origin_id") == node_id]
            sample_link = next(link for link in incoming if link["type"] == "LATENT")
            model_link = next(link for link in incoming if link["type"] == "LATENT_UPSCALE_MODEL")
            source_types.append(record["by_id"][sample_link["origin_id"]]["type"])
            loader = record["by_id"][model_link["origin_id"]]
            self.assertEqual("LatentUpscaleModelLoader", loader["type"])
            loader_models.append(loader["widgets_values"][0])
            self.assertEqual(1, len(outgoing))
            target_types.append(record["by_id"][outgoing[0]["target_id"]]["type"])
        self.assertEqual(Counter({"LTXVCropGuides": 8, "LTXVSeparateAVLatent": 8}), Counter(source_types))
        self.assertEqual(Counter({"LTXVImgToVideoInplace": 12, "LTXVConcatAVLatent": 4}), Counter(target_types))
        self.assertEqual(
            Counter(
                {
                    "ltx-2-spatial-upscaler-x2-1.0.safetensors": 9,
                    "ltx-2.3-spatial-upscaler-x2-1.1.safetensors": 5,
                    "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors": 2,
                }
            ),
            Counter(loader_models),
        )

        void = [record for record in records if record["node"]["type"] == "VOIDSampler"]
        self.assertEqual(1, len({record["member"] for record in void}))
        self.assertTrue(all(record["member"].endswith("utility_void_video_inpainting.json") for record in void))
        self.assertEqual({"root/subgraph:1"}, {record["scope"] for record in void})
        downstream_inputs: list[Counter[str]] = []
        for record in void:
            node_id = record["node"]["id"]
            outgoing = [link for link in record["links"] if link.get("origin_id") == node_id]
            self.assertEqual(1, len(outgoing))
            sampler_id = outgoing[0]["target_id"]
            self.assertEqual("SamplerCustomAdvanced", record["by_id"][sampler_id]["type"])
            incoming = [link for link in record["links"] if link.get("target_id") == sampler_id]
            downstream_inputs.append(Counter(record["by_id"][link["origin_id"]]["type"] for link in incoming))
        self.assertIn(Counter({"RandomNoise": 1, "CFGGuider": 1, "VOIDSampler": 1, "BasicScheduler": 1, "VOIDInpaintConditioning": 1}), downstream_inputs)
        self.assertIn(Counter({"VOIDWarpedNoiseSource": 1, "CFGGuider": 1, "VOIDSampler": 1, "BasicScheduler": 1, "VOIDInpaintConditioning": 1}), downstream_inputs)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_model_free_probe(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for exact-source probe")
        result = subprocess.run(
            [str(python), "-X", "utf8", str(SYNTHETIC_PROBE)],
            cwd=catalog.ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0 and python == Path(sys.executable):
            self.skipTest(f"torch or einops unavailable for probe: {result.stderr}")
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        ltx = payload["ltxvLatentUpsampler"]
        self.assertEqual([2, 3, 4, 5, 6], ltx["inputShape"])
        self.assertEqual([2, 3, 4, 10, 12], ltx["outputShape"])
        self.assertEqual([1, 1, 2, 6, 8], ltx["exactModelSyntheticShape"])
        self.assertEqual("torch.float32", ltx["outputDtype"])
        self.assertEqual("torch.float64", ltx["modelInputDtype"])
        self.assertEqual(2_160_000.0, ltx["memoryRequired"])
        self.assertTrue(ltx["noiseMaskRemovedFromCopyOnly"])
        self.assertTrue(ltx["metadataIdentityPreserved"])

        minimax = payload["miniMaxH3SigmaShift"]
        self.assertEqual(12.0, minimax["shiftVideo"])
        self.assertEqual(3.0, minimax["shiftAudio"])
        self.assertEqual(4.0, minimax["audioScale"])
        self.assertEqual(2.5, minimax["noiseScalePreserved"])
        self.assertTrue(minimax["audioMappingMatches"])
        self.assertTrue(minimax["equalShiftsAreIdentity"])
        self.assertTrue(minimax["originalTransformerOptionsUnchanged"])

        apg = payload["apg"]
        self.assertEqual(apg["etaOneNoModifiersExpectedCondPlusCfgGuidance"], apg["etaOneNoModifiersStandardCfg"])
        self.assertNotEqual(apg["ordinaryCfgWouldBe"], apg["etaOneNoModifiersStandardCfg"])
        self.assertTrue(apg["singleConditionBypassed"])
        self.assertEqual([1.5, 2.5, 3.0], apg["reverseMomentumFirstSecondReset"])
        self.assertFalse(apg["cfgZeroIsFinite"])
        self.assertTrue(apg["projectionReconstructs"])

        void = payload["voidSampler"]
        self.assertEqual("torch.float32", void["dtype"])
        self.assertEqual([[0, 3], [1, 3], [2, 3]], void["callbackRecords"])
        self.assertTrue(void["matchesManualAlphaUpdate"])
        self.assertTrue(void["oneSigmaSkipsModel"])
        self.assertTrue(void["terminalZeroReturnsDenoised"])
        self.assertTrue(void["latentAndMaskAcceptedButUnused"])


if __name__ == "__main__":
    unittest.main()
