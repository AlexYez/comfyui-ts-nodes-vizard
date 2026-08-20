from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter,defaultdict
from typing import Any,Iterator
from tools import catalog
SPECS={'core.load-background-removal-model':('load-background-removal-model','LoadBackgroundRemovalModel','sha256:8fdeecbb4a656250c48c651b7ef18d921d721780ee0ba379aacbfd76de2f9ccd'),'core.remove-background':('remove-background','RemoveBackground','sha256:569952070c1f87834376959fd50d0cb17c0aaea2a06148ad2432e0006df7fc6a')}
DOCS={'LoadBackgroundRemovalModel':('1b6f09ae24a9815b2ff49a71490c6c1039d5d68f3a745781d034ef48631439a5','1c041184fdf5f628312c5e9701b4ee21706b6721574772d8cc1ba5900d6b7d35'),'RemoveBackground':('a5541012176dc1ffb9c0ce53c5636b8df3d6f20ff526ab5f31e4e5f82b27a978','1d34badc770fa74621b135adeb59074bb6bc3b6a62df5f33365347d9f9167c2b')}
def gs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from gs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from gs(y)
class BackgroundRemovalTests(unittest.TestCase):
 def test_all(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json'),sch['article-research']))
  rp=catalog.CONTENT/'recipes/birefnet-foreground-mask/recipe.json';rec=catalog.load_json(rp);catalog.validate_recipe(rp,rec,ids,e);self.assertEqual([],catalog.json_schema_errors(rec,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),sch['recipe-fragment']));self.assertEqual([],e)
  p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_bg_removal.py';self.assertEqual('501bcee5b6c7fcf889b400ce840500dcd3b9166d52014da3e8df0138c0cdb1fe',hashlib.sha256(p.read_bytes()).hexdigest());p2=catalog.ROOT/'.comfyui-source-0.32.0/comfy/bg_removal_model.py';self.assertEqual('7f1ad7f5cecc51c7dc07ee071e7c2145b55286b9d35a5ea0877090bfa602934c',hashlib.sha256(p2.read_bytes()).hexdigest());t=p2.read_text(encoding='utf8');self.assertIn('for i in range(pixel_values.shape[0])',t);self.assertIn('mode="bicubic", antialias=False',t);self.assertIn('return mask.squeeze(1)',t)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
  c=Counter();w=defaultdict(list);cases=[]
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if n.endswith('.json'):
     for g in gs(json.loads(z.read(n))):
      for q in g.get('nodes',[]):
       if q.get('type') in {'LoadBackgroundRemovalModel','RemoveBackground'}:c[q['type']]+=1;w[q['type']].append(q.get('widgets_values',[]))
      by_id={q.get('id'):q for q in g.get('nodes',[])}
      if any(q.get('type')=='RemoveBackground' for q in by_id.values()):
       links={(x.get('origin_id'),x.get('target_id'),x.get('target_slot'),x.get('type')) for x in g.get('links',[])}
       loader=next(q for q in by_id.values() if q.get('type')=='LoadBackgroundRemovalModel');remove=next(q for q in by_id.values() if q.get('type')=='RemoveBackground');invert=next(q for q in by_id.values() if q.get('type')=='InvertMask');join=next(q for q in by_id.values() if q.get('type')=='JoinImageWithAlpha')
       self.assertIn((loader['id'],remove['id'],1,'BACKGROUND_REMOVAL'),links);self.assertIn((remove['id'],invert['id'],0,'MASK'),links);self.assertIn((invert['id'],join['id'],1,'MASK'),links);cases.append(n)
  self.assertEqual({'LoadBackgroundRemovalModel':2,'RemoveBackground':2},dict(c));self.assertEqual([['birefnet.safetensors']]*2,w['LoadBackgroundRemovalModel'])
  self.assertEqual(2,len(cases));self.assertTrue(any('utility_birefnet_remove_background' in n for n in cases));self.assertTrue(any('triposplat' in n.lower() for n in cases))
if __name__=='__main__':unittest.main()
