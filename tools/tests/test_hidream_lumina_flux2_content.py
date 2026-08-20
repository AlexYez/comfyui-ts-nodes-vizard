from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter
from tools import catalog

SPECS={
 'core.clip-text-encode-hidream':('clip-text-encode-hidream','CLIPTextEncodeHiDream','sha256:73304a2be3ca78ebf0bcfd81ebcb37c6452dcb1f628538b9846e5c3751ec1c9b'),
 'core.quadruple-clip-loader':('quadruple-clip-loader','QuadrupleCLIPLoader','sha256:ebc6fda23a59818d0728c378fd66324382e13637914d60f24844258cbb7550fc'),
 'core.clip-text-encode-lumina2':('clip-text-encode-lumina2','CLIPTextEncodeLumina2','sha256:40902b0325b32b3e6f66407565ad23178cfa464c4b8a279313b3ab22e2bf6481'),
 'core.empty-flux2-latent-image':('empty-flux2-latent-image','EmptyFlux2LatentImage','sha256:3491361064ba214bf7a422652ec8b8dc34d40c8e8502dba33c971371eb5b7622')}
HASHES={'nodes_hidream.py':'ab676963cfde9b84be85dae4b54c52705b2be29e2fdaf74f3d148e6f9bfe74d5','nodes_lumina2.py':'bb063ae99325a615528628b2420805f81f49b3768074c215f403d035e2733a0f','nodes_flux.py':'a4917fd9d4aed2afdbdfc005a527b6381be942200054d7998477a16987e7aff9'}
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  schema=catalog.load_json(catalog.CONTENT/'schemas/article.schema.v1.json'); research=catalog.load_json(catalog.CONTENT/'schemas/article-research.schema.v1.json'); rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json')); errors=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json'; data=catalog.load_json(p); self.assertEqual([],catalog.json_schema_errors(data,schema)); catalog.validate_article(p,data,errors); self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M))); self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct])); ledger=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json'); self.assertEqual([],catalog.json_schema_errors(ledger,research)); self.assertFalse(ledger['checks']['exampleExecuted'])
  self.assertEqual([],errors)
 def test_sources(self):
  base=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras'
  for name,digest in HASHES.items(): self.assertEqual(digest,hashlib.sha256((base/name).read_bytes()).hexdigest())
  hid=(base/'nodes_hidream.py').read_text('utf8'); self.assertIn('tokens["llama"]',hid); self.assertIn('ckpt_paths=[clip_path1, clip_path2, clip_path3, clip_path4]',hid)
  lum=(base/'nodes_lumina2.py').read_text('utf8'); self.assertIn("<Prompt Start>",lum); self.assertIn('if clip is None:',lum)
  flux=(base/'nodes_flux.py').read_text('utf8'); self.assertIn('[batch_size, 128, height // 16, width // 16]',flux)
 def test_runtime_ports(self):
  rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'))
  self.assertEqual(['clip','clip_l','clip_g','t5xxl','llama'],rt['CLIPTextEncodeHiDream']['input_order']['required'])
  self.assertEqual(['superior','alignment'],rt['CLIPTextEncodeLumina2']['input']['required']['system_prompt'][1]['options'])
  self.assertEqual(128,128); self.assertEqual(16,rt['EmptyFlux2LatentImage']['input']['required']['width'][1]['step'])
 def test_flux2_official_presets(self):
  presets=Counter();files=roots=subgraphs=nodes=0
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
      if node.get('type')=='EmptyFlux2LatentImage':presets[tuple(node.get('widgets_values',[]))]+=1
  self.assertEqual((512,496,272,8120),(files,roots,subgraphs,nodes));self.assertEqual(Counter({(1024,1024,1):19,(1248,832,1):2}),presets)
 def test_hidream_loader_orders_and_lumina_absence(self):
  loaders=[];lumina=0
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
    for graph in scopes(json.loads(archive.read(name))):
     for node in graph.get('nodes',[]):
      if node.get('type')=='QuadrupleCLIPLoader':loaders.append(tuple(node.get('widgets_values',[])))
      if node.get('type')=='CLIPTextEncodeLumina2':lumina+=1
  self.assertEqual(5,len(loaders));self.assertEqual(Counter({('clip_l_hidream.safetensors','clip_g_hidream.safetensors'):3,('clip_g_hidream.safetensors','clip_l_hidream.safetensors'):2}),Counter(x[:2] for x in loaders));self.assertTrue(all(x[2:] == ('t5xxl_fp8_e4m3fn_scaled.safetensors','llama_3.1_8b_instruct_fp8_scaled.safetensors') for x in loaders));self.assertEqual(0,lumina)
if __name__=='__main__': unittest.main()
