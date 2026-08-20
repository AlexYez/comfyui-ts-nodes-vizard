from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter,defaultdict
from typing import Any,Iterator
from tools import catalog
SPECS={'core.text-encode-boogu-edit':('text-encode-boogu-edit','TextEncodeBooguEdit','sha256:1420c0673e67f2145354b923d18e16946de7a539dfc98f2f90eadada69f53e70'),'core.text-encode-joy-image-edit':('text-encode-joy-image-edit','TextEncodeJoyImageEdit','sha256:6ead890eedd04233007919fd08849c242e202852fb7d7ba57b29fdc8b3fa9a97'),'core.text-encode-mage-flow-edit':('text-encode-mage-flow-edit','TextEncodeMageFlowEdit','sha256:ef68490e8ecc71db4a4085cd613fa9a44fe289988f34083fed55e4f7bc78b47f'),'core.text-encode-zimage-omni':('text-encode-zimage-omni','TextEncodeZImageOmni','sha256:8d8784958dac63073473fe1476c06574600c6b78a8cbd0b6c1cfeffa326daae7')}
HASHES={'nodes_boogu.py':'15571e134f2d592c11ff38b5cd59d9c9daa070ba1dc9380d8784821874ad80ac','nodes_joyimage.py':'845123d079be958401801b7294d5794750bc25c0c9ddfbbb197ba364f55af767','nodes_mage.py':'29d8fac0be437e58da49ca0d122010e3553d679168fe26ba05329660fd3a144e','nodes_zimage.py':'4f9e75a86f53c3bd900513bb5d7603840646c6882b8e8262acee6a57f9f84754'}
DOCS={'TextEncodeBooguEdit':('5dc62465caa8200becba75e012b114a09d345a37df348e5096fc0af70fef7065','ac39440f9d00a9ee06e413ac17c7f63033e6fe91bbd8ed0d4e09440ea07ef6d0'),'TextEncodeJoyImageEdit':('309313b00ef98157c28aa3e4b22dc94ab860554653740aca99f9400779bd7d19','f86a0161076a16949da72a9e820e39691da6b3f519c3ba851fd5a965a2f0fbe5'),'TextEncodeMageFlowEdit':('32fce55806757c037367786694223fd5a7b43675b62be952097cb91d204ca81d','160f3e3e95119d187642f77c8ed85cecf6f82e803f662a90cc282347fe319b71'),'TextEncodeZImageOmni':('dd4675dc20f6fe793bfb5b464d0d25b862918fdff0505219bf603a886dff10c6','0a1bf7340e3168f0422098dbc42963b9525959a2b3634fe65e239ce6511cceb6')}
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
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,sch['article-research']));self.assertFalse(q['checks']['exampleExecuted'])
  for slug in ['boogu-edit-official','joy-image-edit-official','mage-flow-edit-official','zimage-omni-reference']:
   p=catalog.CONTENT/'recipes'/slug/'recipe.json';r=catalog.load_json(p);catalog.validate_recipe(p,r,ids,e);self.assertEqual([],catalog.json_schema_errors(r,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(p.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],e)
 def test_sources(self):
  for n,h in HASHES.items():self.assertEqual(h,hashlib.sha256((catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras'/n).read_bytes()).hexdigest())
  mage=(catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_mage.py').read_text('utf8');self.assertIn('[batch_size, 128, height // 16, width // 16]',mage);self.assertIn('negative_prompt if negative_prompt else " "',mage)
  z=(catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_zimage.py').read_text('utf8');self.assertIn('reference_latents_text_embeds',z);self.assertIn('clip_vision_outputs',z)
 def test_docs_and_census(self):
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
  c=Counter();w=defaultdict(list)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   names=[n for n in z.namelist() if n.endswith('.json')];self.assertEqual(512,len(names))
   for n in names:
    for g in gs(json.loads(z.read(n))):
     for q in g.get('nodes',[]):
      if q.get('type') in {x[1] for x in SPECS.values()}:c[q['type']]+=1;w[q['type']].append(q.get('widgets_values',[]))
  self.assertEqual({'TextEncodeBooguEdit':2,'TextEncodeJoyImageEdit':2,'TextEncodeMageFlowEdit':4},dict(c));self.assertNotIn('TextEncodeZImageOmni',c);self.assertIn(['remove the hat',''],w['TextEncodeBooguEdit']);self.assertIn(['Remove all hot air balloons','',0,0,1],w['TextEncodeMageFlowEdit'])
 def test_fragments(self):
  self.assertEqual('remove the hat',catalog.load_json(catalog.CONTENT/'recipes/boogu-edit-official/fragment.json')['nodes'][0]['settings']['prompt']);self.assertTrue(catalog.load_json(catalog.CONTENT/'recipes/zimage-omni-reference/fragment.json')['nodes'][0]['settings']['auto_resize_images'])
if __name__=='__main__':unittest.main()
