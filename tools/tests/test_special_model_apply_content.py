from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter
from tools import catalog
SPECS={'core.anima-lllite-apply':('anima-lllite-apply','AnimaLLLiteApply','sha256:1137b192ff47cd1233822e495973ab544b6c85297bd116ec55d57b3403fd77ad'),'core.controlnet-inpainting-alimama-apply':('controlnet-inpainting-alimama-apply','ControlNetInpaintingAliMamaApply','sha256:bcd89c4f94f3d6ecc0ff48eedbbf13b9a9641cbecc1329fe7eaa86998b7d93e5'),'core.qwen-image-diffsynth-controlnet':('qwen-image-diffsynth-controlnet','QwenImageDiffsynthControlnet','sha256:814683aed1ade132b5f42056b9acfe585e7379d1fb93d3070dc842fde7d999a4'),'core.supir-apply':('supir-apply','SUPIRApply','sha256:a2f3d66f21f4a574520bbecd77454dcaf3bc728d7ca48d63d10aea497b90a265')}
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  a_s=catalog.load_json(catalog.CONTENT/'schemas/article.schema.v1.json');r_s=catalog.load_json(catalog.CONTENT/'schemas/article-research.schema.v1.json');rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,a_s));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,r_s));self.assertFalse(q['checks']['exampleExecuted'])
  self.assertEqual([],e)
 def test_sources(self):
  m=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_model_patch.py';c=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_controlnet.py';self.assertEqual('f8fd8b9281e8926536c71867ccf1529a41fe690ba2ed12db8f58251ba32cbc76',hashlib.sha256(m.read_bytes()).hexdigest());self.assertEqual('42ab7998d31232310bfebfde1363f3b0eedbb868b3fde5dec8724293bd28d69a',hashlib.sha256(c.read_bytes()).hexdigest());s=m.read_text('utf8');self.assertIn('set_model_attn1_patch',s);self.assertIn('ZImageControlPatch',s);self.assertIn('denoised - d_center * ((sigma_val / sigma_max) ** restore_cfg)',s);u=c.read_text('utf8');self.assertIn('if control_net.concat_mask:',u);self.assertIn('extra_concat=extra_concat',u)
 def test_official_workflow_census(self):
  wanted={v[1] for v in SPECS.values()};counts=Counter();widgets=Counter();files=roots=subgraphs=nodes_total=0
  def scopes(value):
   if isinstance(value,list):
    for item in value:yield from scopes(item)
   elif isinstance(value,dict):
    if isinstance(value.get('nodes'),list):yield value
    definitions=value.get('definitions')
    if isinstance(definitions,dict):
     for item in definitions.get('subgraphs',[]):yield from scopes(item)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as archive:
   for name in archive.namelist():
    if not name.endswith('.json'):continue
    files+=1;all_scopes=list(scopes(json.loads(archive.read(name))));roots+=bool(all_scopes);subgraphs+=max(0,len(all_scopes)-1)
    for graph in all_scopes:
     nodes=graph.get('nodes',[]);nodes_total+=len(nodes)
     for node in nodes:
      node_type=node.get('type')
      if node_type in wanted:counts[node_type]+=1;widgets[(node_type,tuple(node.get('widgets_values',[])))]+=1
  self.assertEqual((512,496,272,8120),(files,roots,subgraphs,nodes_total))
  self.assertEqual(Counter({'AnimaLLLiteApply':3,'ControlNetInpaintingAliMamaApply':2,'QwenImageDiffsynthControlnet':2}),counts)
  self.assertEqual(3,widgets[('AnimaLLLiteApply',(1,0,1))]);self.assertEqual(2,widgets[('ControlNetInpaintingAliMamaApply',(1,0,1))]);self.assertEqual(2,widgets[('QwenImageDiffsynthControlnet',(1,))]);self.assertEqual(0,counts['SUPIRApply'])
if __name__=='__main__':unittest.main()
