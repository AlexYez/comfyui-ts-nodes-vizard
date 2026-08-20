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
    "core.sam3-detect": (
        "sam3-detect",
        "SAM3_Detect",
        "sha256:fba0b4aa9cc9b9d25044112b793252f4440dfea16aeb43ee4d1af0aa57c4d2d4",
        "sam3-detect-text-mask",
    ),
    "core.sam3-video-track": (
        "sam3-video-track",
        "SAM3_VideoTrack",
        "sha256:5171cc0ac90f251e7026053834b4d3dc09fc3e15e0d92b15ab99042ab9d49d51",
        "sam3-video-track-default",
    ),
    "core.sam3-track-preview": (
        "sam3-track-preview",
        "SAM3_TrackPreview",
        "sha256:fe8749c4a6cc91d3246c8001a39a1ae40798b7984aac14618286e563869c0033",
        "sam3-preview-track",
    ),
    "core.sam3-track-to-mask": (
        "sam3-track-to-mask",
        "SAM3_TrackToMask",
        "sha256:73ee67f8aa1a0157ce82ff8a3a8fc673b4fd079e6e9748bbd611a563d417b2a3",
        "sam3-track-union-mask",
    ),
}

DOCS = {
    "SAM3_Detect": (
        "c22bb489cadd3a0174025c84f0fd560b7d536e6de2d3ab3396139301a0869e89",
        "4cc47f1d5e43065bd92a86af09c042692b64110144a5828639b6529b44f7cab5",
    ),
    "SAM3_VideoTrack": (
        "70314be5f861efd5d37fdbe1b0b277b55243388bd1147a352036e38b110a7d76",
        "42b933c5f03ec7b7b825be3907b67a7cafab6251d8f59175a59efee65bf99853",
    ),
    "SAM3_TrackPreview": (
        "b26a3b61222d0b646caa69ede1dc5cb38e73b6723a6d3ae87140ad78175d660a",
        "6e77d17f286df93dcbc4cabe878a890c49b9e764c392c8202a2863f976973661",
    ),
    "SAM3_TrackToMask": (
        "e58efc6114f4e7b579d75109e86af8a9f8e145b68f54b4d0fccf0fba0edcca25",
        "212d14d73999c4111533e5571e1363eca56ab9b755395b0724ac15e4f84da2d9",
    ),
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


class SAM3ContentTests(unittest.TestCase):
    def test_schema_identity_and_honesty(self) -> None:
        schemas = {
            name: catalog.load_json(catalog.CONTENT / f"schemas/{name}.schema.v1.json")
            for name in ("article", "recipe", "recipe-fragment", "article-research")
        }
        article_ids = {
            catalog.load_json(path)["articleId"]
            for path in (catalog.CONTENT / "articles").rglob("manifest.json")
        }
        nodes = catalog.object_info_nodes(
            catalog.load_json(catalog.CONTENT / "runtime/comfyui-0.32.0.object-info.json")
        )
        errors: list[str] = []
        for article_id, (directory, class_type, fingerprint, recipe) in SPECS.items():
            article_path = catalog.CONTENT / "articles/core" / directory / "manifest.json"
            article = catalog.load_json(article_path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(article_path, article, errors)
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(10, len(re.findall(r"^## ", (article_path.parent / "ru.md").read_text(encoding="utf8"), re.M)))
            self.assertEqual("comfy_extras.nodes_sam3", article["runtimeIdentity"]["pythonModule"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, nodes[class_type]))
            self.assertFalse(bool(nodes[class_type].get("experimental", False)))
            self.assertFalse(bool(nodes[class_type].get("deprecated", False)))

            recipe_path = catalog.CONTENT / "recipes" / recipe / "recipe.json"
            recipe_data = catalog.load_json(recipe_path)
            fragment_data = catalog.load_json(recipe_path.parent / "fragment.json")
            catalog.validate_recipe(recipe_path, recipe_data, article_ids, errors)
            self.assertEqual([], catalog.json_schema_errors(recipe_data, schemas["recipe"]))
            self.assertEqual([], catalog.json_schema_errors(fragment_data, schemas["recipe-fragment"]))
            self.assertNotIn("workflow", recipe_data)

            ledger = catalog.load_json(catalog.CONTENT / "research/reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["article-research"]))
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
        self.assertEqual([], errors)

    def test_pinned_source_and_docs(self) -> None:
        source = catalog.ROOT / ".comfyui-source-0.32.0/comfy_extras/nodes_sam3.py"
        self.assertEqual(
            "596951b7288b77bb919eda2171287670b40e32a05f2cda935e3f0547465158b8",
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        text = source.read_text(encoding="utf8")
        for snippet in (
            'common_upscale(image[..., :3].movedim(-1, 1), 1008, 1008, "bilinear", crop="disabled")',
            "keep = probs > threshold",
            "max_objects=max_objects",
            "Fraction(round(fps * 1000), 1000)",
            "if i.strip().isdigit()",
            'mode="bilinear", align_corners=False',
        ):
            self.assertIn(snippet, text)
        with zipfile.ZipFile(catalog.ROOT / ".upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl") as archive:
            for class_type, (english_hash, russian_hash) in DOCS.items():
                base = f"comfyui_embedded_docs/docs/{class_type}"
                self.assertEqual(english_hash, hashlib.sha256(archive.read(f"{base}/en.md")).hexdigest())
                self.assertEqual(russian_hash, hashlib.sha256(archive.read(f"{base}/ru.md")).hexdigest())

    def test_official_workflow_census_and_presets(self) -> None:
        found: list[tuple[str, Any, int]] = []
        json_count = graph_count = 0
        targets = {spec[1] for spec in SPECS.values()}
        with zipfile.ZipFile(catalog.ROOT / ".upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl") as archive:
            for name in archive.namelist():
                if not name.endswith(".json"):
                    continue
                json_count += 1
                for graph in graphs(json.loads(archive.read(name))):
                    graph_count += 1
                    for node in graph.get("nodes", []):
                        if node.get("type") in targets:
                            found.append((node["type"], node.get("widgets_values"), node.get("mode", 0)))
        self.assertEqual((512, 768), (json_count, graph_count))
        counts = Counter(item[0] for item in found)
        self.assertEqual(
            {"SAM3_Detect": 4, "SAM3_VideoTrack": 8},
            dict(counts),
        )
        self.assertTrue(all(values == [0.5, 2, False] and mode == 0 for kind, values, mode in found if kind == "SAM3_Detect"))
        self.assertTrue(all(values == [0.5, 4, 1] and mode == 0 for kind, values, mode in found if kind == "SAM3_VideoTrack"))

    def test_fragments_are_exact_and_external(self) -> None:
        expected = {
            "sam3-detect-text-mask": ("SAM3_Detect", {"threshold": 0.5, "refine_iterations": 2, "individual_masks": False}, 3),
            "sam3-video-track-default": ("SAM3_VideoTrack", {"detection_threshold": 0.5, "max_objects": 4, "detect_interval": 1}, 3),
            "sam3-preview-track": ("SAM3_TrackPreview", {"opacity": 0.5, "fps": 24.0}, 1),
            "sam3-track-union-mask": ("SAM3_TrackToMask", {"object_indices": ""}, 1),
        }
        for directory, (class_type, settings, external_count) in expected.items():
            fragment = catalog.load_json(catalog.CONTENT / "recipes" / directory / "fragment.json")
            self.assertEqual(1, len(fragment["nodes"]))
            self.assertEqual(class_type, fragment["nodes"][0]["classType"])
            self.assertEqual(settings, fragment["nodes"][0]["settings"])
            self.assertEqual(external_count, len(fragment["externalInputs"]))
            self.assertEqual([], fragment["connections"])

    def test_natural_russian_regression(self) -> None:
        forbidden = re.compile(
            r"\b(?:official|workflow|source-derived|human approval pending|instances|optional|default|tracks|identities|encoder|detector|decoder|packed masks)\b",
            re.I,
        )
        for article_id, (directory, _class_type, _fingerprint, recipe) in SPECS.items():
            prose = (catalog.CONTENT / "articles/core" / directory / "ru.md").read_text(encoding="utf8")
            prose += "\n" + (catalog.CONTENT / "recipes" / recipe / "ru.md").read_text(encoding="utf8")
            ledger = catalog.load_json(catalog.CONTENT / "research/reviews" / f"{article_id}.json")
            prose += "\n" + "\n".join(item["assessment"] for item in ledger["evidence"]["embeddedDocs"])
            prose += "\n" + "\n".join(item["role"] for item in ledger["evidence"]["workflows"])
            prose += "\n" + "\n".join(ledger["knownGaps"])
            without_code = re.sub(r"`[^`]+`|https?://\S+", "", prose)
            self.assertIsNone(forbidden.search(without_code), directory)


if __name__ == "__main__":
    unittest.main()
