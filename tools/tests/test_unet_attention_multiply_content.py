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


SPECS = {
    "core.unet-self-attention-multiply": {
        "directory": "unet-self-attention-multiply",
        "classType": "UNetSelfAttentionMultiply",
        "fingerprint": "sha256:2b9dd6bfde7a163154bda2656d172b311e22b1225d2df1650047ffdbeb99bed6",
        "recipe": "recipe.inspect-unet-self-attention-q",
    },
    "core.unet-cross-attention-multiply": {
        "directory": "unet-cross-attention-multiply",
        "classType": "UNetCrossAttentionMultiply",
        "fingerprint": "sha256:91c3715f15d033e726ed5eba0b183ed95fd3ed89f77141c62f0037162e1c5f6b",
        "recipe": "recipe.inspect-unet-cross-attention-v",
    },
    "core.unet-temporal-attention-multiply": {
        "directory": "unet-temporal-attention-multiply",
        "classType": "UNetTemporalAttentionMultiply",
        "fingerprint": "sha256:dd36e12633cfbf18f391aee221b6568e696d40a915df5bbcd9b1061c444e5b8c",
        "recipe": "recipe.wan-temporal-attention-chain",
    },
}

RECIPES = {
    "recipe.inspect-unet-self-attention-q": "inspect-unet-self-attention-q",
    "recipe.inspect-unet-cross-attention-v": "inspect-unet-cross-attention-v",
    "recipe.wan-temporal-attention-chain": "wan-temporal-attention-chain",
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

SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
PROBE = Path(__file__).with_name("unet_attention_multiply_synthetic_probe.py")

DOCS_HASH = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOW_HASH = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
SOURCE_HASHES = {
    "comfy_extras/nodes_attention_multiply.py": "486e015b785eb330afe8d79177466e601831c2515bafc2a33bd15598437db16b",
    "comfy/model_patcher.py": "0a0e1991b4bea80dc6f5785ba7d6b2d76929c976a6c156a08387a0567c9ebf04",
    "comfy/lora.py": "4efd82adbd4e70f8fc29a9bf1cf2827ca211e7a15297187236b7b3119acd8d03",
}
DOC_MEMBER_HASHES = {
    ("UNetSelfAttentionMultiply", "en"): "6f0831b46fb3edfd45aae912bc3cd708c59fd1d349e005004759569a1fa41f5a",
    ("UNetSelfAttentionMultiply", "ru"): "e5c2ede315d1eb90bf908b2cfccfa066fc218c1265bb5812eed8ed1d851f4447",
    ("UNetCrossAttentionMultiply", "en"): "2ae83378103b89247e356a60a438ef8796c7102bfebd598e25e9e747d6be76cc",
    ("UNetCrossAttentionMultiply", "ru"): "d743f5d3cffdf9d7da17b06121695780ca0e24487b60e747267e0020b415f6c3",
    ("UNetTemporalAttentionMultiply", "en"): "2df1109d72d9a931e0e4663246fd7018b6e575ab2b83dd45c3b2eab6fbd1432b",
    ("UNetTemporalAttentionMultiply", "ru"): "91dedcb20b857353b80079d9003e9b634b24256576a75edd85406ec6479c3f6b",
}


def article_path(spec: dict[str, str]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPES[recipe_id] / "recipe.json"


def article_ids() -> set[str]:
    return {
        payload["articleId"]
        for path in (catalog.CONTENT / "articles").rglob("manifest.json")
        if isinstance((payload := catalog.load_json(path)), dict)
        and isinstance(payload.get("articleId"), str)
    }


def runtime_inputs(node: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = node.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def graph_iter(payload: dict[str, Any]) -> Iterator[tuple[str, int | None, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", None, payload
    definitions = payload.get("definitions")
    if not isinstance(definitions, dict):
        return
    for index, graph in enumerate(definitions.get("subgraphs", [])):
        if isinstance(graph, dict) and isinstance(graph.get("nodes"), list):
            yield "subgraph", index, graph


def normalized_links(graph: dict[str, Any]) -> list[tuple[Any, Any, Any, Any, Any, Any]]:
    links = graph.get("links", [])
    if isinstance(links, list):
        return [tuple(link[:6]) for link in links if isinstance(link, list) and len(link) >= 6]
    return []


class UNetAttentionMultiplyContentTests(unittest.TestCase):
    def test_articles_recipes_fragments_and_ledgers_validate(self) -> None:
        ids = article_ids()
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        errors: list[str] = []
        cliches = re.compile(
            r"важно отметить|стоит подчеркнуть|подводя итог|в современном мире|революционн|"
            r"данная нода|является незаменим|давайте разбер|без лишних слов|коротко о главном",
            re.IGNORECASE,
        )

        for article_id, spec in SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            targets = article["relations"]["related"] + article["relations"]["alternatives"]
            self.assertTrue(set(targets).issubset(ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(EXPECTED_HEADINGS, re.findall(r"^## (.+)$", body, re.MULTILINE))
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliches)

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertTrue(research["checks"]["russianEdited"])
            self.assertTrue(research["checks"]["factsRecheckedAfterEditing"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(any("редактор" in gap.casefold() for gap in research["knownGaps"]))

        for recipe_id, directory in RECIPES.items():
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            self.assertNotRegex((path.parent / recipe["body"]).read_text(encoding="utf-8"), cliches)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))

        self.assertEqual([], errors)

    def test_runtime_identity_fingerprints_flags_and_fragment_ports(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for spec in SPECS.values():
            runtime = dict(nodes[spec["classType"]])
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_attention_multiply", runtime["python_module"])
            self.assertEqual("experimental/attention_experiments", runtime["category"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertTrue(runtime["experimental"])
            self.assertFalse(runtime["deprecated"])
            self.assertFalse(runtime["dev_only"])
            self.assertFalse(runtime["api_node"])
            self.assertEqual(["MODEL"], runtime["output"])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertIsNone(runtime["search_aliases"])

        for class_type in ("UNetSelfAttentionMultiply", "UNetCrossAttentionMultiply"):
            node = nodes[class_type]
            self.assertEqual(["model", "q", "k", "v", "out"], node["input_order"]["required"])
            for name in ("q", "k", "v", "out"):
                self.assertEqual(
                    {"advanced": True, "default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01},
                    node["input"]["required"][name][1],
                )
        temporal = nodes["UNetTemporalAttentionMultiply"]
        self.assertEqual(
            ["model", "self_structural", "self_temporal", "cross_structural", "cross_temporal"],
            temporal["input_order"]["required"],
        )

        expected = {
            "recipe.inspect-unet-self-attention-q": (["UNetSelfAttentionMultiply"], [], {"q": 0.9, "k": 1.0, "v": 1.0, "out": 1.0}),
            "recipe.inspect-unet-cross-attention-v": (["UNetCrossAttentionMultiply"], [], {"q": 1.0, "k": 1.0, "v": 0.9, "out": 1.0}),
        }
        for recipe_id, (class_types, connections, settings) in expected.items():
            recipe = catalog.load_json(recipe_path(recipe_id))
            fragment = catalog.load_json(recipe_path(recipe_id).parent / recipe["fragment"]["path"])
            self.assertEqual(class_types, [node["classType"] for node in fragment["nodes"]])
            self.assertEqual(connections, fragment["connections"])
            self.assertEqual(settings, fragment["nodes"][0]["settings"])

        recipe = catalog.load_json(recipe_path("recipe.wan-temporal-attention-chain"))
        fragment = catalog.load_json(recipe_path("recipe.wan-temporal-attention-chain").parent / recipe["fragment"]["path"])
        self.assertEqual(
            ["ModelSamplingSD3", "UNetTemporalAttentionMultiply", "CFGZeroStar", "KSampler"],
            [node["classType"] for node in fragment["nodes"]],
        )
        self.assertEqual(
            {"self_structural": 1.0, "self_temporal": 1.0, "cross_structural": 1.2, "cross_temporal": 1.3},
            fragment["nodes"][1]["settings"],
        )
        refs = {node["ref"]: node for node in fragment["nodes"]}
        for external in fragment["externalInputs"]:
            self.assertEqual(external["type"], runtime_inputs(dict(nodes[refs[external["to"]]["classType"]]))[external["input"]][0])
        for connection in fragment["connections"]:
            source = nodes[refs[connection["from"]]["classType"]]
            target = nodes[refs[connection["to"]]["classType"]]
            output_index = source["output_name"].index(connection["output"])
            self.assertEqual(source["output"][output_index], runtime_inputs(dict(target))[connection["input"]][0])

    def test_pinned_source_docs_and_replacements_are_fail_closed(self) -> None:
        self.assertTrue(SOURCE.is_dir())
        for relative, expected_hash in SOURCE_HASHES.items():
            data = (SOURCE / relative).read_bytes()
            self.assertEqual(expected_hash, hashlib.sha256(data).hexdigest(), relative)
        source_text = (SOURCE / "comfy_extras" / "nodes_attention_multiply.py").read_text(encoding="utf-8")
        for snippet in (
            'attention_multiply("attn1", model, q, k, v, out)',
            'attention_multiply("attn2", model, q, k, v, out)',
            'if \'.time_stack.\' in k:',
            'm.add_patches({k: (None,)}, 0.0, cross_temporal)',
        ):
            self.assertIn(snippet, source_text)
        self.assertNotIn("UNetSelfAttentionMultiply", json.dumps(catalog.load_json(REPLACEMENTS)))
        self.assertNotIn("UNetCrossAttentionMultiply", json.dumps(catalog.load_json(REPLACEMENTS)))
        self.assertNotIn("UNetTemporalAttentionMultiply", json.dumps(catalog.load_json(REPLACEMENTS)))

        self.assertTrue(DOCS_WHEEL.is_file())
        self.assertEqual(DOCS_HASH, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for (class_type, locale), expected_hash in DOC_MEMBER_HASHES.items():
                member = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                data = archive.read(member)
                self.assertEqual(expected_hash, hashlib.sha256(data).hexdigest(), member)
            temporal_en = archive.read("comfyui_embedded_docs/docs/UNetTemporalAttentionMultiply/en.md").decode("utf-8")
            self.assertNotIn("time_stack", temporal_en)
            self.assertNotIn("to_out.0", temporal_en)

    def test_exhaustive_workflow_census_and_wan_topology(self) -> None:
        self.assertTrue(WORKFLOW_WHEEL.is_file())
        self.assertEqual(WORKFLOW_HASH, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in SPECS.values()}
        direct: list[dict[str, Any]] = []
        json_count = root_count = subgraph_count = node_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for member in archive.namelist():
                if not member.endswith(".json") or "/templates/" not in member:
                    continue
                json_count += 1
                payload = json.loads(archive.read(member))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                definitions = payload.get("definitions")
                if isinstance(definitions, dict):
                    subgraph_count += sum(isinstance(item, dict) for item in definitions.get("subgraphs", []))
                for scope, index, graph in graph_iter(payload):
                    nodes = [node for node in graph["nodes"] if isinstance(node, dict)]
                    node_count += len(nodes)
                    for node in nodes:
                        if node.get("type") in targets:
                            direct.append({"member": Path(member).name, "payload": payload, "scope": scope, "index": index, "graph": graph, "node": node})

        self.assertEqual((512, 496, 272, 8120), (json_count, root_count, subgraph_count, node_count))
        self.assertEqual(Counter({"UNetTemporalAttentionMultiply": 2}), Counter(item["node"]["type"] for item in direct))
        self.assertEqual({"wan2.1_fun_control.json", "wan2.1_fun_inp.json"}, {item["member"] for item in direct})
        expected_seeds = {"wan2.1_fun_control.json": 887940314022885, "wan2.1_fun_inp.json": 622093119444720}
        for item in direct:
            self.assertEqual(("root", 68, 0, [1, 1, 1.2, 1.3]), (item["scope"], item["node"]["id"], item["node"]["mode"], item["node"]["widgets_values"]))
            self.assertEqual("e7533930-2792-43a9-b4b5-ded4617d8a43", item["payload"]["id"])
            nodes = {node["id"]: node for node in item["graph"]["nodes"] if isinstance(node, dict)}
            self.assertEqual([5.000000000000001], nodes[67]["widgets_values"])
            self.assertEqual([expected_seeds[item["member"]], "randomize", 20, 6, "uni_pc", "simple", 1], nodes[3]["widgets_values"])
            edges = {(nodes.get(a, {}).get("type"), nodes.get(b, {}).get("type"), typ) for _, a, _, b, _, typ in normalized_links(item["graph"])}
            self.assertIn(("ModelSamplingSD3", "UNetTemporalAttentionMultiply", "MODEL"), edges)
            self.assertIn(("UNetTemporalAttentionMultiply", "CFGZeroStar", "MODEL"), edges)
            self.assertIn(("CFGZeroStar", "KSampler", "MODEL"), edges)

    def test_safe_exact_source_probe_without_weights(self) -> None:
        self.assertTrue(SOURCE.is_dir())
        completed = subprocess.run(
            [sys.executable, str(PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        if completed.returncode != 0:
            self.fail(completed.stderr or completed.stdout)
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(8, result["self"]["matched"])
        self.assertEqual([0.0, 0.5, 1.5, 2.0], result["self"]["factors"])
        self.assertEqual(8, result["cross"]["matched"])
        self.assertEqual([0.4, 0.6, 0.8, 1.2], result["cross"]["factors"])
        self.assertEqual(8, result["temporal"]["matched"])
        self.assertEqual([0.4, 0.5, 0.6, 0.7], result["temporal"]["factors"])
        self.assertEqual({"scaled": [3.0, 6.0], "zeroed": [0.0, 0.0], "sequential": [0.5, 1.0]}, result["weights"])

    def test_article_and_runtime_identities_are_unique(self) -> None:
        article_matches = Counter()
        class_matches = Counter()
        for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
            payload = catalog.load_json(path)
            if isinstance(payload, dict):
                article_matches[payload.get("articleId")] += 1
                identity = payload.get("runtimeIdentity")
                if isinstance(identity, dict) and identity.get("origin") == "backend":
                    class_matches[identity.get("classType")] += 1
        for article_id, spec in SPECS.items():
            self.assertEqual(1, article_matches[article_id])
            self.assertEqual(1, class_matches[spec["classType"]])


if __name__ == "__main__":
    unittest.main()
