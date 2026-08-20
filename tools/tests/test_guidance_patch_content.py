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
    "core.perturbed-attention-guidance": {
        "directory": "perturbed-attention-guidance",
        "classType": "PerturbedAttentionGuidance",
        "module": "comfy_extras.nodes_pag",
        "category": "model/patch/unet",
        "experimental": False,
        "fingerprint": "sha256:f85ae8523a8f9542f5e5dc3245c43666f2b9e0fbcf90aff05f262e4721ed7449",
        "recipe": "recipe.perturbed-attention-guidance-source-default",
    },
    "core.self-attention-guidance": {
        "directory": "self-attention-guidance",
        "classType": "SelfAttentionGuidance",
        "module": "comfy_extras.nodes_sag",
        "category": "experimental",
        "experimental": True,
        "fingerprint": "sha256:bb7fb09c9b42386421082af1ea32053396f76ce0091510e3d256d7e0956b89d8",
        "recipe": "recipe.self-attention-guidance-source-default",
    },
    "core.nag-guidance": {
        "directory": "nag-guidance",
        "classType": "NAGuidance",
        "module": "comfy_extras.nodes_nag",
        "category": "advanced/guidance",
        "experimental": True,
        "fingerprint": "sha256:c1e17b94ef810c9ce482c02fc2e5931fd3702abe9a284a09d89ee9513e5ddbc7",
        "recipe": "recipe.nag-guidance-source-default",
    },
    "core.epsilon-scaling": {
        "directory": "epsilon-scaling",
        "classType": "Epsilon Scaling",
        "module": "comfy_extras.nodes_eps",
        "category": "model/patch/unet",
        "experimental": False,
        "fingerprint": "sha256:4a524e167c6909d78331765f9fadd7c49a1621ba2c195b0a22447fc2fd0f4e3d",
        "recipe": "recipe.epsilon-scaling-source-default",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.perturbed-attention-guidance-source-default": "perturbed-attention-guidance-source-default",
    "recipe.self-attention-guidance-source-default": "self-attention-guidance-source-default",
    "recipe.nag-guidance-source-default": "nag-guidance-source-default",
    "recipe.epsilon-scaling-source-default": "epsilon-scaling-source-default",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.perturbed-attention-guidance-source-default": [
        ("PerturbedAttentionGuidance", {"scale": 3.0})
    ],
    "recipe.self-attention-guidance-source-default": [
        ("SelfAttentionGuidance", {"scale": 0.5, "blur_sigma": 2.0})
    ],
    "recipe.nag-guidance-source-default": [
        ("NAGuidance", {"nag_scale": 5.0, "nag_alpha": 0.5, "nag_tau": 1.5})
    ],
    "recipe.epsilon-scaling-source-default": [
        ("Epsilon Scaling", {"scaling_factor": 1.005})
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
SYNTHETIC_PROBE = Path(__file__).with_name("guidance_patch_synthetic_probe.py")


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


def workflow_graphs(payload: dict[str, Any], scope: str = "root") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield scope, payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, subgraph in enumerate(subgraphs):
        if isinstance(subgraph, dict):
            yield from workflow_graphs(subgraph, f"{scope}/subgraph:{index}")


class GuidancePatchContentTests(unittest.TestCase):
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
            self.assertEqual(spec["experimental"], article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            relation_targets = article["relations"]["related"] + article["relations"]["alternatives"]
            if article["relations"]["replacedBy"] is not None:
                relation_targets.append(article["relations"]["replacedBy"])
            self.assertTrue(set(relation_targets).issubset(article_ids))

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
            self.assertTrue(research["checks"]["russianEdited"])
            self.assertTrue(research["checks"]["factsRecheckedAfterEditing"])
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
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = dict(nodes[spec["classType"]])
            article = catalog.load_json(article_path(spec))
            self.assertEqual(spec["module"], runtime["python_module"])
            self.assertEqual(spec["category"], runtime["category"])
            self.assertEqual(spec["experimental"], runtime["experimental"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertFalse(runtime["deprecated"])
            self.assertFalse(runtime["dev_only"])
            self.assertFalse(runtime["api_node"])
            self.assertFalse(runtime["is_input_list"])
            self.assertEqual(["MODEL"], runtime["output"])
            self.assertIsNone(runtime["search_aliases"])

        pag = nodes["PerturbedAttentionGuidance"]
        self.assertIsNone(pag["display_name"])
        self.assertEqual(["model", "scale"], pag["input_order"]["required"])
        self.assertEqual(
            {"default": 3.0, "min": 0.0, "max": 100.0, "step": 0.01, "round": 0.01},
            pag["input"]["required"]["scale"][1],
        )

        sag = nodes["SelfAttentionGuidance"]
        self.assertEqual("Self-Attention Guidance", sag["display_name"])
        self.assertEqual(["model", "scale", "blur_sigma"], sag["input_order"]["required"])
        self.assertEqual(
            {"default": 0.5, "min": -2.0, "max": 5.0, "step": 0.01},
            sag["input"]["required"]["scale"][1],
        )
        self.assertEqual(
            {"advanced": True, "default": 2.0, "min": 0.0, "max": 10.0, "step": 0.1},
            sag["input"]["required"]["blur_sigma"][1],
        )

        nag = nodes["NAGuidance"]
        self.assertEqual("Normalized Attention Guidance", nag["display_name"])
        self.assertIn("distilled/schnell", nag["description"])
        self.assertEqual(["model", "nag_scale", "nag_alpha", "nag_tau"], nag["input_order"]["required"])
        self.assertEqual(5.0, nag["input"]["required"]["nag_scale"][1]["default"])
        self.assertEqual(0.5, nag["input"]["required"]["nag_alpha"][1]["default"])
        self.assertEqual(1.5, nag["input"]["required"]["nag_tau"][1]["default"])

        epsilon = nodes["Epsilon Scaling"]
        self.assertIsNone(epsilon["display_name"])
        self.assertEqual(["model", "scaling_factor"], epsilon["input_order"]["required"])
        self.assertEqual(
            {
                "advanced": True,
                "default": 1.005,
                "min": 0.5,
                "max": 1.5,
                "step": 0.001,
                "display": "number",
            },
            epsilon["input"]["required"]["scaling_factor"][1],
        )

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
                    self.assertGreaterEqual(value, options["min"])
                    self.assertLessEqual(value, options["max"])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_contracts_and_replacement_absence(self) -> None:
        pag = (SOURCE / "comfy_extras" / "nodes_pag.py").read_text(encoding="utf-8")
        sag = (SOURCE / "comfy_extras" / "nodes_sag.py").read_text(encoding="utf-8")
        nag = (SOURCE / "comfy_extras" / "nodes_nag.py").read_text(encoding="utf-8")
        epsilon = (SOURCE / "comfy_extras" / "nodes_eps.py").read_text(encoding="utf-8")
        attention = (SOURCE / "comfy" / "ldm" / "modules" / "attention.py").read_text(encoding="utf-8")

        self.assertIn('return v', pag)
        self.assertIn('set_model_options_patch_replace(model_options, perturbed_attention, "attn1", unet_block, unet_block_id)', pag)
        self.assertIn('if scale == 0:', pag)
        self.assertIn('return cfg_result + (cond_pred - pag) * scale', pag)
        self.assertIn('n = self.attn1.to_out(n)', attention)

        self.assertIn('mask = attn.mean(1, keepdim=False).sum(1, keepdim=False) > threshold', sag)
        self.assertIn('gaussian_blur_2d(x0, kernel_size=9, sigma=sigma)', sag)
        self.assertIn('# TODO: make this work properly with chunked batches', sag)
        self.assertIn('if min(cfg_result.shape[2:]) <= 4:', sag)
        self.assertIn('return cfg_result + (degraded - sag) * sag_scale', sag)
        self.assertIn('disable_cfg1_optimization=True', sag)

        self.assertIn('guided = z_pos * nag_scale - z_neg * (nag_scale - 1.0)', nag)
        self.assertIn('torch.norm(z_pos, p=1, dim=-1, keepdim=True).clamp_min(eps)', nag)
        self.assertIn('scale_factor = torch.minimum(ratio, torch.full_like(ratio, nag_tau)) / ratio', nag)
        self.assertIn('orig_out[half_size * ind_neg:half_size * (ind_neg + 1), img_slice[0]:img_slice[1]] = z_final', nag)
        self.assertIn('m.disable_model_cfg1_optimization()', nag)

        self.assertIn('node_id="Epsilon Scaling"', epsilon)
        self.assertIn('scaled_noise_pred = noise_pred / scaling_factor', epsilon)
        self.assertIn('new_denoised = x - scaled_noise_pred', epsilon)
        self.assertIn('if scaling_factor == 0:', epsilon)

        replacements_text = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False, sort_keys=True)
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements_text)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_pinned_embedded_docs_exact_routes_and_limits(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        members = {
            "comfyui_embedded_docs/docs/PerturbedAttentionGuidance/en.md": "value projections",
            "comfyui_embedded_docs/docs/PerturbedAttentionGuidance/ru.md": "масштаб",
            "comfyui_embedded_docs/docs/SelfAttentionGuidance/en.md": "limitations with chunked batches",
            "comfyui_embedded_docs/docs/SelfAttentionGuidance/ru.md": "сигма_размытия",
            "comfyui_embedded_docs/docs/NAGuidance/en.md": "distilled or schnell models",
            "comfyui_embedded_docs/docs/NAGuidance/ru.md": "nag_tau",
            "comfyui_embedded_docs/docs/Epsilon Scaling/en.md": "uniform schedule",
            "comfyui_embedded_docs/docs/Epsilon Scaling/ru.md": "коэффициент_масштабирования",
            "comfyui_embedded_docs/docs/EpsilonScaling/en.md": "EpsilonScaling",
        }
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for member, marker in members.items():
                self.assertIn(marker.lower(), archive.read(member).decode("utf-8").lower())

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_root_and_recursive_subgraph_census_is_zero(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts: Counter[str] = Counter()
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
                for _scope, graph in workflow_graphs(payload):
                    for node in graph.get("nodes", []):
                        if isinstance(node, dict) and node.get("type") in targets:
                            counts[node["type"]] += 1
        self.assertEqual(512, file_count)
        self.assertEqual(496, root_graph_count)
        self.assertEqual(Counter(), counts)

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

        pag = payload["perturbedAttentionGuidance"]
        self.assertEqual(pag["expected"], pag["result"])
        self.assertEqual(["attn1", "middle", 0], pag["patchKey"])
        self.assertTrue(pag["returnsProjectedVByIdentity"])
        self.assertTrue(pag["scaleZeroBypassesExtraCall"])

        sag = payload["selfAttentionGuidance"]
        self.assertEqual(["middle", 0, 0], sag["patchKey"])
        self.assertTrue(sag["cfg1OptimizationDisabled"])
        self.assertTrue(sag["scaleZeroStillRunsExtraUnconditionalCall"])
        self.assertTrue(sag["smallSpatialDimensionSkips"])
        self.assertTrue(sag["sigmaTwoFinite"])
        self.assertFalse(sag["sigmaZeroFinite"])
        self.assertTrue(sag["unselectedCornerPreserved"])

        nag = payload["normalizedAttentionGuidance"]
        self.assertTrue(nag["cfg1OptimizationDisabled"])
        self.assertTrue(nag["negativeBranchPreservedWithoutImageSlice"])
        self.assertTrue(nag["ratioWasCapped"])
        self.assertTrue(nag["alphaZeroNoSliceIsIdentity"])
        self.assertTrue(nag["alphaZeroImageSliceCopiesPositiveIntoNegative"])
        self.assertTrue(nag["nonImageTokensPreserved"])

        epsilon = payload["epsilonScaling"]
        self.assertTrue(epsilon["factorOneIsIdentity"])
        self.assertEqual([[[[1.5999999046325684, 1.2000000476837158]]]], epsilon["factorAboveOne"])
        self.assertEqual([[[[-2.0, 6.0]]]], epsilon["factorBelowOne"])
        self.assertTrue(epsilon["directZeroGuardFinite"])
        self.assertTrue(epsilon["allStepsUniformFormulaHasNoSigmaInput"])


if __name__ == "__main__":
    unittest.main()
