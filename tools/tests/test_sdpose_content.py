from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter
from typing import Any, Iterator

from tools import catalog


SPECS = {
    "core.sdpose-keypoint-extractor": ("sdpose-keypoint-extractor", "SDPoseKeypointExtractor", "sha256:28e715e943741912b1e7cd89ae2cad9a0350053ca2a5f7be4165c9994812ff21"),
    "core.sdpose-draw-keypoints": ("sdpose-draw-keypoints", "SDPoseDrawKeypoints", "sha256:44a612d677dc8ee8a11db2869b6b93379dac759838065689d54302869432aab7"),
    "core.sdpose-face-bboxes": ("sdpose-face-bboxes", "SDPoseFaceBBoxes", "sha256:0f1ecda555e33a13f3d8745124a42950203c74da4109f84d2ddc72ee81d2d9f1"),
}
DOCS = {
    "SDPoseKeypointExtractor": ("40a9eb95f3f8eb692ec2d63b0b0fc64e13cd28f1754387e7481bed8e79e8ef13", "3917ae9d76070a157d53530a28ccbb9651a6ae16b9b2c3bb6f6878d05e221068"),
    "SDPoseDrawKeypoints": ("2c7ddec14a5010e87ce5168ba713a624b716ae49c7745a22f34ec1040b7ed40d", "0ef793e75853f3cc40b4ef104452afdffbb26df3be51c13018bd98e639c0ca33"),
    "SDPoseFaceBBoxes": ("4fd7b44d0ddeb3e00ed5316e8584f47a988d409a52d2045e6b9bb51463275fcc", "1066b40506432ec32c66c77b4bc0892a933e3c9eaef517aa77c2734c0a28d828"),
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


class SDPoseContentTests(unittest.TestCase):
    def test_schema_identity_and_honesty(self):
        schemas = {name: catalog.load_json(catalog.CONTENT / f"schemas/{name}.schema.v1.json") for name in ("article", "recipe", "recipe-fragment", "article-research")}
        runtime = catalog.object_info_nodes(catalog.load_json(catalog.CONTENT / "runtime/comfyui-0.32.0.object-info.json"))
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        for article_id, (slug, class_type, fingerprint) in SPECS.items():
            path = catalog.CONTENT / "articles/core" / slug / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(10, len(re.findall(r"^## ", (path.parent / "ru.md").read_text(encoding="utf8"), re.M)))
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, runtime[class_type]))
            self.assertEqual("comfy_extras.nodes_sdpose", runtime[class_type]["python_module"])
            self.assertFalse(any(runtime[class_type].get(flag, False) for flag in ("experimental", "deprecated", "dev_only", "api_node")))
            ledger = catalog.load_json(catalog.CONTENT / "research/reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["article-research"]))
            self.assertFalse(ledger["checks"]["exampleExecuted"])
        for recipe_slug in ("sdpose-extract-and-draw", "sdpose-face-bboxes"):
            path = catalog.CONTENT / "recipes" / recipe_slug / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            self.assertEqual([], catalog.json_schema_errors(catalog.load_json(path.parent / "fragment.json"), schemas["recipe-fragment"]))
        self.assertEqual([], errors)

    def test_pinned_source_and_docs(self):
        path = catalog.ROOT / ".comfyui-source-0.32.0/comfy_extras/nodes_sdpose.py"
        self.assertEqual("eb9ad7181c8d236a7531e238d7d0e1e2deab726085a30556203bd2c043b4812c", hashlib.sha256(path.read_bytes()).hexdigest())
        text = path.read_text(encoding="utf8")
        for snippet in (
            "model_w = int(head.heatmap_size[0]) * 4",
            'sampler_name="euler", scheduler="simple"',
            "bboxes[min(img_idx, len(bboxes) - 1)]",
            "face_kp,  face_sc  = face_kp[:68], face_sc[:68]",
            "expanded_area = initial_area * scale",
            "kp_padded = np.vstack([np.zeros((1, 2)",
        ):
            self.assertIn(snippet, text)
        with zipfile.ZipFile(catalog.ROOT / ".upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl") as archive:
            for class_type, (en_hash, ru_hash) in DOCS.items():
                base = f"comfyui_embedded_docs/docs/{class_type}"
                self.assertEqual(en_hash, hashlib.sha256(archive.read(f"{base}/en.md")).hexdigest())
                self.assertEqual(ru_hash, hashlib.sha256(archive.read(f"{base}/ru.md")).hexdigest())

    def test_official_workflow_census_and_widgets(self):
        counts = Counter()
        widgets: dict[str, list[list[Any]]] = {class_type: [] for _, class_type, _ in SPECS.values()}
        modes: dict[str, list[int]] = {class_type: [] for _, class_type, _ in SPECS.values()}
        json_count = graph_count = 0
        with zipfile.ZipFile(catalog.ROOT / ".upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl") as archive:
            for name in archive.namelist():
                if not name.endswith(".json"):
                    continue
                json_count += 1
                for graph in graphs(json.loads(archive.read(name))):
                    graph_count += 1
                    for node in graph.get("nodes", []):
                        class_type = node.get("type")
                        if class_type in widgets:
                            counts[class_type] += 1
                            widgets[class_type].append(node.get("widgets_values", []))
                            modes[class_type].append(node.get("mode", 0))
        self.assertEqual((512, 768), (json_count, graph_count))
        self.assertEqual({"SDPoseKeypointExtractor": 4, "SDPoseDrawKeypoints": 4}, dict(counts))
        self.assertEqual([[16]] * 4, widgets["SDPoseKeypointExtractor"])
        self.assertEqual(2, widgets["SDPoseDrawKeypoints"].count([True, True, True, True, 4, 2, 0.5, True]))
        self.assertEqual(2, widgets["SDPoseDrawKeypoints"].count([True, True, True, True, 4, 2, 0.5]))
        self.assertEqual([0] * 4, modes["SDPoseKeypointExtractor"])
        self.assertEqual([0] * 4, modes["SDPoseDrawKeypoints"])

    def test_fragments_match_runtime_contract(self):
        main = catalog.load_json(catalog.CONTENT / "recipes/sdpose-extract-and-draw/fragment.json")
        self.assertEqual(["SDPoseKeypointExtractor", "SDPoseDrawKeypoints"], [node["classType"] for node in main["nodes"]])
        self.assertEqual({"batch_size": 16}, main["nodes"][0]["settings"])
        self.assertEqual("keypoints", main["connections"][0]["output"])
        self.assertEqual("keypoints", main["connections"][0]["input"])
        boxes = catalog.load_json(catalog.CONTENT / "recipes/sdpose-face-bboxes/fragment.json")
        self.assertEqual("SDPoseFaceBBoxes", boxes["nodes"][0]["classType"])
        self.assertEqual({"scale": 1.5, "force_square": True}, boxes["nodes"][0]["settings"])


if __name__ == "__main__":
    unittest.main()
