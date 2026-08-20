from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter
from typing import Any,Iterator
from tools import catalog
SPECS={
'core.seedvr2-conditioning':('seedvr2-conditioning','SeedVR2Conditioning','sha256:2e259def77d019b67f98376371f925da172e6a23abdaabfdaa80152070f844f2'),
'core.seedvr2-preprocess':('seedvr2-preprocess','SeedVR2Preprocess','sha256:d1cc93d369f475ded70e31e9acdb7c7e930a608d36ea12fda141a7c8f32e0f6a'),
'core.seedvr2-post-processing':('seedvr2-post-processing','SeedVR2PostProcessing','sha256:d5b18d46f3b3b55d6e5238f0d6eef04ba9ed916c478cf42994f3e611a4151bc3'),
'core.seedvr2-temporal-chunk':('seedvr2-temporal-chunk','SeedVR2TemporalChunk','sha256:50cae64205b994b57bb4d653559f6353d9d5c867fe821d9dc05f041df5de61a4'),
'core.seedvr2-temporal-merge':('seedvr2-temporal-merge','SeedVR2TemporalMerge','sha256:19d29617ccae608724679c5da51eefd5eeacda612c009ec12ed2454a9eec5b32')}
DOCS={'SeedVR2Conditioning':('f73071290fd2a18cc0ac9615f9a48531f10a9d272b37070ae05e541ed461cdb3','9fe23983d6eba9b25d10969ec210d6d7dc492d89be6d0992fccafce20fc1c594'),'SeedVR2Preprocess':('a340b0b6e1df4994fbb05fdb75da26bf62b03e329514555b5acf4748d317a064','091899a5a63f5f3c58baebc70df9090a359b3a175224cce1ab017068a83cb77a'),'SeedVR2PostProcessing':('77af723938277038cbc104f511542b118159c015aabeac14ad933460dd797e36','61d8e9c1976f080115f093ef23b08af2c2f16e2f0f6aa7d89be1f3b2613e3a5f'),'SeedVR2TemporalChunk':('a6f951cc1a8f0500e4c1d2c384bc3295794243030959d39f61c4844c55933b1c','6c3b93d20c94d51f860325e1e45767e6a7e6ac9e1f3175384d03fcbe29ae21ac'),'SeedVR2TemporalMerge':('fedeeb47aa54cf2d1bb94d7569a1318229e21a9090a9875d0e05cad0f1ed612c','a94753193d40ad1618869f6f7cd4195c19745db1bf29833e0abe1916e89f2d1e')}
def graphs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from graphs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from graphs(y)
class SeedVR2ContentTests(unittest.TestCase):
 def test_schema_identity_honesty(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};nodes=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(d,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/d/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,nodes[ct]));self.assertFalse(any(nodes[ct].get(k,False) for k in ['experimental','deprecated','dev_only','api_node']));led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,sch['article-research']));self.assertFalse(led['checks']['exampleExecuted'])
  for d in ['seedvr2-preprocess-input','seedvr2-conditioning-latent','seedvr2-postprocess-none','seedvr2-temporal-chunk-merge']:
   p=catalog.CONTENT/'recipes'/d/'recipe.json';r=catalog.load_json(p);catalog.validate_recipe(p,r,ids,e);self.assertEqual([],catalog.json_schema_errors(r,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(p.parent/'fragment.json'),sch['recipe-fragment']));self.assertNotIn('workflow',r)
  self.assertEqual([],e)
 def test_source_docs(self):
  p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_seedvr.py';self.assertEqual('55e4de8cafe16ef2d834d29fb1073d4ae3780e6e35bf649eb5f9fb7b0334fb04',hashlib.sha256(p.read_bytes()).hexdigest());t=p.read_text(encoding='utf8')
  for s in ('(t - 1) % 4 == 0','images[..., :3]','output.shape[-3] % 2','vae_conditioning.ndim != 5','4 * (t_latent - 1) + 1','frames_per_chunk must be a 4n+1','_seedvr2_chunk_crossfade_weights','out.pop("noise_mask", None)'):self.assertIn(s,t)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
 def test_workflow_census(self):
  found=[];jc=gc=0;targets={v[1] for v in SPECS.values()}
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if not n.endswith('.json'):continue
    jc+=1
    for g in graphs(json.loads(z.read(n))):
     gc+=1
     for q in g.get('nodes',[]):
      if q.get('type') in targets:found.append((q['type'],q.get('widgets_values'),q.get('mode',0)))
  self.assertEqual((512,768),(jc,gc));self.assertEqual({'SeedVR2Preprocess':3,'SeedVR2PostProcessing':3,'SeedVR2Conditioning':3,'SeedVR2TemporalChunk':1,'SeedVR2TemporalMerge':1},dict(Counter(x[0] for x in found)));self.assertTrue(all(w==[] for t,w,_ in found if t in ('SeedVR2Preprocess','SeedVR2Conditioning','SeedVR2TemporalMerge')));self.assertTrue(all(w==['none'] for t,w,_ in found if t=='SeedVR2PostProcessing'));self.assertTrue(all(w==[0,'auto'] for t,w,_ in found if t=='SeedVR2TemporalChunk'));self.assertTrue(all(m==0 for _,_,m in found))
 def test_fragment_contracts(self):
  expected={'seedvr2-preprocess-input':['SeedVR2Preprocess'],'seedvr2-conditioning-latent':['SeedVR2Conditioning'],'seedvr2-postprocess-none':['SeedVR2PostProcessing'],'seedvr2-temporal-chunk-merge':['SeedVR2TemporalChunk','SeedVR2TemporalMerge']}
  for d,types in expected.items():self.assertEqual(types,[n['classType'] for n in catalog.load_json(catalog.CONTENT/'recipes'/d/'fragment.json')['nodes']])
if __name__=='__main__':unittest.main()
