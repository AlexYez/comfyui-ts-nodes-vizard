from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from pathlib import Path
from typing import Any,Iterator
from tools import catalog
SPECS={'core.perp-neg':('perp-neg','PerpNeg','sha256:f792041380a21591ce61aea21309b466ee6ab621b6a215ff3e197ed9b413f5a1','perp-neg-legacy-model-patch'),'core.clip-text-encode-pixart-alpha':('clip-text-encode-pixart-alpha','CLIPTextEncodePixArtAlpha','sha256:d5c625fa2c81758a4fc4603d7c765282e5c04e5a8b96264eff15f54a13cd528c','pixart-alpha-1024-conditioning'),'core.temporal-score-rescaling':('temporal-score-rescaling','TemporalScoreRescaling','sha256:9e697e9045f189299f5f6f5c0d636770121d723ccda356a383ba8cb7ed6c7930','temporal-score-rescaling-default')}
DOCS={'PerpNeg':('ef8df9513000cd26146db833d252906fae42ddcb06dc0255d28e94fbb8f86685','b47621b12880bfd167930cb63366bae5a46ea85452deed4804b7bc3034196a30'),'CLIPTextEncodePixArtAlpha':('42bf0ea777d439bfa354244de309d5109b124c86dd4bc0a865ed53aa900bb081','5810a43dedf2b89869ca64cd44fdc2230b0ee0c14d957ad76952986b21c9ff41'),'TemporalScoreRescaling':('f93f176a40f58e71a97c47c77c30d2188e7c0e2274b0b3928ab64a64bb166bee','f69d1bee68931cc78423d4821069ed03e4b15d5ff43501a67bc1db1d9f5cd34d')}
def graphs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from graphs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from graphs(y)
class ConditioningPatchMiscContentTests(unittest.TestCase):
 def test_schema_runtime_and_honesty(self):
  schemas={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};nodes=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));errors=[]
  for aid,(d,ct,fp,r) in SPECS.items():
   ap=catalog.CONTENT/'articles/core'/d/'manifest.json';a=catalog.load_json(ap);self.assertEqual([],catalog.json_schema_errors(a,schemas['article']));catalog.validate_article(ap,a,errors);self.assertEqual(10,len(re.findall(r'^## ',(ap.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,nodes[ct]));self.assertEqual(('draft','in_review'),(a['status'],a['editorial']['state']));led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,schemas['article-research']));self.assertFalse(led['checks']['exampleExecuted']);rp=catalog.CONTENT/'recipes'/r/'recipe.json';rec=catalog.load_json(rp);self.assertEqual([],catalog.json_schema_errors(rec,schemas['recipe']));catalog.validate_recipe(rp,rec,ids,errors);self.assertNotIn('workflow',rec);self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),schemas['recipe-fragment']))
  self.assertTrue(nodes['PerpNeg']['deprecated'] and nodes['PerpNeg']['experimental']);self.assertFalse(nodes['CLIPTextEncodePixArtAlpha']['experimental'] or nodes['TemporalScoreRescaling']['experimental']);self.assertEqual([],errors)
 def test_sources_docs_formulas(self):
  files={'nodes_perpneg.py':'4639785c433a9d1e3612c67298540b5684b64e27ed5248ce22817f9cb6b1c9f2','nodes_pixart.py':'e351b1732601ac5fdcddcbe3c29d49dc96e2bbe0287efa46f4947c027c6e5cde','nodes_eps.py':'db27a4586856a4f64f221128649f4c9e4094b89e490c25587623086ecb618b9d'}
  for n,h in files.items():self.assertEqual(h,hashlib.sha256((catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras'/n).read_bytes()).hexdigest())
  self.assertIn('torch.norm(pos)**2',(catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_perpneg.py').read_text(encoding='utf8'));self.assertIn('add_dict={"width": width, "height": height}',(catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_pixart.py').read_text(encoding='utf8'));eps=(catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_eps.py').read_text(encoding='utf8');self.assertIn('(snr * tsr_variance + 1) / (snr * tsr_variance / tsr_k + 1)',eps);self.assertIn('torch.lerp(x / alpha, denoised, rescaling_r)',eps)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
 def test_zero_workflow_census(self):
  c={x:0 for _,x,_,_ in SPECS.values()};jc=gc=0
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if not n.endswith('.json'):continue
    jc+=1
    for g in graphs(json.loads(z.read(n))):
     gc+=1
     for node in g.get('nodes',[]):
      if node.get('type') in c:c[node['type']]+=1
  self.assertEqual((512,768),(jc,gc));self.assertEqual({'PerpNeg':0,'CLIPTextEncodePixArtAlpha':0,'TemporalScoreRescaling':0},c)
if __name__=='__main__':unittest.main()
