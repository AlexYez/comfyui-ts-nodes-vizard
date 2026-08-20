from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


ARTICLE_SPECS = {
    "core.batch-latents-node": {
        "directory": "batch-latents-node",
        "classType": "BatchLatentsNode",
        "pythonModule": "comfy_extras.nodes_post_processing",
        "fingerprint": "sha256:13547a24afeb51dc6181e063ef724575cfe6f4efa8721fa25959472f29d2c316",
        "recipe": "recipe.batch-two-latent-streams",
    },
    "core.rebatch-latents": {
        "directory": "rebatch-latents",
        "classType": "RebatchLatents",
        "pythonModule": "comfy_extras.nodes_rebatch",
        "fingerprint": "sha256:78b25af3f57292ce68c8baf958eb7a62db5327d89f3a29dfae75edc71ac67f44",
        "recipe": "recipe.rebatch-latents-by-two",
    },
    "core.rebatch-images": {
        "directory": "rebatch-images",
        "classType": "RebatchImages",
        "pythonModule": "comfy_extras.nodes_rebatch",
        "fingerprint": "sha256:c6a8bdbf23c861f5e80374fc61a76609c88e9556f7680da309da67dd4931fe06",
        "recipe": "recipe.rebatch-images-for-video",
    },
    "core.audio-concat": {
        "directory": "audio-concat",
        "classType": "AudioConcat",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:bcda352b5c3831ab72952028ec02d709f6e4ed2290c7fd9c4d0866213782c012",
        "recipe": "recipe.concatenate-audio-after",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.batch-two-latent-streams": "batch-two-latent-streams",
    "recipe.rebatch-latents-by-two": "rebatch-latents-by-two",
    "recipe.rebatch-images-for-video": "rebatch-images-for-video",
    "recipe.concatenate-audio-after": "concatenate-audio-after",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.batch-two-latent-streams": [("BatchLatentsNode", {})],
    "recipe.rebatch-latents-by-two": [
        ("RebatchLatents", {"batch_size": 2}),
    ],
    "recipe.rebatch-images-for-video": [
        ("RebatchImages", {"batch_size": 4096}),
        ("CreateVideo", {"fps": 30.0, "bit_depth": 8}),
    ],
    "recipe.concatenate-audio-after": [
        ("AudioConcat", {"direction": "after"}),
    ],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_WHEEL_SHA256 = (
    "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
)


def article_path(spec: dict[str, str]) -> Path:
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


def workflow_node_records(
    payload: dict[str, Any], member: str
) -> Iterator[dict[str, Any]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield {"member": member, "scope": "root", "node": node}

    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph_index, subgraph in enumerate(subgraphs):
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield {
                    "member": member,
                    "scope": "subgraph",
                    "subgraphIndex": subgraph_index,
                    "subgraphId": subgraph.get("id"),
                    "node": node,
                }


def load_official_node_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
        for member in sorted(archive.namelist()):
            if "/templates/" not in member or not member.endswith(".json"):
                continue
            payload = json.loads(archive.read(member).decode("utf-8"))
            if isinstance(payload, dict):
                records.extend(workflow_node_records(payload, member))
    return records


class BatchRebatchContentTests(unittest.TestCase):
    def test_articles_and_fragment_only_recipes_are_structurally_valid(self) -> None:
        article_ids = all_article_ids()
        article_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article.schema.v1.json"
        )
        recipe_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "recipe.schema.v1.json"
        )
        fragment_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"
        )
        errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            self.assertNotIn("\ufffd", json.dumps(article, ensure_ascii=False))

            relations = article["relations"]
            targets = relations["related"] + relations["alternatives"]
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, re.MULTILINE)))
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|в современном мире|революционн|данная нода|является незаменим",
            )
            self.assertNotIn("\ufffd", body)

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("draft", recipe["editorial"]["state"])

            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )

        self.assertEqual([], errors)

    def test_research_records_are_honest(self) -> None:
        schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
        )
        for article_id, spec in ARTICLE_SPECS.items():
            path = catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            record = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(record, schema))
            self.assertEqual(article_id, record["articleId"])
            self.assertEqual(spec["classType"], record["node"]["classType"])
            self.assertEqual(spec["pythonModule"], record["node"]["pythonModule"])
            self.assertEqual("fact_checked", record["state"])
            self.assertEqual("automated_assisted", record["reviewMode"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["checks"]["exampleSchemaValidated"])
            self.assertTrue(record["knownGaps"])

    def test_runtime_fingerprints_list_flags_ports_and_settings(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual(spec["classType"], article["runtimeIdentity"]["classType"])
            self.assertEqual(runtime["python_module"], spec["pythonModule"])
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        batch = nodes["BatchLatentsNode"]
        autogrow = batch["input"]["required"]["latents"]
        self.assertEqual("COMFY_AUTOGROW_V3", autogrow[0])
        self.assertEqual("LATENT", autogrow[1]["template"]["input"]["required"]["latent"][0])
        self.assertEqual("latent", autogrow[1]["template"]["prefix"])
        self.assertEqual((1, 50), (autogrow[1]["template"]["min"], autogrow[1]["template"]["max"]))
        self.assertFalse(batch["is_input_list"])
        self.assertEqual([False], batch["output_is_list"])

        for class_type in ("RebatchLatents", "RebatchImages"):
            runtime = nodes[class_type]
            self.assertTrue(runtime["is_input_list"])
            self.assertEqual([True], runtime["output_is_list"])
            batch_size = runtime["input"]["required"]["batch_size"][1]
            self.assertEqual(
                {"default": 1, "min": 1, "max": 4096},
                batch_size,
            )

        audio = nodes["AudioConcat"]
        self.assertEqual(["AUDIO", "AUDIO", "COMBO"], [
            audio["input"]["required"][name][0]
            for name in ("audio1", "audio2", "direction")
        ])
        self.assertEqual(
            ["after", "before"],
            audio["input"]["required"]["direction"][1]["options"],
        )
        self.assertEqual("after", audio["input"]["required"]["direction"][1]["default"])
        self.assertFalse(audio["is_input_list"])
        self.assertEqual([False], audio["output_is_list"])

    def test_fragment_ports_connections_and_widget_values_match_runtime(self) -> None:
        runtime_nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))

        def input_spec(runtime: dict[str, Any], name: str) -> list[Any] | None:
            for group in ("required", "optional"):
                spec = runtime.get("input", {}).get(group, {}).get(name)
                if isinstance(spec, list):
                    return spec
            return None

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            refs = {node["ref"]: node for node in fragment["nodes"]}

            for node in fragment["nodes"]:
                runtime = runtime_nodes[node["classType"]]
                for setting, value in node["settings"].items():
                    spec = input_spec(runtime, setting)
                    self.assertIsNotNone(spec, f"{recipe_id}: unknown setting {setting}")
                    kind, options = spec[0], spec[1]
                    if kind == "COMBO":
                        self.assertIn(value, options["options"])
                    if kind in {"INT", "FLOAT"}:
                        self.assertGreaterEqual(value, options.get("min", value))
                        self.assertLessEqual(value, options.get("max", value))

            for external in fragment["externalInputs"]:
                target_runtime = runtime_nodes[refs[external["to"]]["classType"]]
                target_name = external["input"]
                spec = input_spec(target_runtime, target_name)
                if spec is None and "." in target_name:
                    group_name, child_name = target_name.split(".", 1)
                    autogrow = input_spec(target_runtime, group_name)
                    self.assertIsNotNone(autogrow, f"{recipe_id}: missing {group_name}")
                    self.assertEqual("COMFY_AUTOGROW_V3", autogrow[0])
                    template = autogrow[1]["template"]
                    prefix = template["prefix"]
                    self.assertRegex(child_name, rf"^{re.escape(prefix)}\d+$")
                    child_spec = template["input"]["required"]["latent"]
                    self.assertEqual(external["type"], child_spec[0])
                else:
                    self.assertIsNotNone(spec, f"{recipe_id}: unknown port {target_name}")
                    self.assertEqual(external["type"], spec[0])

            for connection in fragment["connections"]:
                source_runtime = runtime_nodes[refs[connection["from"]]["classType"]]
                target_runtime = runtime_nodes[refs[connection["to"]]["classType"]]
                output_names = source_runtime.get("output_name", source_runtime["output"])
                output_index = output_names.index(connection["output"])
                source_type = source_runtime["output"][output_index]
                target = input_spec(target_runtime, connection["input"])
                self.assertIsNotNone(target)
                self.assertEqual(source_type, target[0])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_articles_track_exact_pinned_implementation(self) -> None:
        rebatch = (SOURCE / "comfy_extras" / "nodes_rebatch.py").read_text(
            encoding="utf-8"
        )
        post = (SOURCE / "comfy_extras" / "nodes_post_processing.py").read_text(
            encoding="utf-8"
        )
        audio = (SOURCE / "comfy_extras" / "nodes_audio.py").read_text(
            encoding="utf-8"
        )
        replacements = (
            SOURCE / "comfy_extras" / "nodes_replacements.py"
        ).read_text(encoding="utf-8")

        self.assertIn("samples_out = latents[0].copy()", post)
        self.assertIn('samples_out["batch_index"] = []', post)
        self.assertIn("batch_latents(list(latents.values()))", post)
        self.assertIn("prefix=\"latent\", min=1, max=50", post)

        self.assertIn("is_input_list=True", rebatch)
        self.assertIn("io.Latent.Output(is_output_list=True)", rebatch)
        self.assertIn("io.Image.Output(is_output_list=True)", rebatch)
        self.assertIn("batch_size = batch_size[0]", rebatch)
        self.assertIn("torch.nn.functional.interpolate", rebatch)
        self.assertNotIn("mask = torch.nn.functional.interpolate", rebatch)
        self.assertIn("for img in images:", rebatch)
        self.assertIn("torch.cat(all_images[i:i+batch_size], dim=0)", rebatch)

        self.assertIn("torchaudio.functional.resample", audio)
        self.assertIn("waveform_1.repeat(1, 2, 1)", audio)
        self.assertIn("waveform_2.repeat(1, 2, 1)", audio)
        self.assertIn("torch.cat((waveform_1, waveform_2), dim=2)", audio)
        self.assertIn("torch.cat((waveform_2, waveform_1), dim=2)", audio)

        self.assertNotIn("RebatchAudio", replacements)
        self.assertNotIn("AudioFromBatch", replacements)
        self.assertNotIn("RebatchAudio", nodes_text := FULL_INVENTORY.read_text(encoding="utf-8"))
        self.assertNotIn('"AudioFromBatch":', nodes_text)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_full_official_census_and_exact_representative_topologies(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        records = load_official_node_records()
        by_type = Counter(
            record["node"].get("type")
            for record in records
            if record["node"].get("type")
            in {
                "BatchLatentsNode",
                "RebatchLatents",
                "RebatchImages",
                "AudioConcat",
                "RebatchAudio",
                "AudioFromBatch",
            }
        )
        self.assertEqual(0, by_type["BatchLatentsNode"])
        self.assertEqual(0, by_type["RebatchLatents"])
        self.assertEqual(1, by_type["RebatchImages"])
        self.assertEqual(1, by_type["AudioConcat"])
        self.assertEqual(0, by_type["RebatchAudio"])
        self.assertEqual(0, by_type["AudioFromBatch"])

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            dancer = json.loads(
                archive.read(
                    "comfyui_workflow_templates_json/templates/video_wan_dancer.json"
                ).decode("utf-8")
            )
            self.assertEqual("a92ccb88-3a14-4114-9b6b-fa8952839d39", dancer["id"])
            subgraph = dancer["definitions"]["subgraphs"][2]
            self.assertEqual("f7467834-35a6-42fe-b525-7f17383beb4f", subgraph["id"])
            self.assertEqual("Image to Video (Wan Dancer)", subgraph["name"])
            nodes = {node["id"]: node for node in subgraph["nodes"]}
            self.assertEqual("RebatchImages", nodes[671]["type"])
            self.assertEqual([4096], nodes[671]["widgets_values"])
            self.assertEqual("VAEDecode", nodes[658]["type"])
            self.assertEqual("CreateVideo", nodes[158]["type"])
            self.assertEqual([30, 8], nodes[158]["widgets_values"])
            links = {link["id"]: link for link in subgraph["links"]}
            self.assertEqual(
                (658, 0, 671, 0, "IMAGE"),
                tuple(links[1329][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")),
            )
            self.assertEqual(
                (671, 0, 158, 0, "IMAGE"),
                tuple(links[1330][key] for key in ("origin_id", "origin_slot", "target_id", "target_slot", "type")),
            )

            talk = json.loads(
                archive.read(
                    "comfyui_workflow_templates_json/templates/video_wan2_1_infinitetalk.json"
                ).decode("utf-8")
            )
            self.assertEqual("4795b4f0-7caa-4281-9a43-86d1770433f4", talk["id"])
            talk_nodes = {node["id"]: node for node in talk["nodes"]}
            self.assertEqual("AudioConcat", talk_nodes[113]["type"])
            self.assertEqual(["after"], talk_nodes[113]["widgets_values"])
            selected = [link for link in talk["links"] if link[0] in {430, 435, 440, 442}]
            self.assertEqual(
                [
                    [430, 113, 0, 138, 1, "AUDIO"],
                    [435, 113, 0, 140, 1, "AUDIO"],
                    [440, 24, 0, 113, 0, "AUDIO"],
                    [442, 90, 0, 113, 1, "AUDIO"],
                ],
                selected,
            )

    def test_audio_concat_is_scoped_replacement_not_runtime_alias(self) -> None:
        path = article_path(ARTICLE_SPECS["core.audio-concat"])
        article = catalog.load_json(path)
        body = (path.parent / "ru.md").read_text(encoding="utf-8")
        self.assertEqual([], article["runtimeIdentity"]["aliases"])
        self.assertIn("scoped replacement редакционной задачи", body)
        self.assertIn("не alias ноды и не запись Node Replacement API", body)


if __name__ == "__main__":
    unittest.main()
