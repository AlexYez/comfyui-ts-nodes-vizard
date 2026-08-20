from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter
from tools import catalog
SPECS={'core.easy-cache':('easy-cache','EasyCache','sha256:a5dad6047859ec7278ba85445396d43d2e6fc0efdee38d21265a017e9949f22c'),'core.lazy-cache':('lazy-cache','LazyCache','sha256:67c82452864b2f4eb9fc6da08d048ce2052123a95596da81afa92d2c4523f124'),'core.flux-kv-cache':('flux-kv-cache','FluxKVCache','sha256:edb15a787a726e1fb73df727eb0344defd753e95c0c8194053b6263d09d79c62'),'core.wan-animate2-cache':('wan-animate2-cache','WanAnimate2Cache','sha256:bd980d80a11ef5410b726b91994a704f3441c20ab7a7470be7b49eb7a4291ca9')}
HASHES={'nodes_easycache.py':'a76d70b1c131bd5afbea2674db4ee6fd04af33ebd92f7cd486b9ea8347036f9d','nodes_flux.py':'a4917fd9d4aed2afdbdfc005a527b6381be942200054d7998477a16987e7aff9','nodes_wan.py':'39ff111cc45c8d2a75cab1aa3b97ad9bf9037868178af2468bc52b34dbd0d96d'}
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  a_s=catalog.load_json(catalog.CONTENT/'schemas/article.schema.v1.json');r_s=catalog.load_json(catalog.CONTENT/'schemas/article-research.schema.v1.json');rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,a_s));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,r_s));self.assertFalse(q['checks']['exampleExecuted'])
  self.assertEqual([],e)
 def test_sources(self):
  base=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras'
  for n,h in HASHES.items():self.assertEqual(h,hashlib.sha256((base/n).read_bytes()).hexdigest())
  e=(base/'nodes_easycache.py').read_text('utf8');self.assertIn('subsample_factor=8',e);self.assertIn('uuid_cache_diffs',e);self.assertIn('self.cache_diff = output - x',e);self.assertIn('WrappersMP.PREDICT_NOISE',e)
  self.assertIn('metadata = (x.device, x.dtype, x.shape)',e);self.assertIn('return x + self.cache_diff.to(x.device)',e);self.assertIn('easycache.reset()',e);self.assertIn('percent_to_sigma(self.start_percent)',e)
  f=(base/'nodes_flux.py').read_text('utf8');self.assertIn('reference_image_num_tokens',f);self.assertIn('index_timestep_zero',f);self.assertIn('cache_key = "{}_{}".format(extra_options["block_type"], extra_options["block_index"])',f);self.assertIn('repeat_to_batch_size(kk, k.shape[0])',f);self.assertIn('self.cache[cache_key] = (k[:, :, -ref_toks:].clone(), v[:, :, -ref_toks:].clone())',f)
  w=(base/'nodes_wan.py').read_text('utf8');self.assertIn('PoseBranchCache',w);self.assertIn('ON_CLEANUP',w);self.assertIn('cache.free()',w)
 def test_official_cache_presets(self):
  counts=Counter();widgets=Counter();modes=Counter();members=Counter();files=roots=subgraphs=nodes=0
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
      kind=node.get('type')
      if kind not in {'EasyCache','WanAnimate2Cache'}:continue
      counts[kind]+=1;widgets[(kind,tuple(node.get('widgets_values',[])))]+=1;modes[(kind,node.get('mode',0))]+=1;members[(kind,name)]+=1
  self.assertEqual((512,496,272,8120),(files,roots,subgraphs,nodes));self.assertEqual(Counter({'EasyCache':4,'WanAnimate2Cache':2}),counts);self.assertEqual(4,widgets[('EasyCache',(0.2,0.15,0.95,False))]);self.assertEqual(2,widgets[('WanAnimate2Cache',('gpu','int8'))]);self.assertEqual(4,modes[('EasyCache',4)]);self.assertEqual(2,modes[('WanAnimate2Cache',0)]);self.assertEqual(2,sum(1 for key in members if key[0]=='EasyCache'));self.assertEqual(1,sum(1 for key in members if key[0]=='WanAnimate2Cache'))
if __name__=='__main__':unittest.main()
