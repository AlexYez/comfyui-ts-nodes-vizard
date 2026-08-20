from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter
from typing import Any,Iterator
from tools import catalog

SPECS={
'core.load-moge-model':('load-moge-model','LoadMoGeModel','sha256:02d92daa00bed71b6cb35afdc770542b88d4af5a897818dadd963b6db8d70aef'),
'core.moge-inference':('moge-inference','MoGeInference','sha256:02570908441df36e149535a10622c1c80b257bb56aad228e18cdb305ba0b538f'),
'core.moge-panorama-inference':('moge-panorama-inference','MoGePanoramaInference','sha256:61eba3ef7f520cb950b27a56d6d1c0ae832eb871fa4432679856a10fa89748f8'),
'core.moge-render':('moge-render','MoGeRender','sha256:77d2d29d099a31a72b2d713b132312ccfe73ebf007ee7296bb365f41011a93b0'),
'core.moge-point-map-to-mesh':('moge-point-map-to-mesh','MoGePointMapToMesh','sha256:5c0db0c4c474626e59931e7de702da87005b95044b78971dc5f0be5931f2e5e0')}
DOCS={'LoadMoGeModel':('1c8bd8d684a6e22fd8a804b8b3e8384dffc71e53330c1b26c084c044765e283c','3b3db56b4bc7fe9065ef4ebdcb58945fbe944a03f4d41ceee68ee3e612ab2b78'),'MoGeInference':('395df2559339eef60effc0b94edde3e9669fed28fc197ba6b8473f286082cf1f','d576a7b017b2b783cd9bd37684ccb73e6deefcc854488ad35397492698e6df44'),'MoGePanoramaInference':('af8e9b5f31e9df638ebe3253b89046772451ead79db07a493a7daf3a26f126ca','680ea578b4cfdb7bc7cb4961463845ebb668ab8eb68ea2954a1db095c6860dd1'),'MoGeRender':('56751e71b326fb99a0d90aba92b57339531a7fce776878860a4d011bb13811c7','f66d3bca0ca92e875a0d363d839407e246ec2c6685ef64bc02389cc824ca2299'),'MoGePointMapToMesh':('ea8e7d6c40aa68556792996b7aca54a9cc29bc65eb292f36ca7b8c17b92c8469','2b3eef9d35a48e27d03b5a833a2bc0aec129021fe42632ed081d1b78847c9008')}
def graphs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from graphs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from graphs(y)
class MoGeContentTests(unittest.TestCase):
 def test_schema_runtime_honesty(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};nodes=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(d,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/d/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,nodes[ct]));self.assertFalse(any(nodes[ct].get(k,False) for k in ['experimental','deprecated','dev_only','api_node']));led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,sch['article-research']));self.assertFalse(led['checks']['exampleExecuted'])
  for d in ['moge-official-perspective-mesh','moge-official-panorama-mesh']:
   p=catalog.CONTENT/'recipes'/d/'recipe.json';r=catalog.load_json(p);catalog.validate_recipe(p,r,ids,e);self.assertEqual([],catalog.json_schema_errors(r,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(p.parent/'fragment.json'),sch['recipe-fragment']));self.assertNotIn('workflow',r)
  self.assertEqual([],e)
 def test_source_and_docs(self):
  p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_moge.py';self.assertEqual('a5cfeaf0d7ed646be3d77ff1f947477313f522ffcde509cb58480181b26c2029',hashlib.sha256(p.read_bytes()).hexdigest());t=p.read_text(encoding='utf8')
  for s in ('safe_load=True','for i in range(0, B, batch_size)','takes a single image','apply_metric_scale=False','torch.quantile(disp_valid, 0.001)','verts = verts[:, [1, 2, 0]].contiguous()','faces = faces[:, [0, 2, 1]].contiguous()'):self.assertIn(s,t)
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
  self.assertEqual((512,768),(jc,gc));self.assertEqual({'LoadMoGeModel':4,'MoGeInference':3,'MoGePanoramaInference':1,'MoGeRender':8,'MoGePointMapToMesh':2},dict(Counter(x[0] for x in found)));self.assertTrue(all(w==[0,1,0.04,True] for t,w,_ in found if t=='MoGePointMapToMesh'));self.assertTrue(all(w==[5,512,1024,4] for t,w,_ in found if t=='MoGePanoramaInference'));self.assertTrue(all(m==0 for _,_,m in found))
 def test_fragments(self):
  p=catalog.load_json(catalog.CONTENT/'recipes/moge-official-perspective-mesh/fragment.json');q=catalog.load_json(catalog.CONTENT/'recipes/moge-official-panorama-mesh/fragment.json');self.assertEqual(['LoadMoGeModel','MoGeInference','MoGePointMapToMesh'],[n['classType'] for n in p['nodes']]);self.assertEqual(['LoadMoGeModel','MoGePanoramaInference','MoGePointMapToMesh'],[n['classType'] for n in q['nodes']]);self.assertEqual(2,len(p['connections']));self.assertEqual(2,len(q['connections']))
if __name__=='__main__':unittest.main()
