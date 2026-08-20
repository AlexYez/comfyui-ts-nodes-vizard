from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


SPECS = {
    "core.save-lora-weights": ("save-lora-weights", "SaveLoRA", "sha256:d47e39c387157ab35cd522defc0c4cca747fdedd60f6caafecbe8931947dd14f", "save-trained-lora"),
    "core.lora-save": ("lora-save", "LoraSave", "sha256:5221a485e413a34b1567bef0473c8348c2cdaf57c0e2a9a653c1ac60a35c1411", "extract-model-diff-lora"),
    "core.loss-graph-node": ("loss-graph-node", "LossGraphNode", "sha256:fc403b31bf1c0fbfff792954c61ec8ec863e0a7870e2a3c48c151cc8de66ff2c", "plot-training-loss"),
}
DOCS = {
    "SaveLoRA": ("fa7eaa62a4ee1a8f4ea3cb33456509d4def53d91b78293e5512035e7fa189d16", "12912d0a5d37e46cd84842ef7a7c83aa93f6d3f022586cee75fcbea023dcdff0"),
    "LoraSave": ("61b03515ee0bb59f7e523bb86f62c34ffe2bca88bbf7c2e7eac78f9de0a72214", "477e891877bccbbf4b8368d55bc27acec3f796301345a987ea132008d5bb1471"),
    "LossGraphNode": ("2a62b431778ec54edd16c441b287736e57db1548fc678ed9c8c42f8a7f4e48c3", "d0ca858175c48f8abd303047a294034197f462934a6328fbb8cac354fc99c2b4"),
}


def graphs(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from graphs(item)
    elif isinstance(value, dict):
        if isinstance(value.get("nodes"), list):
            yield value
        definitions = value.get("definitions")
        if isinstance(definitions, dict):
            for item in definitions.get("subgraphs", []):
                yield from graphs(item)


class LoraSaveLossContentTests(unittest.TestCase):
    def test_schemas_status_sections_and_fragments(self):
        schemas = {name: catalog.load_json(catalog.CONTENT / f"schemas/{name}.schema.v1.json") for name in ("article", "recipe", "recipe-fragment", "article-research")}
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        for article_id, (directory, _, _, recipe_dir) in SPECS.items():
            article_path = catalog.CONTENT / "articles/core" / directory / "manifest.json"
            article = catalog.load_json(article_path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(article_path, article, errors)
            self.assertEqual(("draft", "in_review"), (article["status"], article["editorial"]["state"]))
            self.assertEqual(10, len(re.findall(r"^## ", (article_path.parent / "ru.md").read_text(encoding="utf-8"), re.M)))
            ledger = catalog.load_json(catalog.CONTENT / "research/reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["article-research"]))
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            recipe_path = catalog.CONTENT / "recipes" / recipe_dir / "recipe.json"
            recipe = catalog.load_json(recipe_path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(recipe_path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            self.assertEqual([], catalog.json_schema_errors(catalog.load_json(recipe_path.parent / "fragment.json"), schemas["recipe-fragment"]))
        self.assertEqual([], errors)

    def test_runtime_source_and_docs_fail_closed(self):
        nodes = catalog.object_info_nodes(catalog.load_json(catalog.CONTENT / "runtime/comfyui-0.32.0.object-info.json"))
        for _, (_, class_type, fingerprint, _) in SPECS.items():
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, nodes[class_type]))
            self.assertTrue(nodes[class_type]["experimental"])
            self.assertTrue(nodes[class_type]["output_node"])
        train = catalog.ROOT / ".comfyui-source-0.32.0/comfy_extras/nodes_train.py"
        extract = catalog.ROOT / ".comfyui-source-0.32.0/comfy_extras/nodes_lora_extract.py"
        self.assertEqual("b95c59f1e7a0dc9e4ca2782377b571dc3ffe722d7d36eb08801526a9dfb34ae5", hashlib.sha256(train.read_bytes()).hexdigest())
        self.assertEqual("bf15126341d68added60f1d38cb025677ac78d49822e8026caed923bae24b626", hashlib.sha256(extract.read_bytes()).hexdigest())
        train_text = train.read_text(encoding="utf-8")
        extract_text = extract.read_text(encoding="utf-8")
        for snippet in ("{filename}_{steps}_steps_{counter:05}_.safetensors", "scaled_loss = [(l - min_loss) / (max_loss - min_loss)", "ui.PreviewImage(img_tensor, cls=cls)"):
            self.assertIn(snippet, train_text)
        for snippet in ("rank = min(rank, in_dim, out_dim)", "torch.linalg.svd(diff.float())", "torch.quantile(dist, CLAMP_QUANTILE)", "metadata=None"):
            self.assertIn(snippet, extract_text)
        docs = catalog.ROOT / ".upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl"
        with zipfile.ZipFile(docs) as archive:
            for class_type, (en_hash, ru_hash) in DOCS.items():
                self.assertEqual(en_hash, hashlib.sha256(archive.read(f"comfyui_embedded_docs/docs/{class_type}/en.md")).hexdigest())
                self.assertEqual(ru_hash, hashlib.sha256(archive.read(f"comfyui_embedded_docs/docs/{class_type}/ru.md")).hexdigest())

    def test_exact_edge_math(self):
        values = [4.0, 2.0, 3.0]
        low, high = min(values), max(values)
        self.assertEqual([1.0, 0.0, 0.5], [(value - low) / (high - low) for value in values])
        with self.assertRaises(ZeroDivisionError):
            _ = [(value - 1.0) / (1.0 - 1.0) for value in [1.0]]
        self.assertEqual(2, min(8, 2, 3))
        self.assertEqual("name_7_steps_00003_.safetensors", f"name_{7}_steps_{3:05}_.safetensors")

    def test_workflow_zero_census(self):
        workflow_wheel = catalog.ROOT / ".upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
        counts = {class_type: 0 for _, class_type, _, _ in SPECS.values()}
        json_count = graph_count = 0
        with zipfile.ZipFile(workflow_wheel) as archive:
            for name in archive.namelist():
                if not name.endswith(".json"):
                    continue
                json_count += 1
                for graph in graphs(json.loads(archive.read(name))):
                    graph_count += 1
                    for node in graph.get("nodes", []):
                        if node.get("type") in counts:
                            counts[node["type"]] += 1
        self.assertEqual((512, 768), (json_count, graph_count))
        self.assertEqual({"SaveLoRA": 0, "LoraSave": 0, "LossGraphNode": 0}, counts)

    def test_natural_russian_and_honesty(self):
        bad = re.compile(r"official case|source-derived|root workflow|human approved|exact nodes|in 768 graphs", re.I)
        for article_id, (directory, _, _, recipe_dir) in SPECS.items():
            for path in (catalog.CONTENT / "articles/core" / directory / "ru.md", catalog.CONTENT / "recipes" / recipe_dir / "ru.md", catalog.CONTENT / "research/reviews" / f"{article_id}.json"):
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, bad)
                self.assertNotIn("\ufffd", text)


if __name__ == "__main__":
    unittest.main()
