from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter,defaultdict
from typing import Any,Iterator
from tools import catalog
SPECS={'core.kandinsky5-image-to-video':('kandinsky5-image-to-video','Kandinsky5ImageToVideo','sha256:27df3f0407e8ed3e8b01577bf0a16195ee5e4a26608b0685415423c7bec0d496','kandinsky5-i2v-conditioning'),'core.normalize-video-latent-start':('normalize-video-latent-start','NormalizeVideoLatentStart','sha256:9b45107115a58cf0450c3d897fc99d25f7c76d361702061046e80dd6c7047ded','normalize-video-latent-start'),'core.clip-text-encode-kandinsky5':('clip-text-encode-kandinsky5','CLIPTextEncodeKandinsky5','sha256:e1f31e937ef39bc98e8ce8627707a18294743cd07ac068e74f42d676548e0032','kandinsky5-dual-prompt')}
DOCS={'Kandinsky5ImageToVideo':('133f9c65a9177d6e506928f6764dfa391c0e5bcb5f696cf56e38418688fa7155','372bd0f9858322b1578a9200560a009300e1842844859140933b3878215cc97d'),'NormalizeVideoLatentStart':('623047419e69c1066762c954cab9ad00ae6d23ae2cb31dae73b9654360a31d9f','b0b929d25ed7267c208d79370b5f389f5e04204ae5319d28a36d36b05aa7400a'),'CLIPTextEncodeKandinsky5':('15c1f154a163afd360a32ef50ca3200df9c009b6e1c624ced2ee2d595ca29395','b102de5646452f9474d628788573b0dae976f783ac3ce491bf46c1a15548b60a')}
def gs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from gs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from gs(y)
class Kandinsky5Tests(unittest.TestCase):
 def test_schema_identity(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};e=[]
  for aid,(slug,ct,fp,r) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));self.assertFalse(rt[ct].get('api_node',False));led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,sch['article-research']));rp=catalog.CONTENT/'recipes'/r/'recipe.json';rec=catalog.load_json(rp);catalog.validate_recipe(rp,rec,ids,e);self.assertEqual([],catalog.json_schema_errors(rec,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],e)
 def test_source_docs_census(self):
  p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_kandinsky5.py';self.assertEqual('4fcf88f3d2091c00aaca4862cc574cb8f2deb506c580c569cfc1e3e38e4311ed',hashlib.sha256(p.read_bytes()).hexdigest());t=p.read_text(encoding='utf8')
  for s in ('((length - 1) // 4) + 1','{"time_dim_replace": encoded, "concat_mask": mask}','reference_frames_data = samples[:, :, start_frame_count:','tokens["qwen25_7b"] = clip.tokenize(qwen25_7b)'):self.assertIn(s,t)
  c=Counter();w=defaultdict(list);jc=gc=0
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if not n.endswith('.json'):continue
    jc+=1
    for g in gs(json.loads(z.read(n))):
     gc+=1
     for q in g.get('nodes',[]):
      if q.get('type') in {v[1] for v in SPECS.values()}:c[q['type']]+=1;w[q['type']].append(q.get('widgets_values',[]))
  self.assertEqual((512,768),(jc,gc));self.assertEqual({'Kandinsky5ImageToVideo':2,'NormalizeVideoLatentStart':1},dict(c));self.assertEqual([[768,512,121,1]]*2,w['Kandinsky5ImageToVideo']);self.assertEqual([[4,5]],w['NormalizeVideoLatentStart'])
 def test_fragments(self):
  self.assertEqual({'width':768,'height':512,'length':121,'batch_size':1},catalog.load_json(catalog.CONTENT/'recipes/kandinsky5-i2v-conditioning/fragment.json')['nodes'][0]['settings']);self.assertEqual({'start_frame_count':4,'reference_frame_count':5},catalog.load_json(catalog.CONTENT/'recipes/normalize-video-latent-start/fragment.json')['nodes'][0]['settings'])
if __name__=='__main__':unittest.main()
