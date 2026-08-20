from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter
from typing import Any,Iterator
from tools import catalog
SPECS={'core.void-inpaint-conditioning':('void-inpaint-conditioning','VOIDInpaintConditioning','sha256:97f8cb342598113e9b8f8de97d75dde1ec4ff13427755a36817532a1b46ddf11'),'core.void-warped-noise':('void-warped-noise','VOIDWarpedNoise','sha256:4262ffce0303055f25e27072d73f79000921e5cdcdd9dc7357de3e5259ba6ac4'),'core.void-warped-noise-source':('void-warped-noise-source','VOIDWarpedNoiseSource','sha256:7928504cc1f44e3efd02ff7ddb2ca2e77b1352b0393b8bd939aac508741715af'),'core.set-union-controlnet-type':('set-union-controlnet-type','SetUnionControlNetType','sha256:50e00be58396a45d20a823943f56772fd35290a4ed21fb097a7b0f1e7214a364')}
def scopes(value:Any)->Iterator[dict[str,Any]]:
 if isinstance(value,list):
  for item in value:yield from scopes(item)
 elif isinstance(value,dict):
  if isinstance(value.get('nodes'),list):yield value
  definitions=value.get('definitions')
  if isinstance(definitions,dict):
   for item in definitions.get('subgraphs',[]):yield from scopes(item)
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  a_s=catalog.load_json(catalog.CONTENT/'schemas/article.schema.v1.json');r_s=catalog.load_json(catalog.CONTENT/'schemas/article-research.schema.v1.json');rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,a_s));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,r_s));self.assertFalse(q['checks']['exampleExecuted'])
  self.assertEqual([],e)
 def test_sources(self):
  v=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_void.py';c=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_controlnet.py';self.assertEqual('242dcd84baf0a7934cd3c980f01d6c73992abc7f4b2e18d87712619a7425af90',hashlib.sha256(v.read_bytes()).hexdigest());self.assertEqual('42ab7998d31232310bfebfde1363f3b0eedbb868b3fde5dec8724293bd28d69a',hashlib.sha256(c.read_bytes()).hexdigest());s=v.read_text('utf8');self.assertIn('latent_t % PATCH_SIZE_T == 0',s);self.assertIn('torch.cat([mask_latents, masked_video_latents], dim=1)',s);self.assertIn('lat[:, :, -1:].repeat',s);self.assertIn('(vid.clamp(0, 1) * 255).to(torch.uint8)',s);self.assertIn('torch.linspace(0, warped.shape[0] - 1, latent_t',s);self.assertIn('warped_tensor.repeat(batch_size, 1, 1, 1, 1)',s);self.assertIn('return self._samples.clone().cpu()',s);u=c.read_text('utf8');self.assertIn('UNION_CONTROLNET_TYPES.get(type, -1)',u);self.assertIn('set_extra_arg("control_type", [])',u)
 def test_official_void_topology(self):
  wanted={'VOIDInpaintConditioning','VOIDWarpedNoise','VOIDWarpedNoiseSource'};counts=Counter();widgets={};edges=[]
  wheel=catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl'
  with zipfile.ZipFile(wheel) as archive:
   for name in archive.namelist():
    if not name.endswith('.json'):continue
    for graph in scopes(json.loads(archive.read(name))):
     nodes={node.get('id'):node for node in graph.get('nodes',[]) if isinstance(node,dict)}
     for node in nodes.values():
      if node.get('type') in wanted:counts[node['type']]+=1;widgets[node['type']]=node.get('widgets_values',[])
     for link in graph.get('links',[]):
      if isinstance(link,dict):
       source=nodes.get(link.get('origin_id'));target=nodes.get(link.get('target_id'))
       if source and target:edges.append((source.get('type'),link.get('type'),target.get('type')))
  self.assertEqual(Counter({'VOIDInpaintConditioning':1,'VOIDWarpedNoise':1,'VOIDWarpedNoiseSource':1}),counts)
  self.assertEqual([672,384,45,1],widgets['VOIDInpaintConditioning']);self.assertEqual([672,384,45,1],widgets['VOIDWarpedNoise']);self.assertEqual([],widgets['VOIDWarpedNoiseSource'])
  self.assertIn(('OpticalFlowLoader','OPTICAL_FLOW','VOIDWarpedNoise'),edges);self.assertIn(('VOIDWarpedNoise','LATENT','VOIDWarpedNoiseSource'),edges);self.assertIn(('VOIDWarpedNoiseSource','NOISE','SamplerCustomAdvanced'),edges)
if __name__=='__main__':unittest.main()
