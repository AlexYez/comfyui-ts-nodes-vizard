import sampleText from "../../../content/runtime/comfyui-0.32.0.object-info.sample.json?raw";
import { describe, expect, it } from "vitest";

import { decodeObjectInfo, parseObjectInfoText } from "./objectInfo";

describe("object_info fingerprints", () => {
  it("matches the Python golden fingerprints byte-for-byte", async () => {
    const nodes = await decodeObjectInfo(parseObjectInfoText(sampleText));
    expect(nodes.get("KSampler")?.schemaHash).toBe(
      "sha256:a1bb877a87dd7f5498755b2bd2f76d7552a519cccef83ccfa1a9e6c7834f64e6"
    );
    expect(nodes.get("CheckpointLoaderSimple")?.schemaHash).toBe(
      "sha256:e725e6fa7c42ae40496bd2b2f8d3eb063fe5051e6f2fb740a0d3614e453dc5f4"
    );
    expect(nodes.get("SaveImage")?.schemaHash).toBe(
      "sha256:30800abf24532254d235e86951334ea2a648d6fcaf0544d15adc37bcdf1073ac"
    );
    expect(nodes.get("KSampler")?.apiNode).toBe(false);
  });

  it("does not fingerprint installation-dependent combo choices", async () => {
    const changed = sampleText
      .replace('"example-a.safetensors", "example-b.safetensors"', '"private.safetensors"')
      .replace('"euler", "euler_ancestral", "dpmpp_2m"', '"future-sampler"');
    const before = await decodeObjectInfo(parseObjectInfoText(sampleText));
    const after = await decodeObjectInfo(parseObjectInfoText(changed));
    expect(after.get("CheckpointLoaderSimple")?.schemaHash).toBe(
      before.get("CheckpointLoaderSimple")?.schemaHash
    );
    expect(after.get("KSampler")?.schemaHash).toBe(before.get("KSampler")?.schemaHash);
  });

  it("preserves the live api_node flag independently of editorial content", async () => {
    const payload = parseObjectInfoText(sampleText) as Record<string, Record<string, unknown>>;
    if (payload.KSampler) payload.KSampler.api_node = true;
    const nodes = await decodeObjectInfo(payload);
    expect(nodes.get("KSampler")?.apiNode).toBe(true);
  });
});
