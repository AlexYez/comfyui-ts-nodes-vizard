from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter,defaultdict
from tools import catalog
SPECS={'core.triposplat-preprocess-image':('triposplat-preprocess-image','TripoSplatPreprocessImage','sha256:34a9bc1193d130e7607341fb2189145c575e443eb49f487f2a56c3bb4846e2c5'),'core.triposplat-conditioning':('triposplat-conditioning','TripoSplatConditioning','sha256:d66203c5200494ad9546489b84738fee0ff4bd76f1549b4c2d3a53a4aa4d3a2d'),'core.vae-decode-triposplat':('vae-decode-triposplat','VAEDecodeTripoSplat','sha256:c3912e68bc473b495fbb79ab0b001c6b84452b00901626c7452f6a915c5ea378'),'core.triposplat-sampling-preview':('triposplat-sampling-preview','TripoSplatSamplingPreview','sha256:0c5bc17fcaa44801f062faa3698302301047d661566de33478fb7b3be453da0e')}
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  a_s=catalog.load_json(catalog.CONTENT/'schemas/article.schema.v1.json');r_s=catalog.load_json(catalog.CONTENT/'schemas/article-research.schema.v1.json');rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,a_s));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,r_s));self.assertFalse(q['checks']['exampleExecuted'])
  self.assertEqual([],e)
 def test_source(self):
  p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_triposplat.py';self.assertEqual('24d4fa4dea56cb8b53b37917e74faa2705215a111dfa6ab8d5cdcdb806c2c22f',hashlib.sha256(p.read_bytes()).hexdigest());s=p.read_text('utf8');self.assertIn('max(x1 - x0, y1 - y0) / 2 * 1.2',s);self.assertIn('_Q_TOKEN_LENGTH = 8192',s);self.assertIn('NestedTensor((latent_seq, camera))',s);self.assertIn('torch.Generator(device="cpu").manual_seed(seed)',s);self.assertIn('preview failed, disabling',s);self.assertIn('cb_idx = 5',s)
 def test_official_pipeline_presets(self):
  wanted={'TripoSplatPreprocessImage','TripoSplatConditioning','VAEDecodeTripoSplat','TripoSplatSamplingPreview'};counts=Counter();widgets=defaultdict(list);files=roots=subgraphs=nodes=0;target_links=[]
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
     if any(node.get('type')=='TripoSplatConditioning' for node in graph_nodes):target_links.extend((link['origin_id'],link['origin_slot'],link['target_id'],link['target_slot'],link['type']) for link in graph.get('links',[]))
     for node in graph_nodes:
      if node.get('type') in wanted:counts[node['type']]+=1;widgets[node['type']].append(node.get('widgets_values',[]))
  self.assertEqual((512,496,272,8120),(files,roots,subgraphs,nodes));self.assertEqual(Counter({name:1 for name in wanted}),counts);self.assertEqual([[1,1024]],widgets['TripoSplatPreprocessImage']);self.assertEqual([[5,16384,90,15,2]],widgets['TripoSplatSamplingPreview']);self.assertEqual(262144,widgets['VAEDecodeTripoSplat'][0][0]);self.assertEqual('fixed',widgets['VAEDecodeTripoSplat'][0][2])
  for expected in [(24,0,6,1,'CONDITIONING'),(24,1,6,2,'CONDITIONING'),(24,2,6,3,'LATENT'),(6,0,55,0,'LATENT')]:self.assertIn(expected,target_links)
if __name__=='__main__':unittest.main()
