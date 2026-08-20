from __future__ import annotations
import hashlib,json,math,re,unittest,zipfile
from collections import Counter
from typing import Any,Iterator
from tools import catalog

SPECS={
'core.color-to-rgb-int':('color-to-rgb-int','ColorToRGBInt','sha256:2a022175ee77e4b1fa9854bcc4c6cf460e8bf1a87c0e8d670ce8c4e9eb811d1e'),
'core.comfy-number-convert':('comfy-number-convert','ComfyNumberConvert','sha256:78ad2e6b0f772c0e82abda77429e50045b82534b4df819e78e3b6c7840e7fdd6'),
'core.seed-node':('seed-node','SeedNode','sha256:5abf0c4ab2dc5716bec79de5e390428ce8e79e69289bcca7e97ae4500fba5eae'),
'core.preview-any':('preview-any','PreviewAny','sha256:bfd8d83b1229578c19215f2449749372102a1cbcbe9a421a5b537d9e5202ba69')}
HASHES={'nodes_color.py':'0618ea4901e76fcf2336b2c3a655927acd24746f5d377ad9c07d2b613ccb5f8f','nodes_number_convert.py':'7dd4c65056c597c7bd3bb39fe557393a265fb84282d61be82e8a94fda780a67c','nodes_seed.py':'913677a8a10417b91773e1c196666a31312bf2d228643b35b87b63589332c62c','nodes_preview_any.py':'2ccae80490c47b67c44bc51efaf075bd1ce5868ce59b3985a7aef1e6b5384f5b'}
DOCS={'ColorToRGBInt':('1f5ebd792539406a068fbfaff3a8b2a069bf68046bb25a213904a6dc527d564a','b6d53e160fb75e8c47fc982c6b6bcd354e06ee3b618f9dbef37f016cc59db473'),'ComfyNumberConvert':('921bc2f3da830ce79e65feb010090b5366a632ea3120b9de3ea374ef639f3095','6326fd995d4c7a8f2ad5368aad217aa542398f29de8a2190ed317fa6a22aaad3'),'SeedNode':('015055c4cd7d1f32a89ff74d724906cc5b5b4ac97a9eb8c3300ea5698c505688','ec2dc94daf16fb289204bd07f37e9a4b1b3b6fab4c38f93c661672e540b0f49b'),'PreviewAny':('50837135cb0d26d292f26ad32283257afb1c2c63c441362b93af710aeb65d9d5','1999716e33e1e69720c11dc3dc171df142c277ff83a7e31c17c45dc13f82c9f4')}
def gs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from gs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  for y in (x.get('definitions') or {}).get('subgraphs',[]):yield from gs(y)
class UtilityValueContentTests(unittest.TestCase):
 def test_schema_runtime_and_text(self):
  schemas={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};errors=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,schemas['article']));catalog.validate_article(p,a,errors);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,schemas['article-research']));self.assertFalse(q['checks']['exampleExecuted'])
  for slug in ['color-to-rgb-int-official','number-convert-preview','seed-preview']:
   p=catalog.CONTENT/'recipes'/slug/'recipe.json';r=catalog.load_json(p);catalog.validate_recipe(p,r,ids,errors);self.assertEqual([],catalog.json_schema_errors(r,schemas['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(p.parent/'fragment.json'),schemas['recipe-fragment']))
  self.assertEqual([],errors)
 def test_sources_and_semantics(self):
  for n,h in HASHES.items():self.assertEqual(h,hashlib.sha256((catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras'/n).read_bytes()).hexdigest())
  self.assertEqual(692889,10*65536+146*256+153);self.assertEqual(1,int(True));self.assertEqual(-1,int(-1.9));self.assertTrue(math.isfinite(float('1.5')))
  s=(catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_preview_any.py').read_text('utf8');self.assertIn('json.dumps(source, indent=4)',s);self.assertIn('torch.set_printoptions(edgeitems=6)',s);self.assertIn('torch.set_printoptions()',s)
 def test_docs_and_census(self):
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
  c=Counter();widgets=[]
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   names=[n for n in z.namelist() if n.endswith('.json')];self.assertEqual(512,len(names))
   for n in names:
    for g in gs(json.loads(z.read(n))):
     for q in g.get('nodes',[]):
      if q.get('type') in {'ColorToRGBInt','ComfyNumberConvert','SeedNode','PreviewAny'}:c[q['type']]+=1
      if q.get('type')=='ColorToRGBInt':widgets.append(q.get('widgets_values'))
  self.assertEqual({'ColorToRGBInt':2,'ComfyNumberConvert':7,'PreviewAny':129},dict(c));self.assertIn(['#0a9299'],widgets);self.assertNotIn('SeedNode',c)
 def test_fragments(self):
  color=catalog.load_json(catalog.CONTENT/'recipes/color-to-rgb-int-official/fragment.json');self.assertEqual('#0a9299',color['nodes'][0]['settings']['color'])
  number=catalog.load_json(catalog.CONTENT/'recipes/number-convert-preview/fragment.json');self.assertEqual(['FLOAT','INT'],[x['output'] for x in number['connections']])
  seed=catalog.load_json(catalog.CONTENT/'recipes/seed-preview/fragment.json');self.assertEqual(42,seed['nodes'][0]['settings']['seed'])
if __name__=='__main__':unittest.main()
