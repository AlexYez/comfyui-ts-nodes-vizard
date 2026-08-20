from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from typing import Any

from tools import catalog


ARTICLE_SPECS: dict[str, dict[str, Any]] = {
    "core.sampler-dpmpp-3m-sde": {
        "directory": "sampler-dpmpp-3m-sde",
        "classType": "SamplerDPMPP_3M_SDE",
        "fingerprint": "sha256:19224bc2e87dbdabe73fc3cc480d7662756d99fddd7365ca1a53d94e23c307f4",
        "recipe": "recipe.dpmpp-3m-sde-custom-sampling",
        "required": {
            "eta": ["FLOAT", {"advanced": True, "default": 1.0, "min": 0.0, "max": 100.0, "step": 0.01, "round": False}],
            "s_noise": ["FLOAT", {"advanced": True, "default": 1.0, "min": 0.0, "max": 100.0, "step": 0.01, "round": False}],
            "noise_device": ["COMBO", {"advanced": True, "multiselect": False, "options": ["gpu", "cpu"]}],
        },
    },
    "core.sampler-dpmpp-2m-sde": {
        "directory": "sampler-dpmpp-2m-sde",
        "classType": "SamplerDPMPP_2M_SDE",
        "fingerprint": "sha256:f33bc719e1df466d5fd9e69f00c06661bbeb95eb1f429210905364567f318943",
        "recipe": "recipe.dpmpp-2m-sde-midpoint-custom-sampling",
        "required": {
            "solver_type": ["COMBO", {"multiselect": False, "options": ["midpoint", "heun"]}],
            "eta": ["FLOAT", {"advanced": True, "default": 1.0, "min": 0.0, "max": 100.0, "step": 0.01, "round": False}],
            "s_noise": ["FLOAT", {"advanced": True, "default": 1.0, "min": 0.0, "max": 100.0, "step": 0.01, "round": False}],
            "noise_device": ["COMBO", {"advanced": True, "multiselect": False, "options": ["gpu", "cpu"]}],
        },
    },
    "core.sampler-dpmpp-sde": {
        "directory": "sampler-dpmpp-sde",
        "classType": "SamplerDPMPP_SDE",
        "fingerprint": "sha256:a20ee287dfcb1fd037a2a7550c23bc1103f6cf085c44ac17a89cb4f593389cfa",
        "recipe": "recipe.dpmpp-sde-custom-sampling",
        "required": {
            "eta": ["FLOAT", {"advanced": True, "default": 1.0, "min": 0.0, "max": 100.0, "step": 0.01, "round": False}],
            "s_noise": ["FLOAT", {"advanced": True, "default": 1.0, "min": 0.0, "max": 100.0, "step": 0.01, "round": False}],
            "r": ["FLOAT", {"advanced": True, "default": 0.5, "min": 0.0, "max": 100.0, "step": 0.01, "round": False}],
            "noise_device": ["COMBO", {"advanced": True, "multiselect": False, "options": ["gpu", "cpu"]}],
        },
    },
    "core.sampler-dpmpp-2s-ancestral": {
        "directory": "sampler-dpmpp-2s-ancestral",
        "classType": "SamplerDPMPP_2S_Ancestral",
        "fingerprint": "sha256:0c1e6e5f5f3c4e0cfb1494d448a6c100ec1f2bfd9b8834124362c007c7122799",
        "recipe": "recipe.dpmpp-2s-ancestral-custom-sampling",
        "required": {
            "eta": ["FLOAT", {"default": 1.0, "min": 0.0, "max": 100.0, "step": 0.01, "round": False}],
            "s_noise": ["FLOAT", {"default": 1.0, "min": 0.0, "max": 100.0, "step": 0.01, "round": False}],
        },
    },
}

RECIPE_DIRECTORIES = {
    "recipe.dpmpp-3m-sde-custom-sampling": "dpmpp-3m-sde-custom-sampling",
    "recipe.dpmpp-2m-sde-midpoint-custom-sampling": "dpmpp-2m-sde-midpoint-custom-sampling",
    "recipe.dpmpp-sde-custom-sampling": "dpmpp-sde-custom-sampling",
    "recipe.dpmpp-2s-ancestral-custom-sampling": "dpmpp-2s-ancestral-custom-sampling",
}

TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}
ALGORITHM_NAMES = {
    "dpmpp_3m_sde",
    "dpmpp_3m_sde_gpu",
    "dpmpp_2m_sde",
    "dpmpp_2m_sde_gpu",
    "dpmpp_2m_sde_heun",
    "dpmpp_2m_sde_heun_gpu",
    "dpmpp_sde",
    "dpmpp_sde_gpu",
    "dpmpp_2s_ancestral",
}
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
INVENTORY_META = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.meta.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("dpmpp_sampler_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    ids: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            ids.add(payload["articleId"])
    return ids


def nested_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from nested_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from nested_strings(item)


class DpmppSamplerContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_ten_sections_and_editorial_state(self) -> None:
        schemas = {
            "article": catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json"),
            "recipe": catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json"),
            "fragment": catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"),
            "research": catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json"),
        }
        article_ids = all_article_ids()
        errors: list[str] = []
        clichés = re.compile(
            r"важно отметить|стоит отметить|следует отметить|в современном мире|"
            r"революционн|является мощн|давайте|глубже погруз|открывает новые|"
            r"может показаться|позволяет вам|подводя итог|в заключение|данная нода|"
            r"не просто .{0,80},? а ",
            flags=re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertFalse(article["experimental"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual("comfy_extras.nodes_custom_sampler", article["runtimeIdentity"]["pythonModule"])
            self.assertIn(spec["recipe"], {asset["id"] for asset in article["assets"]})

            relations = article["relations"]
            targets = set(relations["related"] + relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.add(relations["replacedBy"])
            self.assertTrue(targets.issubset(article_ids), (article_id, targets - article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertIsNone(clichés.search(body), article_id)
            self.assertNotIn("\ufffd", body)
            self.assertIn("512 JSON", body)
            self.assertRegex(body.lower(), r"не найден|отсутств|нет ни одного")

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertEqual(spec["classType"], research["node"]["classType"])
            for check in ("implementationRead", "runtimeCompared", "officialCasesInspected", "exampleSchemaValidated", "russianEdited", "factsRecheckedAfterEditing"):
                self.assertTrue(research["checks"][check], (article_id, check))
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["knownGaps"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual(recipe["fragment"]["id"], fragment["fragmentId"])

        self.assertEqual([], errors)

    def test_exact_runtime_fingerprints_flags_ports_and_fragment_contract(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        meta = catalog.load_json(INVENTORY_META)
        self.assertEqual(SOURCE_COMMIT, meta["source"]["commit"])
        self.assertEqual("0.32.0", meta["source"]["backendVersion"])
        self.assertEqual("/object_info", meta["capture"]["endpoint"])
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)

        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_custom_sampler", runtime["python_module"])
            self.assertEqual("model/sampling/samplers", runtime["category"])
            self.assertEqual(spec["required"], runtime["input"]["required"])
            self.assertEqual(list(spec["required"]), runtime["input_order"]["required"])
            self.assertEqual(["SAMPLER"], runtime["output"])
            self.assertEqual(["SAMPLER"], runtime["output_name"])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertIsNone(runtime["search_aliases"])
            for flag in ("output_node", "deprecated", "experimental", "dev_only", "api_node"):
                self.assertFalse(runtime[flag], (article_id, flag))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertNotIn(spec["classType"], replacements)

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            by_ref = {node["ref"]: node for node in fragment["nodes"]}
            supplied = {ref: set(node["settings"]) for ref, node in by_ref.items()}
            for external in fragment["externalInputs"]:
                supplied[external["to"]].add(external["input"])
                runtime = nodes[by_ref[external["to"]]["classType"]]
                self.assertEqual(external["type"], runtime["input"]["required"][external["input"]][0])
            for connection in fragment["connections"]:
                supplied[connection["to"]].add(connection["input"])
                source_runtime = nodes[by_ref[connection["from"]]["classType"]]
                target_runtime = nodes[by_ref[connection["to"]]["classType"]]
                index = source_runtime["output_name"].index(connection["output"])
                self.assertEqual(source_runtime["output"][index], target_runtime["input"]["required"][connection["input"]][0])
            for ref, node in by_ref.items():
                runtime = nodes[node["classType"]]
                self.assertTrue(set(runtime["input"]["required"]).issubset(supplied[ref]), (recipe_id, ref))
                for name, value in node["settings"].items():
                    descriptor = runtime["input"]["required"][name]
                    if descriptor[0] == "FLOAT":
                        self.assertGreaterEqual(value, descriptor[1]["min"])
                        self.assertLessEqual(value, descriptor[1]["max"])
                    elif descriptor[0] == "COMBO":
                        self.assertIn(value, descriptor[1]["options"])
            if recipe_id == "recipe.dpmpp-sde-custom-sampling":
                self.assertGreater(by_ref["algorithm"]["settings"]["r"], 0)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_dispatch_algorithm_branches_cost_and_r_guard(self) -> None:
        self.assertEqual(SOURCE_COMMIT, (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        node_source = (SOURCE / "comfy_extras" / "nodes_custom_sampler.py").read_text(encoding="utf-8")
        sampling = (SOURCE / "comfy" / "k_diffusion" / "sampling.py").read_text(encoding="utf-8")

        node_sections = {
            "3m": node_source.split("class SamplerDPMPP_3M_SDE", 1)[1].split("class SamplerDPMPP_2M_SDE", 1)[0],
            "2m": node_source.split("class SamplerDPMPP_2M_SDE", 1)[1].split("class SamplerDPMPP_SDE", 1)[0],
            "sde": node_source.split("class SamplerDPMPP_SDE", 1)[1].split("class SamplerDPMPP_2S_Ancestral", 1)[0],
            "2s": node_source.split("class SamplerDPMPP_2S_Ancestral", 1)[1].split("class SamplerEulerAncestral", 1)[0],
        }
        self.assertIn('sampler_name = "dpmpp_3m_sde"', node_sections["3m"])
        self.assertIn('sampler_name = "dpmpp_3m_sde_gpu"', node_sections["3m"])
        self.assertIn('sampler_name = "dpmpp_2m_sde"', node_sections["2m"])
        self.assertIn('"solver_type": solver_type', node_sections["2m"])
        self.assertIn('sampler_name = "dpmpp_sde_gpu"', node_sections["sde"])
        self.assertIn('"r": r', node_sections["sde"])
        self.assertIn('ksampler("dpmpp_2s_ancestral"', node_sections["2s"])
        self.assertNotIn("noise_device", node_sections["2s"])

        two_m = sampling.split("def sample_dpmpp_2m_sde", 1)[1].split("def sample_dpmpp_2m_sde_heun", 1)[0]
        three_m = sampling.split("def sample_dpmpp_3m_sde", 1)[1].split("def sample_dpmpp_3m_sde_gpu", 1)[0]
        plain_sde = sampling.split("def sample_dpmpp_sde", 1)[1].split("def sample_dpmpp_2m", 1)[0]
        two_s = sampling.split("def sample_dpmpp_2s_ancestral", 1)[1].split("def sample_dpmpp_2s_ancestral_RF", 1)[0]
        two_s_rf = sampling.split("def sample_dpmpp_2s_ancestral_RF", 1)[1].split("def sample_dpmpp_sde", 1)[0]

        self.assertIn("solver_type not in {'heun', 'midpoint'}", two_m)
        self.assertIn("if old_denoised is not None", two_m)
        self.assertIn("if solver_type == 'heun'", two_m)
        self.assertIn("elif solver_type == 'midpoint'", two_m)
        self.assertEqual(1, two_m.count("denoised = model("))
        self.assertIn("denoised_1, denoised_2 = None, None", three_m)
        self.assertIn("if h_2 is not None", three_m)
        self.assertIn("elif h_1 is not None", three_m)
        self.assertEqual(1, three_m.count("denoised = model("))
        self.assertIn("fac = 1 / (2 * r)", plain_sde)
        self.assertEqual(1, plain_sde.count("denoised = model("))
        self.assertEqual(1, plain_sde.count("denoised_2 = model("))
        self.assertIn("sample_dpmpp_2s_ancestral_RF", two_s)
        self.assertIn("get_ancestral_step", two_s)
        self.assertIn("denoised_2 = model(", two_s)
        self.assertIn('getattr(model.inner_model.model_patcher.get_model_object(\'model_sampling\'), "noise_scale", 1.0)', two_s_rf)
        self.assertIn("cpu=True", two_m)
        self.assertIn("cpu=True", three_m)
        self.assertIn("cpu=True", plain_sde)
        for name in ("sample_dpmpp_2m_sde_gpu", "sample_dpmpp_3m_sde_gpu", "sample_dpmpp_sde_gpu"):
            section = sampling.split(f"def {name}", 1)[1].split("\ndef ", 1)[0]
            self.assertIn("cpu=False", section, name)

    def test_pinned_embedded_docs_paths_markers_and_documented_gaps(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for class_type in TARGET_TYPES:
                en_path = f"comfyui_embedded_docs/docs/{class_type}/en.md"
                ru_path = f"comfyui_embedded_docs/docs/{class_type}/ru.md"
                self.assertIn(en_path, archive.namelist())
                self.assertIn(ru_path, archive.namelist())
                en = archive.read(en_path).decode("utf-8")
                ru = archive.read(ru_path).decode("utf-8")
                self.assertIn("AI-generated", en)
                self.assertIn("создана с помощью ИИ", ru)
            two_m_en = archive.read("comfyui_embedded_docs/docs/SamplerDPMPP_2M_SDE/en.md").decode("utf-8")
            self.assertIn("| `solver_type`", two_m_en)
            self.assertIn("| STRING |", two_m_en)
            sde_en = archive.read("comfyui_embedded_docs/docs/SamplerDPMPP_SDE/en.md").decode("utf-8")
            self.assertIn("influences the sampling behavior", sde_en)
            two_s_en = archive.read("comfyui_embedded_docs/docs/SamplerDPMPP_2S_Ancestral/en.md").decode("utf-8")
            self.assertNotIn("CONST", two_s_en)
            self.assertNotIn("RF", two_s_en)

    def test_exhaustive_512_json_root_and_subgraph_census_has_no_targets(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        json_count = root_graphs = subgraphs = 0
        matches: list[tuple[str, str, Any]] = []
        algorithm_records: list[dict[str, Any]] = []
        payloads: dict[str, dict[str, Any]] = {}
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for member in archive.namelist():
                if not member.endswith(".json") or "/templates/" not in member:
                    continue
                json_count += 1
                payload = json.loads(archive.read(member))
                if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
                    continue
                root_graphs += 1
                payloads[Path(member).name] = payload
                graphs: list[tuple[str, dict[str, Any]]] = [("root", payload)]
                definitions = payload.get("definitions")
                nested = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
                for index, graph in enumerate(nested):
                    if isinstance(graph, dict):
                        subgraphs += 1
                        graphs.append((f"subgraph:{index}", graph))
                for scope, graph in graphs:
                    for node in graph.get("nodes", []):
                        if isinstance(node, dict) and node.get("type") in TARGET_TYPES:
                            matches.append((member, scope, node.get("id")))
                        if isinstance(node, dict):
                            selected = sorted(set(nested_strings(node.get("widgets_values"))) & ALGORITHM_NAMES)
                            for algorithm in selected:
                                algorithm_records.append(
                                    {
                                        "file": Path(member).name,
                                        "scope": scope,
                                        "id": node.get("id"),
                                        "type": node.get("type"),
                                        "mode": node.get("mode"),
                                        "widgets": node.get("widgets_values"),
                                        "algorithm": algorithm,
                                    }
                                )
        self.assertEqual((512, 496, 272), (json_count, root_graphs, subgraphs))
        self.assertEqual([], matches)
        self.assertEqual(6, len(algorithm_records))
        self.assertTrue(all(record["mode"] == 0 for record in algorithm_records))
        counts: dict[str, int] = {}
        for record in algorithm_records:
            counts[record["algorithm"]] = counts.get(record["algorithm"], 0) + 1
        self.assertEqual(
            {"dpmpp_3m_sde_gpu": 2, "dpmpp_2m_sde_gpu": 1, "dpmpp_2m_sde": 3},
            counts,
        )

        by_file = {record["file"]: record for record in algorithm_records}
        self.assertEqual(
            [840755638734093, "randomize", 50, 4.98, "dpmpp_3m_sde_gpu", "exponential", 1],
            by_file["audio_stable_audio_example.json"]["widgets"],
        )
        self.assertEqual(
            [900749379955168, "randomize", 26, 8, "dpmpp_3m_sde_gpu", "exponential", 1],
            by_file["sdxl_revision_text_prompts.json"]["widgets"],
        )
        self.assertEqual(
            ["dpmpp_2m_sde_gpu"],
            by_file["image_hidream_o1.json"]["widgets"],
        )
        self.assertEqual(
            [966630005845873, "randomize", 5, 1, "dpmpp_2m_sde", "beta57", 0.6],
            by_file["template_rob_realistic_2k_images_quick_variations.json"]["widgets"],
        )
        self.assertEqual(
            [873653643772748, "randomize", 5, 1, "dpmpp_2m_sde", "beta57", 0.4],
            by_file["templates_rob_realistic_2k_images_quick_variations.app.json"]["widgets"],
        )
        self.assertEqual(
            [824287194145573, "randomize", 5, 1, "dpmpp_2m_sde", "beta", 0.33],
            by_file["utility_z_image_turbo_2k_upscaler.app.json"]["widgets"],
        )

        hidream = payloads["image_hidream_o1.json"]
        hidream_nodes = {node["id"]: node for node in hidream["nodes"]}
        self.assertEqual("KSamplerSelect", hidream_nodes[230]["type"])
        self.assertEqual(["normal", 40, 1], hidream_nodes[112]["widgets_values"])
        self.assertEqual("SamplerCustom", hidream_nodes[108]["type"])
        self.assertIn([351, 230, 0, 108, 3, "SAMPLER"], hidream["links"])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_constructor_and_ancestral_math_probe(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)
        constructors = result["constructors"]
        self.assertEqual("dpmpp_3m_sde", constructors["3mCpu"]["name"])
        self.assertEqual("dpmpp_3m_sde_gpu", constructors["3mGpu"]["name"])
        self.assertEqual("midpoint", constructors["2mMidpointCpu"]["options"]["solver_type"])
        self.assertEqual("heun", constructors["2mHeunGpu"]["options"]["solver_type"])
        self.assertEqual("dpmpp_sde", constructors["sdeCpu"]["name"])
        self.assertEqual("dpmpp_sde_gpu", constructors["sdeGpu"]["name"])
        self.assertEqual("dpmpp_2s_ancestral", constructors["twoS"]["name"])
        self.assertEqual([5.0, 0.0], result["ancestralStep"]["eta0"])
        self.assertAlmostEqual(2.5, result["ancestralStep"]["eta1"][0])
        self.assertTrue(result["dpmppSdeDividesByTwoR"])


if __name__ == "__main__":
    unittest.main()
