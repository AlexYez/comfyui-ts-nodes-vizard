from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter,defaultdict
from typing import Any,Iterator
from tools import catalog

SPECS={
'core.empty-hidream-o1-latent-image':('empty-hidream-o1-latent-image','EmptyHiDreamO1LatentImage','sha256:ab8cb3fe2740e157c546cda83fcb06b074439374c1d1cb09c5f8561925277b6d','hidream-o1-empty-latent'),
'core.hidream-o1-reference-images':('hidream-o1-reference-images','HiDreamO1ReferenceImages','sha256:cea480a0a9551d7a5d07ef1b9746200945cbfe0ca8e188908cac71884c8bf893','hidream-o1-reference-images'),
'core.hidream-o1-patch-seam-smoothing':('hidream-o1-patch-seam-smoothing','HiDreamO1PatchSeamSmoothing','sha256:93b6bffd8daa794ea2236b28ecf9cec50fc416bb045acb601b5e00a230df3ba3','hidream-o1-seam-smoothing')}
DOCS={'EmptyHiDreamO1LatentImage':('d2a1c4219106e9c2917abe0635c2dd2bba9c9163aec3106c4cb79a2220e05e6e','aef62f28facf4e3ab01453781a92830854741e603ad39573b6c8d7617258c97c'),'HiDreamO1ReferenceImages':('7adf4b9ff887e0b6d39b076edf0bf148abbd1fffa0dcf0102af6dc669c4f6f24','fe53b9c3781cb9bd7c9284fff39fe66c59e12a26b4bc2ab8e679bab08c4fd69d'),'HiDreamO1PatchSeamSmoothing':('fce6f933cdf36e71b9ad89ced86be516a2629b74b6c53c3918ed8b846874fff4','7a4f8993954b2f142ddcfbbfbd12b603823600240b26835e18b022e0ccfa0578')}
def graphs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from graphs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from graphs(y)

class HiDreamO1ContentTests(unittest.TestCase):
 def test_schema_identity_honesty(self):
  schemas={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};runtime=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};errors=[]
  for aid,(slug,ct,fp,recipe) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,schemas['article']));catalog.validate_article(p,a,errors);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,runtime[ct]));self.assertEqual(ct=='HiDreamO1PatchSeamSmoothing',bool(runtime[ct].get('experimental',False)));led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,schemas['article-research']));self.assertFalse(led['checks']['exampleExecuted']);rp=catalog.CONTENT/'recipes'/recipe/'recipe.json';r=catalog.load_json(rp);self.assertEqual([],catalog.json_schema_errors(r,schemas['recipe']));catalog.validate_recipe(rp,r,ids,errors);self.assertNotIn('workflow',r);self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),schemas['recipe-fragment']))
  self.assertEqual([],errors)
 def test_source_docs(self):
  p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_hidream_o1.py';self.assertEqual('6872a1b7f50c094639b15aa15f138f2cc448aea1795446a98447d77cc331a8b3',hashlib.sha256(p.read_bytes()).hexdigest());t=p.read_text(encoding='utf8')
  for s in ('(batch_size, 3, height, width)','{"reference_latents": refs}, append=True','if strength <= 0.0 or end_percent <= start_percent','torch.roll(x, shifts=(sy, sx)','torch.median(stacked, dim=0).values','WrappersMP.DIFFUSION_MODEL'):self.assertIn(s,t)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
 def test_workflow_census(self):
  c=Counter();w=defaultdict(list);jc=gc=0;targets={v[1] for v in SPECS.values()}
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if not n.endswith('.json'):continue
    jc+=1
    for g in graphs(json.loads(z.read(n))):
     gc+=1
     for q in g.get('nodes',[]):
      if q.get('type') in targets:c[q['type']]+=1;w[q['type']].append(q.get('widgets_values',[]))
  self.assertEqual((512,768),(jc,gc));self.assertEqual({'EmptyHiDreamO1LatentImage':4,'HiDreamO1ReferenceImages':2,'HiDreamO1PatchSeamSmoothing':1},dict(c));self.assertEqual([[2048,2048,1]]*4,w['EmptyHiDreamO1LatentImage']);self.assertEqual([[0.8,1,'single_shift','ramp_2_4','median',1]],w['HiDreamO1PatchSeamSmoothing'])
 def test_fragments(self):
  expected={'hidream-o1-empty-latent':('EmptyHiDreamO1LatentImage',{'width':2048,'height':2048,'batch_size':1}),'hidream-o1-reference-images':('HiDreamO1ReferenceImages',{}),'hidream-o1-seam-smoothing':('HiDreamO1PatchSeamSmoothing',{'start_percent':0.8,'end_percent':1.0,'pattern':'single_shift','passes':'ramp_2_4','blend':'median','strength':1.0})}
  for slug,(ct,settings) in expected.items():
   f=catalog.load_json(catalog.CONTENT/'recipes'/slug/'fragment.json');self.assertEqual(ct,f['nodes'][0]['classType']);self.assertEqual(settings,f['nodes'][0]['settings'])
if __name__=='__main__':unittest.main()
