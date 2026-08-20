from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter,defaultdict
from typing import Any,Iterator
from tools import catalog
SPECS={'core.empty-minimax-h3-latent-av':('empty-minimax-h3-latent-av','EmptyMiniMaxH3LatentAV','sha256:d1fbc8efbdf52191289cecd832852f229eda30e554c89f080c4d60da627be2da','empty-minimax-h3-latent-av'),'core.minimax-h3-image-to-video':('minimax-h3-image-to-video','MiniMaxH3ImageToVideo','sha256:d6a49b5f04546f5473ebb07dd4ba883ae71fc67e768912ba6abdaeafabee66ba','minimax-h3-image-to-video'),'core.minimax-h3-reference-to-video':('minimax-h3-reference-to-video','MiniMaxH3ReferenceToVideo','sha256:f985c8fd12dc1dae1b6943640f9c4aae821a6e5bab6eebcf4c524752bbecdeaf','minimax-h3-reference-image')}
def gs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from gs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from gs(y)
class MiniMaxH3Tests(unittest.TestCase):
 def test_schema_identity_honesty(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};e=[]
  for aid,(slug,ct,fp,r) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));self.assertFalse(any(rt[ct].get(k,False) for k in ['api_node','experimental','deprecated','dev_only']));led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,sch['article-research']));self.assertFalse(led['checks']['exampleExecuted']);rp=catalog.CONTENT/'recipes'/r/'recipe.json';rec=catalog.load_json(rp);catalog.validate_recipe(rp,rec,ids,e);self.assertEqual([],catalog.json_schema_errors(rec,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],e)
 def test_source_and_math(self):
  p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_minimax_h3.py';self.assertEqual('457602c20e43671011e2edf0b154a674e3203198ebaddd25b951023cccc0be95',hashlib.sha256(p.read_bytes()).hexdigest());t=p.read_text(encoding='utf8')
  for s in ('while n % 17 != 5','[batch_size, 24, latent_t, height // 16, width // 16]','[batch_size, 32, 2, audio_t]','resolved_frame_index": frame_count - 1','if n < 5:','minimax_ref_items=ref_items'):self.assertIn(s,t)
  self.assertEqual(124,next(n for n in range(124,200) if n%17==5));self.assertEqual(37,((124-5)//17)*5+2);self.assertEqual(207,round(124/24*40))
 def test_workflow_census_and_fragments(self):
  c=Counter();w=defaultdict(list);jc=gc=0;targets={v[1] for v in SPECS.values()}
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   names=z.namelist();self.assertFalse(any(any(f'/docs/{ct}/' in n for ct in targets) for n in names))
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if not n.endswith('.json'):continue
    jc+=1
    for g in gs(json.loads(z.read(n))):
     gc+=1
     for q in g.get('nodes',[]):
      if q.get('type') in targets:c[q['type']]+=1;w[q['type']].append(q.get('widgets_values',[]))
  self.assertEqual((512,768),(jc,gc));self.assertEqual({'MiniMaxH3ImageToVideo':2,'MiniMaxH3ReferenceToVideo':1},dict(c));self.assertTrue(all(x[1:]==[1344,768,73] for x in w['MiniMaxH3ImageToVideo']));self.assertEqual([['',1344,768,124,'match']],w['MiniMaxH3ReferenceToVideo'])
  self.assertEqual({'width':1344,'height':768,'length':124},catalog.load_json(catalog.CONTENT/'recipes/empty-minimax-h3-latent-av/fragment.json')['nodes'][0]['settings'])
if __name__=='__main__':unittest.main()
