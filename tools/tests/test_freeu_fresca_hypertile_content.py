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
    "core.freeu": {
        "directory": "freeu",
        "classType": "FreeU",
        "module": "comfy_extras.nodes_freelunch",
        "category": "model/patch/unet",
        "experimental": False,
        "fingerprint": "sha256:3f2e124d40c6bf6053244819c1ad398e8c065b82f5c745ad2e534d4ce83622d3",
        "recipe": "recipe.freeu-source-default",
    },
    "core.freeu-v2": {
        "directory": "freeu-v2",
        "classType": "FreeU_V2",
        "module": "comfy_extras.nodes_freelunch",
        "category": "model/patch/unet",
        "experimental": False,
        "fingerprint": "sha256:cd8fc0a275577569fb03675888fc9cfd731354ae0e531465464d7a7a1c603e3f",
        "recipe": "recipe.freeu-v2-source-default",
    },
    "core.fresca": {
        "directory": "fresca",
        "classType": "FreSca",
        "module": "comfy_extras.nodes_fresca",
        "category": "experimental",
        "experimental": True,
        "fingerprint": "sha256:ea6c0e0015db15742fe1c63ad9ec5581686726058e0a801969118cb0bd9aeebe",
        "recipe": "recipe.fresca-source-default",
    },
    "core.hyper-tile": {
        "directory": "hyper-tile",
        "classType": "HyperTile",
        "module": "comfy_extras.nodes_hypertile",
        "category": "model/patch/unet",
        "experimental": False,
        "fingerprint": "sha256:64c805ffbef8405f03f92290dc2801c610fc6f499ddd2c212c7452372abe53b9",
        "recipe": "recipe.hyper-tile-source-default",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.freeu-source-default": "freeu-source-default",
    "recipe.freeu-v2-source-default": "freeu-v2-source-default",
    "recipe.fresca-source-default": "fresca-source-default",
    "recipe.hyper-tile-source-default": "hyper-tile-source-default",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.freeu-source-default": [("FreeU", {"b1": 1.1, "b2": 1.2, "s1": 0.9, "s2": 0.2})],
    "recipe.freeu-v2-source-default": [("FreeU_V2", {"b1": 1.3, "b2": 1.4, "s1": 0.9, "s2": 0.2})],
    "recipe.fresca-source-default": [("FreSca", {"scale_low": 1.0, "scale_high": 1.25, "freq_cutoff": 20})],
    "recipe.hyper-tile-source-default": [("HyperTile", {"tile_size": 256, "swap_size": 2, "max_depth": 0, "scale_depth": False})],
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
SYNTHETIC_PROBE = Path(__file__).with_name("freeu_fresca_hypertile_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    return {
        payload["articleId"]
        for path in (catalog.CONTENT / "articles").rglob("manifest.json")
        if isinstance((payload := catalog.load_json(path)), dict)
        and isinstance(payload.get("articleId"), str)
    }


def runtime_inputs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def workflow_graphs(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if isinstance(subgraph, dict):
            yield from workflow_graphs(subgraph)


class FreeUFrescaHyperTileContentTests(unittest.TestCase):
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
            targets = article["relations"]["related"] + article["relations"]["alternatives"]
            if article["relations"]["replacedBy"] is not None:
                targets.append(article["relations"]["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(EXPECTED_HEADINGS, re.findall(r"^## (.+)$", body, re.MULTILINE))
            self.assertNotIn("�", body)
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
            self.assertNotIn("�", body)
            self.assertNotRegex(body, cliche_pattern)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )
            compiled = catalog.compile_recipe(path, recipe)
            self.assertIn("fragmentData", compiled)
            self.assertNotIn("workflow", compiled)
            self.assertNotIn("workflowData", compiled)
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
            for flag in ("deprecated", "dev_only", "api_node", "is_input_list"):
                self.assertFalse(runtime[flag])
            self.assertEqual(["MODEL"], runtime["output"])

        expected = {
            "FreeU": (["model", "b1", "b2", "s1", "s2"], {"b1": 1.1, "b2": 1.2, "s1": 0.9, "s2": 0.2}),
            "FreeU_V2": (["model", "b1", "b2", "s1", "s2"], {"b1": 1.3, "b2": 1.4, "s1": 0.9, "s2": 0.2}),
            "FreSca": (["model", "scale_low", "scale_high", "freq_cutoff"], {"scale_low": 1.0, "scale_high": 1.25, "freq_cutoff": 20}),
            "HyperTile": (["model", "tile_size", "swap_size", "max_depth", "scale_depth"], {"tile_size": 256, "swap_size": 2, "max_depth": 0, "scale_depth": False}),
        }
        for class_type, (input_order, defaults) in expected.items():
            runtime = dict(nodes[class_type])
            self.assertEqual(input_order, runtime["input_order"]["required"])
            inputs = runtime_inputs(runtime)
            for name, value in defaults.items():
                self.assertEqual(value, inputs[name][1]["default"])
                self.assertTrue(inputs[name][1]["advanced"])

        self.assertEqual("FreSca", nodes["FreSca"]["display_name"])
        self.assertEqual(["frequency guidance"], nodes["FreSca"]["search_aliases"])
        self.assertEqual(10000, nodes["FreSca"]["input"]["required"]["freq_cutoff"][1]["max"])
        self.assertEqual(1, nodes["HyperTile"]["input"]["required"]["tile_size"][1]["min"])
        self.assertEqual(128, nodes["HyperTile"]["input"]["required"]["swap_size"][1]["max"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            refs = {node["ref"]: node for node in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                runtime = dict(nodes[refs[external["to"]]["classType"]])
                self.assertEqual(external["type"], runtime_inputs(runtime)[external["input"]][0])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_contracts_patch_order_and_replacement_absence(self) -> None:
        freeu = (SOURCE / "comfy_extras" / "nodes_freelunch.py").read_text(encoding="utf-8")
        fresca = (SOURCE / "comfy_extras" / "nodes_fresca.py").read_text(encoding="utf-8")
        hypertile = (SOURCE / "comfy_extras" / "nodes_hypertile.py").read_text(encoding="utf-8")
        patcher = (SOURCE / "comfy" / "model_patcher.py").read_text(encoding="utf-8")
        openaimodel = (SOURCE / "comfy" / "ldm" / "modules" / "diffusionmodules" / "openaimodel.py").read_text(encoding="utf-8")
        attention = (SOURCE / "comfy" / "ldm" / "modules" / "attention.py").read_text(encoding="utf-8")

        self.assertIn("B, C, H, W = x_freq.shape", freeu)
        self.assertIn("scale_dict = {model_channels * 4: (b1, s1), model_channels * 2: (b2, s2)}", freeu)
        self.assertIn("h[:,:h.shape[1] // 2] = h[:,:h.shape[1] // 2] * scale[0]", freeu)
        self.assertIn("Fourier_filter(hsp, threshold=1, scale=scale[1])", freeu)
        self.assertIn("hidden_mean = h.mean(1).unsqueeze(1)", freeu)
        self.assertIn("(hidden_max - hidden_min).unsqueeze(2).unsqueeze(3)", freeu)
        self.assertIn("((scale[0] - 1 ) * hidden_mean + 1)", freeu)

        self.assertIn('if len(conds_out) <= 1 or None in args["conds"][:2]:', fresca)
        self.assertIn("guidance = cond - uncond", fresca)
        self.assertIn("filtered_cond = filtered_guidance + uncond", fresca)
        self.assertIn("f_c = min(freq_cutoff, cc)", fresca)
        self.assertNotIn("disable_cfg1_optimization=True", fresca)

        self.assertIn("idx = randint(low=0, high=len(ns) - 1", hypertile)
        self.assertIn("latent_tile_size = max(32, tile_size) // 8", hypertile)
        self.assertIn("if model_chans in apply_to:", hypertile)
        self.assertIn('rearrange(q, "b (nh h nw w) c -> (b nh nw) (h w) c"', hypertile)
        self.assertIn("temp = None", hypertile)
        self.assertNotIn("torch.roll", hypertile)
        self.assertNotIn("offset", hypertile.lower())

        self.assertIn('to["patches"][name] = to["patches"].get(name, []) + [patch]', patcher)
        self.assertIn('if "output_block_patch" in transformer_patches:', openaimodel)
        self.assertIn("for p in patch:", openaimodel)
        self.assertIn('if "attn1_patch" in transformer_patches:', attention)
        self.assertIn('if "attn1_output_patch" in transformer_patches:', attention)

        replacements_text = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False, sort_keys=True)
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements_text)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_pinned_embedded_docs_routes(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        members = {
            "comfyui_embedded_docs/docs/FreeU/en.md": "model_channels × 4",
            "comfyui_embedded_docs/docs/FreeU/ru.md": "b1",
            "comfyui_embedded_docs/docs/FreeU_V2/en.md": "frequency-based modifications",
            "comfyui_embedded_docs/docs/FreeU_V2/ru.md": "s2",
            "comfyui_embedded_docs/docs/FreSca/en.md": "frequency indices",
            "comfyui_embedded_docs/docs/FreSca/ru.md": "freq_cutoff",
            "comfyui_embedded_docs/docs/HyperTile/en.md": "max_depth",
            "comfyui_embedded_docs/docs/HyperTile/ru.md": "масштаб_глубины",
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
                for graph in workflow_graphs(payload):
                    for node in graph.get("nodes", []):
                        if isinstance(node, dict) and node.get("type") in targets:
                            counts[node["type"]] += 1
        self.assertEqual(512, file_count)
        self.assertEqual(496, root_graph_count)
        self.assertEqual(Counter(), counts)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_tensor_and_patch_probe(self) -> None:
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

        freeu = payload["freeU"]
        self.assertTrue(freeu["freeuFirstHalfScaled"])
        self.assertTrue(freeu["freeuSecondHalfPreserved"])
        self.assertAlmostEqual(0.9, freeu["constantSkipScaledByS1"], places=3)
        self.assertEqual("torch.float16", freeu["skipDtypePreserved"])
        self.assertTrue(freeu["unmatchedChannelsBypass"])
        self.assertAlmostEqual(1.0, freeu["v2SpatialGainMinMax"][0], places=6)
        self.assertAlmostEqual(1.3, freeu["v2SpatialGainMinMax"][1], places=6)
        self.assertFalse(freeu["v2ConstantHiddenFinite"])
        self.assertTrue(freeu["fiveDimensionalSkipFails"])
        self.assertEqual(2, freeu["stackedPatchCount"])
        self.assertTrue(freeu["freeuThenV2DiffersFromReverse"])

        fresca = payload["freSca"]
        self.assertTrue(fresca["defaultCutoffSaturatesEightByEight"])
        self.assertTrue(fresca["extraConditionPreserved"])
        self.assertTrue(fresca["singleConditionBypassIdentity"])
        self.assertTrue(fresca["missingConditionBypassIdentity"])
        self.assertEqual([2, 4, 3, 8, 10], fresca["fiveDimensionalShape"])
        self.assertTrue(fresca["oversizedCutoffOddShapeLeavesHighFrequencyRim"])
        self.assertEqual(2, fresca["stackedPreCfgPatchCount"])

        hypertile = payload["hyperTile"]
        self.assertEqual([8, 1024, 4], hypertile["batchTwoTiledQueryShape"])
        self.assertEqual([2, 4096, 4], hypertile["restoredShape"])
        self.assertEqual([20, 24, 30], hypertile["swapFourObservedTileCounts"])
        self.assertTrue(hypertile["lastCandidateExcluded"])
        self.assertEqual([2], hypertile["defaultSwapTwoIsDeterministicForSixtyFour"])
        self.assertEqual([[1, 64, 16], [39, 64, 16], [40, 16, 64]], hypertile["tileSizeFloorCases"])
        self.assertEqual([16, 64, 2], hypertile["depthWithoutScaleShape"])
        self.assertEqual([4, 256, 2], hypertile["depthWithScaleShape"])
        self.assertEqual([12, 1024, 2], hypertile["videoPerFrameSpatialAttentionShape"])
        self.assertTrue(hypertile["jointSpatiotemporalAttentionSkipped"])
        self.assertFalse(hypertile["hasRandomSpatialOffset"])


if __name__ == "__main__":
    unittest.main()
