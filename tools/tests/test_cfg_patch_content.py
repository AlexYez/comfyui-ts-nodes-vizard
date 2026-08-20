from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


SPECS: dict[str, dict[str, Any]] = {
    "core.cfg-norm": {
        "directory": "cfg-norm",
        "classType": "CFGNorm",
        "module": "comfy_extras.nodes_cfg",
        "fingerprint": "sha256:86e72419cab85ab8535177b18a883e6bf81d7b2d8eaba29408543f7afc9cc8f8",
        "experimental": True,
        "recipe": "recipe.cfg-norm-pre-cfg",
        "recipeDirectory": "cfg-norm-pre-cfg",
        "nodes": {
            "norm": ("CFGNorm", {"strength": 1.0, "pre_cfg": True}),
            "sample": (
                "KSampler",
                {"seed": 42, "steps": 40, "cfg": 4.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0},
            ),
        },
    },
    "core.cfg-zero-star": {
        "directory": "cfg-zero-star",
        "classType": "CFGZeroStar",
        "module": "comfy_extras.nodes_cfg",
        "fingerprint": "sha256:4670102f9220dd2cd6f5e94df4662b6cb8ab3cb3a8d047f031978927e28ab50c",
        "experimental": False,
        "recipe": "recipe.cfg-zero-star-wan-sampling",
        "recipeDirectory": "cfg-zero-star-wan-sampling",
        "nodes": {
            "zero-star": ("CFGZeroStar", {}),
            "sample": (
                "KSampler",
                {"seed": 887940314022885, "steps": 20, "cfg": 6.0, "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0},
            ),
        },
    },
    "core.tcfg": {
        "directory": "tcfg",
        "classType": "TCFG",
        "module": "comfy_extras.nodes_tcfg",
        "fingerprint": "sha256:d2411b73c2bf2951a3cd8f4d09fda2821319a956cf3b17b6e80de981c370e7ec",
        "experimental": False,
        "recipe": "recipe.tcfg-standard-sampling",
        "recipeDirectory": "tcfg-standard-sampling",
        "nodes": {
            "tcfg": ("TCFG", {}),
            "sample": (
                "KSampler",
                {"seed": 0, "steps": 20, "cfg": 8.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0},
            ),
        },
    },
    "core.mahiro": {
        "directory": "mahiro",
        "classType": "Mahiro",
        "module": "comfy_extras.nodes_mahiro",
        "fingerprint": "sha256:a657e6ea447319c013397d0720c331a88ca4a3d4d319416208508dff5f02a32a",
        "experimental": True,
        "recipe": "recipe.mahiro-standard-sampling",
        "recipeDirectory": "mahiro-standard-sampling",
        "nodes": {
            "mahiro": ("Mahiro", {}),
            "sample": (
                "KSampler",
                {"seed": 0, "steps": 20, "cfg": 8.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0},
            ),
        },
    },
}

SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
INVENTORY_META = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.meta.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
PROBE = Path(__file__).with_name("cfg_patch_synthetic_probe.py")
TARGETS = {spec["classType"] for spec in SPECS.values()}


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "recipes" / spec["recipeDirectory"] / "recipe.json"


def article_ids() -> set[str]:
    return {
        catalog.load_json(path)["articleId"]
        for path in (catalog.CONTENT / "articles").rglob("manifest.json")
    }


def graph_iter(payload: dict[str, Any]) -> Iterator[tuple[str, int | None, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", None, payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, graph in enumerate(subgraphs):
        if isinstance(graph, dict) and isinstance(graph.get("nodes"), list):
            yield "subgraph", index, graph


def normalized_links(graph: dict[str, Any]) -> Iterator[tuple[Any, Any, int, Any, int, Any]]:
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            yield tuple(link[:6])
        elif isinstance(link, dict):
            yield (
                link.get("id"), link.get("origin_id"), link.get("origin_slot"),
                link.get("target_id"), link.get("target_slot"), link.get("type"),
            )


def scalar_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from scalar_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from scalar_strings(item)


class CfgPatchContentTests(unittest.TestCase):
    def test_articles_recipes_fragments_ledgers_and_russian_contract(self) -> None:
        schemas = {
            key: catalog.load_json(catalog.CONTENT / "schemas" / filename)
            for key, filename in {
                "article": "article.schema.v1.json",
                "recipe": "recipe.schema.v1.json",
                "fragment": "recipe-fragment.schema.v1.json",
                "research": "article-research.schema.v1.json",
            }.items()
        }
        inventory = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        ids = article_ids()
        errors: list[str] = []
        russian_files: list[Path] = []

        for article_id, spec in SPECS.items():
            manifest_path = article_path(spec)
            manifest = catalog.load_json(manifest_path)
            self.assertEqual([], catalog.json_schema_errors(manifest, schemas["article"]))
            catalog.validate_article(manifest_path, manifest, errors)
            self.assertEqual(article_id, manifest["articleId"])
            self.assertEqual(("draft", "in_review"), (manifest["status"], manifest["editorial"]["state"]))
            self.assertIn("human approval pending", manifest["editorial"]["reviewedBy"].casefold())
            self.assertEqual(spec["experimental"], manifest["experimental"])
            self.assertEqual(
                {"classType": spec["classType"], "pythonModule": spec["module"], "packageId": "comfy-core", "origin": "backend", "aliases": []},
                manifest["runtimeIdentity"],
            )
            self.assertEqual(spec["fingerprint"], manifest["editorial"]["schemaHash"])
            self.assertEqual("0.32.0", manifest["compatibility"]["comfyui"])
            self.assertEqual(">=1.48.7", manifest["compatibility"]["frontend"])
            self.assertEqual(f"ComfyUI v0.32.0 ({SOURCE_COMMIT})", manifest["compatibility"]["sourceRevision"])
            relation_targets = set(manifest["relations"]["related"] + manifest["relations"]["alternatives"])
            self.assertTrue(relation_targets.issubset(ids), relation_targets - ids)
            self.assertIn(spec["recipe"], {a["id"] for a in manifest["assets"] if a["type"] == "recipe"})

            body = manifest_path.parent / manifest["body"]
            text = body.read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", text, re.MULTILINE)), body)
            russian_files.append(body)

            ledger_path = catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            ledger = catalog.load_json(ledger_path)
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["research"]))
            self.assertEqual((article_id, spec["classType"], spec["module"]), (ledger["articleId"], ledger["node"]["classType"], ledger["node"]["pythonModule"]))
            self.assertEqual(("fact_checked", "automated_assisted"), (ledger["state"], ledger["reviewMode"]))
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            for key in ("implementationRead", "runtimeCompared", "officialCasesInspected", "exampleSchemaValidated", "russianEdited", "factsRecheckedAfterEditing"):
                self.assertTrue(ledger["checks"][key], (article_id, key))
            self.assertTrue(any("Человеческое" in gap for gap in ledger["knownGaps"]))

            current_recipe_path = recipe_path(spec)
            recipe = catalog.load_json(current_recipe_path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(current_recipe_path, recipe, ids, errors)
            self.assertEqual(spec["recipe"], recipe["recipeId"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"].casefold())
            self.assertNotIn("workflow", recipe)
            russian_files.append(current_recipe_path.parent / recipe["body"])

            fragment_path = current_recipe_path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            nodes = {node["ref"]: node for node in fragment["nodes"]}
            self.assertEqual(set(spec["nodes"]), set(nodes))
            for ref, (class_type, settings) in spec["nodes"].items():
                self.assertEqual((class_type, settings), (nodes[ref]["classType"], nodes[ref]["settings"]))

            supplied = {ref: set(node["settings"]) for ref, node in nodes.items()}
            for external in fragment["externalInputs"]:
                supplied[external["to"]].add(external["input"])
            for connection in fragment["connections"]:
                supplied[connection["to"]].add(connection["input"])
                source = inventory[nodes[connection["from"]]["classType"]]
                target = inventory[nodes[connection["to"]]["classType"]]
                output_index = source["output_name"].index(connection["output"])
                self.assertEqual(source["output"][output_index], target["input"]["required"][connection["input"]][0])
            for ref, node in nodes.items():
                required = set(inventory[node["classType"]]["input"]["required"])
                self.assertTrue(required.issubset(supplied[ref]), (article_id, ref, required - supplied[ref]))

        self.assertEqual([], errors)
        forbidden = (
            "важно отметить", "стоит отметить", "следует отметить", "в современном мире",
            "давайте", "погрузимся", "революционн", "является мощн", "подводя итог",
            "в заключение", "данная нода", "новый уровень", "идеальное решение",
        )
        for path in russian_files:
            text = path.read_text(encoding="utf-8").casefold()
            self.assertNotIn("\ufffd", text, path)
            for phrase in forbidden:
                self.assertNotIn(phrase, text, path)

    def test_exact_runtime_descriptors_fingerprints_flags_and_replacements(self) -> None:
        inventory = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        metadata = catalog.load_json(INVENTORY_META)
        self.assertEqual(("0.32.0", SOURCE_COMMIT), (metadata["source"]["backendVersion"], metadata["source"]["commit"]))

        expected_required = {
            "CFGNorm": {"model": ["MODEL", {}], "strength": ["FLOAT", {"default": 1.0, "min": 0.0, "max": 100.0, "step": 0.01}]},
            "CFGZeroStar": {"model": ["MODEL", {}]},
            "TCFG": {"model": ["MODEL", {}]},
            "Mahiro": {"model": ["MODEL", {}]},
        }
        expected_optional = {
            "CFGNorm": {"pre_cfg": ["BOOLEAN", {"tooltip": inventory["CFGNorm"]["input"]["optional"]["pre_cfg"][1]["tooltip"], "default": False}]},
            "CFGZeroStar": {}, "TCFG": {}, "Mahiro": {},
        }
        for spec in SPECS.values():
            class_type = spec["classType"]
            runtime = inventory[class_type]
            self.assertEqual(spec["module"], runtime["python_module"])
            self.assertEqual(expected_required[class_type], runtime["input"]["required"])
            self.assertEqual(expected_optional[class_type], runtime["input"].get("optional", {}))
            self.assertEqual(["MODEL"], runtime["output"])
            self.assertEqual(["patched_model"], runtime["output_name"])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertFalse(runtime["output_node"])
            self.assertEqual(
                {"deprecated": False, "experimental": spec["experimental"], "dev_only": False, "api_node": False},
                {key: runtime[key] for key in ("deprecated", "experimental", "dev_only", "api_node")},
            )
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(class_type, runtime))

        self.assertEqual("advanced/guidance", inventory["CFGNorm"]["category"])
        self.assertEqual("advanced/guidance", inventory["CFGZeroStar"]["category"])
        self.assertEqual("advanced/guidance", inventory["TCFG"]["category"])
        self.assertEqual("experimental", inventory["Mahiro"]["category"])
        self.assertEqual(["mahiro", "mahiro cfg", "similarity-adaptive guidance", "positive-biased cfg"], inventory["Mahiro"]["search_aliases"])
        self.assertIn("BEFORE", inventory["CFGNorm"]["input"]["optional"]["pre_cfg"][1]["tooltip"])
        self.assertIn("2503.18137", inventory["TCFG"]["description"])

        ksampler = inventory["KSampler"]["input"]["required"]
        self.assertEqual(
            (0, 20, 8.0, "euler", "simple", 1.0),
            (
                ksampler["seed"][1]["default"],
                ksampler["steps"][1]["default"],
                ksampler["cfg"][1]["default"],
                ksampler["sampler_name"][0][0],
                ksampler["scheduler"][0][0],
                ksampler["denoise"][1]["default"],
            ),
        )

        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for class_type in TARGETS:
            self.assertNotIn(class_type, replacements)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_and_embedded_docs_discrepancies(self) -> None:
        self.assertEqual(SOURCE_COMMIT, (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        cfg_source = (SOURCE / "comfy_extras" / "nodes_cfg.py").read_text(encoding="utf-8")
        tcfg_source = (SOURCE / "comfy_extras" / "nodes_tcfg.py").read_text(encoding="utf-8")
        mahiro_source = (SOURCE / "comfy_extras" / "nodes_mahiro.py").read_text(encoding="utf-8")
        model_patcher = (SOURCE / "comfy" / "model_patcher.py").read_text(encoding="utf-8")

        self.assertIn("if pre_cfg:", cfg_source)
        self.assertIn("comb = uncond + cond_scale * (cond - uncond)", cfg_source)
        self.assertIn("cond_norm / comb_norm.clamp_min(1e-12)", cfg_source)
        self.assertIn(".clamp(min=0.0, max=1.0)", cfg_source)
        self.assertIn("return pred_text_ * scale * strength", cfg_source)
        self.assertIn("squared_norm = torch.sum(negative_flat ** 2, dim=1, keepdim=True) + 1e-8", cfg_source)
        self.assertIn("m.set_model_sampler_post_cfg_function(cfg_zero_star)", cfg_source)
        self.assertNotIn("zero_init", cfg_source.casefold())

        self.assertIn("torch.linalg.svd(score_matrix, full_matrices=False)", tcfg_source)
        self.assertIn("torch.linalg.svd(score_matrix.cpu(), full_matrices=False)", tcfg_source)
        self.assertIn("None in args[\"conds\"][:2]", tcfg_source)
        self.assertIn("m.set_model_sampler_pre_cfg_function(tangential_damping_cfg)", tcfg_source)

        self.assertIn("torch.sqrt(u_leap.abs()) * u_leap.sign()", mahiro_source)
        self.assertIn("F.cosine_similarity(normu, normm).mean()", mahiro_source)
        self.assertIn("(simsc * cfg + (4 - simsc) * leap) / 4", mahiro_source)
        self.assertIn("m.set_model_sampler_post_cfg_function(mahiro_normd)", mahiro_source)
        self.assertIn('model_options.get("sampler_post_cfg_function", []) + [post_cfg_function]', model_patcher)
        self.assertIn('model_options.get("sampler_pre_cfg_function", []) + [pre_cfg_function]', model_patcher)

        self.assertEqual(DOCS_SHA, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            docs: dict[tuple[str, str], str] = {}
            for class_type in TARGETS:
                for locale in ("en", "ru"):
                    member = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                    self.assertIn(member, archive.namelist())
                    docs[(class_type, locale)] = archive.read(member).decode("utf-8")
            self.assertNotIn("pre_cfg", docs[("CFGNorm", "en")])
            self.assertNotIn("zero-init", docs[("CFGZeroStar", "en")].casefold())
            self.assertIn("2503.18137", docs[("TCFG", "en")])
            self.assertIn("Mahiro настолько мила", docs[("Mahiro", "ru")])
            for (class_type, locale), text in docs.items():
                marker = "AI-generated" if locale == "en" else "создана с помощью ИИ"
                self.assertIn(marker, text, (class_type, locale))

    def test_exhaustive_workflow_census_and_representative_topology(self) -> None:
        self.assertEqual(WORKFLOW_SHA, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        direct: list[dict[str, Any]] = []
        exact_scalar_hits = Counter()
        json_count = root_count = subgraph_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for member in archive.namelist():
                if not member.endswith(".json") or "/templates/" not in member:
                    continue
                json_count += 1
                payload = json.loads(archive.read(member))
                for value in scalar_strings(payload):
                    if value in TARGETS:
                        exact_scalar_hits[value] += 1
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                definitions = payload.get("definitions")
                if isinstance(definitions, dict):
                    subgraph_count += sum(isinstance(item, dict) for item in definitions.get("subgraphs", []))
                for scope, graph_index, graph in graph_iter(payload):
                    for node in graph["nodes"]:
                        if isinstance(node, dict) and node.get("type") in TARGETS:
                            direct.append({"member": Path(member).name, "payload": payload, "scope": scope, "index": graph_index, "graph": graph, "node": node})

        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual(Counter({"CFGNorm": 33, "CFGZeroStar": 2}), Counter(item["node"]["type"] for item in direct))
        self.assertEqual(Counter({"CFGNorm": 66, "CFGZeroStar": 4}), exact_scalar_hits)
        self.assertEqual(Counter({"root": 1, "subgraph": 32}), Counter(item["scope"] for item in direct if item["node"]["type"] == "CFGNorm"))
        self.assertEqual(Counter({"[1]": 14, "[1, false]": 18, "[1, true]": 1}), Counter(json.dumps(item["node"].get("widgets_values"), separators=(",", ":")).replace(",", ", ") for item in direct if item["node"]["type"] == "CFGNorm"))
        self.assertTrue(all(item["node"].get("mode") == 0 for item in direct))

        joy = next(item for item in direct if item["member"] == "image_joyai_image_edit.json" and item["node"]["type"] == "CFGNorm")
        self.assertEqual(("b2c3d4e5-f6a7-4890-91bc-def012345678", "subgraph", 0, "7f6dd18d-96db-4ad7-a173-6f6d8a0c3d01", 12, [1, True]), (joy["payload"]["id"], joy["scope"], joy["index"], joy["graph"]["id"], joy["node"]["id"], joy["node"]["widgets_values"]))
        joy_nodes = {node["id"]: node for node in joy["graph"]["nodes"] if isinstance(node, dict)}
        self.assertEqual([42, "fixed", 40, 4, "euler", "normal", 1], joy_nodes[10]["widgets_values"])
        joy_edges = {(joy_nodes.get(a, {}).get("type"), joy_nodes.get(b, {}).get("type"), typ) for _, a, _, b, _, typ in normalized_links(joy["graph"])}
        self.assertIn(("UNETLoader", "CFGNorm", "MODEL"), joy_edges)
        self.assertIn(("CFGNorm", "KSampler", "MODEL"), joy_edges)

        lens_records = [
            item for item in direct
            if item["member"] in {"image_lens_t2i.json", "image_lens_turbo_t2i.json"}
            and item["node"]["type"] == "CFGNorm"
        ]
        self.assertEqual(2, len(lens_records))
        self.assertTrue(all(item["node"]["widgets_values"] == [1, False] for item in lens_records))

        zero_records = [item for item in direct if item["node"]["type"] == "CFGZeroStar"]
        self.assertEqual({"wan2.1_fun_control.json", "wan2.1_fun_inp.json"}, {item["member"] for item in zero_records})
        expected_seeds = {
            "wan2.1_fun_control.json": 887940314022885,
            "wan2.1_fun_inp.json": 622093119444720,
        }
        for item in zero_records:
            self.assertEqual(("e7533930-2792-43a9-b4b5-ded4617d8a43", "root", 66, []), (item["payload"]["id"], item["scope"], item["node"]["id"], item["node"]["widgets_values"]))
            nodes = {node["id"]: node for node in item["graph"]["nodes"] if isinstance(node, dict)}
            self.assertEqual(
                [expected_seeds[item["member"]], "randomize", 20, 6, "uni_pc", "simple", 1],
                nodes[3]["widgets_values"],
            )
            edges = {(nodes.get(a, {}).get("type"), nodes.get(b, {}).get("type"), typ) for _, a, _, b, _, typ in normalized_links(item["graph"])}
            self.assertIn(("UNetTemporalAttentionMultiply", "CFGZeroStar", "MODEL"), edges)
            self.assertIn(("CFGZeroStar", "KSampler", "MODEL"), edges)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_probe_without_weights(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(PROBE), str(SOURCE)], cwd=catalog.ROOT,
            check=False, capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        if completed.returncode != 0:
            self.fail(completed.stderr or completed.stdout)
        result = json.loads(completed.stdout.strip().splitlines()[-1])

        norm = result["cfgNorm"]
        self.assertEqual([[[[0.0]], [[0.0]]]], norm["post"]["0.0"])
        self.assertEqual([[[[3.0]], [[4.0]]]], norm["post"]["1.0"])
        self.assertEqual([[[[6.0]], [[8.0]]]], norm["post"]["2.0"])
        self.assertEqual([[[[6.0]], [[8.0]]]], norm["pre"]["0.0"])
        self.assertEqual([[[[3.0]], [[4.0]]]], norm["pre"]["1.0"])
        self.assertEqual([[[[0.0]], [[0.0]]]], norm["pre"]["2.0"])
        self.assertTrue(norm["preCfgFunction"])
        self.assertEqual(1, norm["postHookCount"])

        zero = result["cfgZeroStar"]
        self.assertEqual([[2.0], [3.0]], zero["alphas"])
        self.assertTrue(zero["zeroAlphaFinite"])
        self.assertEqual([[7.0, 5.0]], zero["result"])
        self.assertEqual([[5.0, 5.0]], zero["cfgOne"])

        tcfg = result["tcfg"]
        self.assertEqual("torch.float16", tcfg["projectedDtype"])
        self.assertEqual([[0.0, 0.0]], tcfg["transformedUncond"])
        self.assertTrue(tcfg["skipIdentity"])
        self.assertEqual(1, tcfg["preHookCount"])

        mahiro = result["mahiro"]
        self.assertEqual([[1.0, 0.0]], mahiro["sameDirection"])
        self.assertEqual([[-4.0, 0.0]], mahiro["oppositeDirection"])
        self.assertEqual([[0.0, 1.0]], mahiro["orthogonal"])
        self.assertEqual([[1.0, 0.0], [-1.0, 0.0]], mahiro["batchCoupled"])
        self.assertEqual([[2.0, -1.0]], mahiro["cfgOne"])
        self.assertEqual(1, mahiro["postHookCount"])


if __name__ == "__main__":
    unittest.main()
