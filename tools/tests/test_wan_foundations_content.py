from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from tools import catalog
SPECS={'core.zimage-fun-controlnet':('zimage-fun-controlnet','ZImageFunControlnet','sha256:31a6b6a894e3ba524586c4fb9313902eeb191f96d98ebfc11bfeef48983668dc'),'core.wan-uni3c-controlnet-apply':('wan-uni3c-controlnet-apply','WanUni3CControlnetApply','sha256:296a8f1ff0033c580c7ac43e8cc5324600f02a4b8fa35bc8324b59daec5e817c'),'core.wan-block-swap':('wan-block-swap','wanBlockSwap','sha256:ea684b080384463f63722d7249f7e1607c356ef945c81aacd1a990f5a76b2d9e'),'core.wan22-image-to-video-latent':('wan22-image-to-video-latent','Wan22ImageToVideoLatent','sha256:7b00c84a8499bdf381548aa7f02e404b0a5673ddb8c5fddffffa0b8e3f161e06')}
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  a_s=catalog.load_json(catalog.CONTENT/'schemas/article.schema.v1.json');r_s=catalog.load_json(catalog.CONTENT/'schemas/article-research.schema.v1.json');rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,a_s));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,r_s));self.assertFalse(q['checks']['exampleExecuted'])
  self.assertEqual([],e)
 def test_sources(self):
  b=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras';self.assertEqual('7e8a30122864d2fc65b4bd4df881f244f22690ef985391c9b6c468886f17c14c',hashlib.sha256((b/'nodes_nop.py').read_bytes()).hexdigest());self.assertEqual('f8fd8b9281e8926536c71867ccf1529a41fe690ba2ed12db8f58251ba32cbc76',hashlib.sha256((b/'nodes_model_patch.py').read_bytes()).hexdigest());self.assertEqual('39ff111cc45c8d2a75cab1aa3b97ad9bf9037868178af2468bc52b34dbd0d96d',hashlib.sha256((b/'nodes_wan.py').read_bytes()).hexdigest());n=(b/'nodes_nop.py').read_text('utf8');self.assertIn('return io.NodeOutput(model)',n);m=(b/'nodes_model_patch.py').read_text('utf8');self.assertIn('not a Uni3C ControlNet',m);self.assertIn('model_dim != cnet_dim',m);self.assertIn('if self.image is not None and self.inpaint_image is not None:',m);self.assertIn('torch.ones_like(control_image) * 0.5',m);self.assertIn('set_model_noise_refiner_patch(patch)',m);w=(b/'nodes_wan.py').read_text('utf8');self.assertIn('[1, 48, ((length - 1) // 4) + 1',w);self.assertIn('if start_image is None:',w)
 def test_zimage_fun_and_wan_block_swap_have_no_official_case(self):
  files=roots=subgraphs=nodes=0;hits={'ZImageFunControlnet':0,'wanBlockSwap':0}
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
     graph_nodes=graph.get('nodes',[]);nodes+=len(graph_nodes)
     for node in graph_nodes:
      if node.get('type') in hits:hits[node.get('type')]+=1
  self.assertEqual((512,496,272,8120),(files,roots,subgraphs,nodes));self.assertEqual({'ZImageFunControlnet':0,'wanBlockSwap':0},hits)
if __name__=='__main__':unittest.main()
