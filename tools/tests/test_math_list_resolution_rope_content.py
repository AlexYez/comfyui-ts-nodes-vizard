from __future__ import annotations
import hashlib,json,math,re,unittest,zipfile
from collections import Counter,defaultdict
from typing import Any,Iterator
from tools import catalog
SPECS={'core.comfy-math-expression':('comfy-math-expression','ComfyMathExpression','sha256:8905faba4720a53012e0d0991109042320431d592bd8d834c688158f3f0316ce'),'core.create-list':('create-list','CreateList','sha256:e03ee260911345ec3d0e0ae5a91a707717966c72ff2540f423404c7e9f1e72fa'),'core.resolution-selector':('resolution-selector','ResolutionSelector','sha256:9336a2b2bcf3cbb2db5f271afcaaf5a78e9dbae893a4d821de68c878029aad2a'),'core.scale-rope':('scale-rope','ScaleROPE','sha256:56fffe39ba5a3f35714e25de1f83fb80fd10f40a82526a0f4f8caef4aece7020')}
HASHES={'nodes_math.py':'a66d07ef4cb9a4948657ce87ea7c1af14937019031dcb3c0313cdee5baa121b7','nodes_toolkit.py':'104f1afdad3b21bad0d115b81a9d215134390b94161ec9cbf144fccfbd3972f0','nodes_resolution.py':'f3dc0c5dddc257dbc8e86db0aba0e791affb10872c3981b677cc2e74bc73c3e5','nodes_rope.py':'d7e2f60b8b1c0964e292939923c8bc4588e0d09014e0917293a553e5716d6f6e'}
DOCS={'ComfyMathExpression':('271947e1a03c2c059226775c0dc0f0c90b94d96b806b64c22fdf6bda315f102d','e09c5ca2ce6541fae391b509ceb19f61ebadeebbe4c04da4c53667b0c0661feb'),'CreateList':('ce7aa427cb0b8f452210501c34ace699e645ed54a9d7219b2585e0b1e14e755e','d24132df8631e376343abf5b3b225b809d80367731ae7709e637168cabfd111f'),'ResolutionSelector':('596a6ab8f9e5a22e6bfa9fa13ef3c123ef50af2d1e2881d232d710a93f8641b0','eed5a18388392aa589c50d2eff6e685dcb90e5b45f3eb83fe6bfe80b490fa252'),'ScaleROPE':('d746492aee55632c4961bce73581888d4f6821f174cd0cfc6ac32fe35ab8e85b','818659bae54439a55f5456191e488ab89854806408a2de2fad891491d3a291c8')}
def gs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from gs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  for y in (x.get('definitions') or {}).get('subgraphs',[]):yield from gs(y)
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json'),sch['article-research']))
  for slug in ['math-expression-half','create-string-list','resolution-widescreen-09mp','scale-rope-chrono-edit']:
   p=catalog.CONTENT/'recipes'/slug/'recipe.json';r=catalog.load_json(p);catalog.validate_recipe(p,r,ids,e);self.assertEqual([],catalog.json_schema_errors(r,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(p.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],e)
 def test_sources_and_math(self):
  for n,h in HASHES.items():self.assertEqual(h,hashlib.sha256((catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras'/n).read_bytes()).hexdigest())
  scale=math.sqrt(.9*1024*1024/(16*9));self.assertEqual((1280,736),(round(16*scale/32)*32,round(9*scale/32)*32));self.assertEqual([1,2,3],[1]+[2,3]);self.assertEqual(2.5,5/2)
  rope=(catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_rope.py').read_text('utf8');self.assertIn('m = model.clone()',rope);self.assertIn('set_model_rope_options(scale_x, shift_x, scale_y, shift_y, scale_t, shift_t)',rope)
 def test_docs_and_workflows(self):
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
  c=Counter();w=defaultdict(list)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   names=[n for n in z.namelist() if n.endswith('.json')];self.assertEqual(512,len(names))
   for n in names:
    for g in gs(json.loads(z.read(n))):
     for q in g.get('nodes',[]):
      if q.get('type') in {'ComfyMathExpression','CreateList','ResolutionSelector','ScaleROPE'}:c[q['type']]+=1;w[q['type']].append(q.get('widgets_values',[]))
  self.assertEqual({'ComfyMathExpression':98,'ResolutionSelector':21,'ScaleROPE':1},dict(c));self.assertNotIn('CreateList',c);self.assertEqual([[1,0,1,0,7,0]],w['ScaleROPE']);self.assertIn(['16:9 (Widescreen)',.9,32],w['ResolutionSelector']);self.assertIn(['a/2'],w['ComfyMathExpression'])
 def test_fragments(self):
  self.assertEqual('a/2',catalog.load_json(catalog.CONTENT/'recipes/math-expression-half/fragment.json')['nodes'][0]['settings']['expression']);self.assertEqual(2,len(catalog.load_json(catalog.CONTENT/'recipes/create-string-list/fragment.json')['externalInputs']));self.assertEqual(7.0,catalog.load_json(catalog.CONTENT/'recipes/scale-rope-chrono-edit/fragment.json')['nodes'][0]['settings']['scale_t'])
if __name__=='__main__':unittest.main()
