from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter,defaultdict
from tools import catalog
SPECS={'core.empty-ace-step-latent-audio':('empty-ace-step-latent-audio','EmptyAceStepLatentAudio','sha256:8ce019ee93c0c0758ac1c71ff5be08e805d8d7795abb054ef259b73d61b414ef'),'core.empty-ace-step-15-latent-audio':('empty-ace-step-15-latent-audio','EmptyAceStep1.5LatentAudio','sha256:abf0aab7dd5724a65821cea948027226caed86fbed8b3a4f8ec10fdfb28bb536'),'core.reference-timbre-audio':('reference-timbre-audio','ReferenceTimbreAudio','sha256:03ef10071e4817c6925ebf3989067ed4f6fa34c921229fab54c1fbd7bb8ef0a6'),'core.empty-mochi-latent-video':('empty-mochi-latent-video','EmptyMochiLatentVideo','sha256:fa751832f6b4bf28818c73a339cdc1f96e105922bc57b8b869fc85c4891d754a')}
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  a_schema=catalog.load_json(catalog.CONTENT/'schemas/article.schema.v1.json');r_schema=catalog.load_json(catalog.CONTENT/'schemas/article-research.schema.v1.json');rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));errs=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,a_schema));catalog.validate_article(p,a,errs);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,r_schema));self.assertFalse(q['checks']['exampleExecuted'])
  self.assertEqual([],errs)
 def test_sources(self):
  ace=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_ace.py';mochi=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_mochi.py';self.assertEqual('9f3142cb53801a25fd214388b4852c578ad71ac58d557884833175b0d02a7bfd',hashlib.sha256(ace.read_bytes()).hexdigest());self.assertEqual('cb7510b31685b91334b6a01383a482138cfe79515f812edd4668e566180ca2e3',hashlib.sha256(mochi.read_bytes()).hexdigest());s=ace.read_text('utf8');self.assertIn('[batch_size, 8, 16, length]',s);self.assertIn('[batch_size, 64, length]',s);self.assertIn('reference_audio_timbre_latents',s);self.assertIn('((length - 1) // 6) + 1',mochi.read_text('utf8'))
 def test_formulas(self):
  self.assertEqual(1291,int(120*44100/512/8));self.assertEqual(3000,round(120*48000/1920));self.assertEqual((1,12,5,60,106),(1,12,((25-1)//6)+1,480//8,848//8))
 def test_mochi_has_no_official_case(self):
  files=roots=subgraphs=nodes=hits=0
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
     graph_nodes=graph.get('nodes',[]);nodes+=len(graph_nodes);hits+=sum(node.get('type')=='EmptyMochiLatentVideo' for node in graph_nodes)
  self.assertEqual((512,496,272,8120,0),(files,roots,subgraphs,nodes,hits))
 def test_ace_official_presets(self):
  wanted={'TextEncodeAceStepAudio','EmptyAceStepLatentAudio','EmptyAceStep1.5LatentAudio','ReferenceTimbreAudio'};counts=Counter();widgets=defaultdict(list)
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
      if node.get('type') in wanted:counts[node['type']]+=1;widgets[node['type']].append(node.get('widgets_values',[]))
  self.assertEqual(Counter({'EmptyAceStep1.5LatentAudio':7,'TextEncodeAceStepAudio':3,'EmptyAceStepLatentAudio':2}),counts);self.assertEqual(Counter({(120,1):7}),Counter(map(tuple,widgets['EmptyAceStep1.5LatentAudio'])));self.assertEqual(Counter({(30,1):1,(120,1):1}),Counter(map(tuple,widgets['EmptyAceStepLatentAudio'])));self.assertTrue(all(abs(v[-1]-0.99)<1e-12 for v in widgets['TextEncodeAceStepAudio']));self.assertEqual(0,counts['ReferenceTimbreAudio'])
if __name__=='__main__':unittest.main()
