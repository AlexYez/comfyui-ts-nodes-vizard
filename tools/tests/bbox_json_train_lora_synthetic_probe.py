from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: bbox_json_train_lora_synthetic_probe.py <source>")
    source = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(source))

    import torch
    from comfy_api.latest import _io
    from comfy_extras import nodes_bounding_boxes as bbox
    from comfy_extras import nodes_json_prompt as json_prompt
    from comfy_extras import nodes_train as train

    boxes = [{
        "x": -10, "y": 20, "width": -30, "height": 40,
        "metadata": {
            "type": "text", "text": "Title", "desc": "Description",
            "palette": ["#ff0000", "#bad", "#00ff00", "#0000ff", "#ffffff", "#111111"],
        },
    }]
    regions = bbox.boxes_to_regions(boxes, 100, 100)
    frame = bbox.fractions_to_bbox_frame(regions, 100, 100)
    elements = bbox.build_elements(regions)
    converted = bbox.elements_to_boxes(
        [{"type": "text", "bbox": [100, -100, 1200, 800], "text": "T", "desc": "D", "color_palette": ["#abc"]}],
        100, 200,
    )
    single_box = {"x": 1, "y": 2, "width": 3, "height": 4}
    later_box = {"x": 91, "y": 92, "width": 5, "height": 6}
    nested_frames = [[single_box], [later_box]]
    input_formats = {
        "dict": bbox.boxes_from_input(single_box, 100, 100),
        "dictJson": bbox.boxes_from_input(json.dumps(single_box), 100, 100),
        "nested": bbox.boxes_from_input(nested_frames, 100, 100),
        "nestedJson": bbox.boxes_from_input(json.dumps(nested_frames), 100, 100),
    }
    background = torch.empty((2, 2, 3, 3), dtype=torch.float32)
    background[0].fill_(0.25)
    background[1].fill_(0.75)
    background_first_pixel = list(bbox._bg_from_image(background).getpixel((0, 0)))
    first = bbox.CreateBoundingBoxes.execute(100, 100, [], [], None, boxes)
    editor = [{"x": 10, "y": 10, "width": 10, "height": 10}]
    second = bbox.CreateBoundingBoxes.execute(100, 100, editor, boxes, None, boxes)
    empty = bbox.CreateBoundingBoxes.execute(100, 100, editor, [], None, [])

    def build(style, description="title", palette=None):
        return json_prompt.BuildJsonPromptIdeogram.execute(
            [{"type": "obj"}], style, description, "bg", "mood", "rim",
            "photograph", palette or [],
        ).args[0]

    json_results = {
        "none": build({"style": "none"}, "  title  ", ["#abc"]),
        "photo": build({"style": "photo", "photo": "35mm"}, palette=["#abc", "", 12, "bad"]),
        "art": build({"style": "art_style", "art_style": "ink"}),
        "string": build("photo", "", ["#fff"]),
    }

    flat_prompt_inputs = {
        "element": [{"type": "obj"}],
        "high_level_description": "title",
        "background": "bg",
        "style": "photo",
        "style.photo": "editorial",
        "aesthetics": "mood",
        "lighting": "rim",
        "medium": "photograph",
        "color_palette": ["#fff"],
    }
    finalized, hidden, v3_data = _io.get_finalized_class_inputs(
        json_prompt.BuildJsonPromptIdeogram.INPUT_TYPES(), flat_prompt_inputs
    )
    materialized = _io.build_nested_inputs(flat_prompt_inputs, v3_data)
    materialized_result = json_prompt.BuildJsonPromptIdeogram.execute(
        materialized["element"], materialized["style"],
        materialized["high_level_description"], materialized["background"],
        materialized["aesthetics"], materialized["lighting"],
        materialized["medium"], materialized["color_palette"],
    ).args[0]
    nested_prompt_inputs = dict(flat_prompt_inputs)
    nested_prompt_inputs["style"] = {"style": "photo", "photo": "editorial"}
    nested_prompt_inputs.pop("style.photo")
    nested_finalized, nested_hidden, nested_v3_data = _io.get_finalized_class_inputs(
        json_prompt.BuildJsonPromptIdeogram.INPUT_TYPES(), nested_prompt_inputs
    )

    latent_a = {"samples": torch.zeros((2, 4, 8, 8))}
    latent_b = {"samples": torch.ones((1, 4, 8, 8))}
    latent_c = {"samples": torch.ones((1, 4, 6, 8))}
    one = train._process_latents_standard_mode([latent_a])
    equal = train._process_latents_standard_mode([latent_a, latent_b])
    unequal = train._process_latents_standard_mode([latent_b, latent_c])
    equal_prep = train._prepare_latents_and_count(equal, torch.float32, False)
    unequal_prep = train._prepare_latents_and_count(unequal, torch.float32, False)
    expanded = train._validate_and_expand_conditioning([["caption"]], 3, False)
    bucket_latents = train._process_latents_bucket_mode([latent_a, latent_c])
    bucket_prep = train._prepare_latents_and_count(bucket_latents, torch.float32, True)
    bucket_conditioning = train._validate_and_expand_conditioning([["only"]], 3, True)
    mismatch = None
    try:
        train._validate_and_expand_conditioning([["one"], ["two"]], 3, False)
    except Exception as exc:
        mismatch = type(exc).__name__

    class Sampling:
        @staticmethod
        def percent_to_sigma(value):
            return value

    class Inner:
        model_sampling = Sampling()

    class ModelWrap:
        inner_model = Inner()

    class Noise:
        @staticmethod
        def generate_noise(latent):
            return torch.zeros_like(latent["samples"])

    class Progress:
        postfix = None

        def set_postfix(self, value):
            self.postfix = value

    bucket_losses = []
    sampler = train.TrainSampler(
        lambda *_args: torch.tensor(0.0), object(),
        loss_callback=bucket_losses.append, batch_size=2, seed=7,
        training_dtype=torch.float32, bucket_latents=bucket_prep[0],
    )
    bucket_call = {}

    def fake_fwd_bwd(
        model_wrap, batch_sigmas, batch_noise, batch_latent, cond,
        indicies, extra_args, dataset_size, bwd=True,
    ):
        bucket_call.update({
            "batchShape": list(batch_latent.shape),
            "indices": indicies,
            "datasetSize": dataset_size,
            "bwd": bwd,
            "sigmaCount": len(batch_sigmas),
            "noiseIsZero": bool(torch.count_nonzero(batch_noise) == 0),
            "conditionCount": len(cond),
            "extraArgs": extra_args,
        })
        return torch.tensor(0.25)

    sampler.fwd_bwd = fake_fwd_bwd
    progress = Progress()
    rng_state = torch.random.get_rng_state()
    try:
        torch.manual_seed(20260814)
        sampler._train_step_bucket_mode(
            ModelWrap(), ["c0", "c1", "c2"], {"tag": "probe"},
            Noise(), torch.zeros((), dtype=torch.float32), progress,
        )

        sampler.seed = 1
        torch.manual_seed(4242)
        sigmas_seed_1 = sampler._generate_batch_sigmas(ModelWrap(), 3, torch.device("cpu"))
        sampler.seed = 999
        torch.manual_seed(4242)
        sigmas_seed_999 = sampler._generate_batch_sigmas(ModelWrap(), 3, torch.device("cpu"))

        weight = torch.zeros((4, 4), dtype=torch.float32)
        torch.manual_seed(101)
        adapter_a = train.adapter_maps["LoRA"].create_train(weight, rank=2, alpha=1.0)
        torch.manual_seed(101)
        adapter_b = train.adapter_maps["LoRA"].create_train(weight, rank=2, alpha=1.0)
        torch.manual_seed(102)
        adapter_c = train.adapter_maps["LoRA"].create_train(weight, rank=2, alpha=1.0)
        adapter_same_global_rng = torch.equal(adapter_a.lora_up.weight, adapter_b.lora_up.weight)
        adapter_changed_global_rng = not torch.equal(adapter_a.lora_up.weight, adapter_c.lora_up.weight)
    finally:
        torch.random.set_rng_state(rng_state)

    original_standard = train.comfy.sd.load_lora_for_models
    original_bypass = train.comfy.sd.load_bypass_lora_for_models
    calls = []

    def route(kind, result):
        def inner(model, clip, lora, strength_model, strength_clip):
            calls.append({
                "kind": kind, "clip": clip, "strength_model": strength_model,
                "strength_clip": strength_clip,
            })
            return result, None
        return inner

    train.comfy.sd.load_lora_for_models = route("standard", "standard-model")
    train.comfy.sd.load_bypass_lora_for_models = route("bypass", "bypass-model")
    model = object()
    try:
        zero = train.LoraModelLoader.execute(model, {"w": 1}, 0, False).args[0]
        regular = train.LoraModelLoader.execute(model, {"w": 1}, 0.5, False).args[0]
        bypass = train.LoraModelLoader.execute(model, {"w": 1}, -2.0, True).args[0]
    finally:
        train.comfy.sd.load_lora_for_models = original_standard
        train.comfy.sd.load_bypass_lora_for_models = original_bypass

    print(json.dumps({
        "bbox": {
            "frame": frame, "elements": elements, "converted": converted,
            "inputFormats": input_formats,
            "backgroundFirstPixel": background_first_pixel,
            "previewShape": list(first.args[0].shape),
            "incoming": first.args[1], "editor": second.args[1],
            "empty": empty.args[1], "uiIncoming": "input_bboxes" in first.ui,
        },
        "json": json_results | {
            "v3FlatFinalRequired": sorted(finalized["required"]),
            "v3FlatHidden": hidden,
            "v3FlatPaths": v3_data.get("dynamic_paths", {}),
            "v3MaterializedStyle": materialized["style"],
            "v3MaterializedResult": materialized_result,
            "v3NestedFinalRequired": sorted(nested_finalized["required"]),
            "v3NestedHidden": nested_hidden,
            "v3NestedPaths": nested_v3_data.get("dynamic_paths", {}),
        },
        "train": {
            "oneShape": list(one.shape),
            "equalShapes": [list(item.shape) for item in equal],
            "unequalShapes": [list(item.shape) for item in unequal],
            "equalPrepared": [list(equal_prep[0].shape), equal_prep[1], equal_prep[2]],
            "unequalPrepared": [len(unequal_prep[0]), unequal_prep[1], unequal_prep[2]],
            "expanded": len(expanded), "mismatch": mismatch,
            "bucketShapes": [list(item.shape) for item in bucket_latents],
            "bucketPrepared": [
                [list(item.shape) for item in bucket_prep[0]], bucket_prep[1], bucket_prep[2]
            ],
            "bucketConditioning": bucket_conditioning,
            "bucketOffsets": sampler.bucket_offsets,
            "bucketWeights": sampler.bucket_weights.tolist(),
            "bucketCall": bucket_call,
            "bucketLosses": bucket_losses,
            "bucketPostfix": progress.postfix,
            "nodeSeedIgnoredForSigmas": torch.equal(sigmas_seed_1, sigmas_seed_999),
            "adapterSameGlobalRng": adapter_same_global_rng,
            "adapterChangedGlobalRng": adapter_changed_global_rng,
            "noneExisting": train._load_existing_lora("[None]"),
        },
        "loader": {
            "zeroIdentity": zero is model, "regular": regular,
            "bypass": bypass, "calls": calls,
        },
    }, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
