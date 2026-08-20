from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from typing import Any,Iterator
from tools import catalog
SPECS={'core.wan-scail-to-video':('wan-scail-to-video','WanSCAILToVideo','sha256:0254022e290859e883f5f995ee20e9a27143fc20c1eb3bdf75bd1c8f1c700a62','wan-scail2-replacement-conditioning'),'core.scail2-colored-mask':('scail2-colored-mask','SCAIL2ColoredMask','sha256:4e066086a709aa8b98ab02180f1fb7444ed524b489755452b5299721bdc115bf','scail2-colored-mask-replacement')}
DOCS={'WanSCAILToVideo':('c9730e30bee537986da2d3497f9a0761261206652591e76674e69b2870ed04f0','46aa373b61a85e2923f953fbca7ac70641907cd3d982e6f91a597dd821c0dc82'),'SCAIL2ColoredMask':('419ff54255ea3d6014bf401038df736487d5acc4c7bd46f18785ba8a9c2b4445','c66dc65ec1dc1d8cb138f61c413bed001dbf1c7c226d67c3541f32d7a959e10a')}
def graphs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from graphs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from graphs(y)
class SCAILContentTests(unittest.TestCase):
 def test_schema_runtime_source_docs(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};nodes=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(d,ct,fp,r) in SPECS.items():
   ap=catalog.CONTENT/'articles/core'/d/'manifest.json';a=catalog.load_json(ap);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(ap,a,e);self.assertEqual(10,len(re.findall(r'^## ',(ap.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,nodes[ct]));self.assertTrue(nodes[ct]['experimental']);led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,sch['article-research']));rp=catalog.CONTENT/'recipes'/r/'recipe.json';rec=catalog.load_json(rp);catalog.validate_recipe(rp,rec,ids,e);self.assertEqual([],catalog.json_schema_errors(rec,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],e);src=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_scail.py';self.assertEqual('7cd7f3588a7fbdb1d1379ad7fd0669364bbae3d921ba17cfbd9ee007251a980b',hashlib.sha256(src.read_bytes()).hexdigest());t=src.read_text(encoding='utf8');
  for s in ('DEFAULT_PALETTE','T_latent = (T - 1) // 4 + 1','padded.view(T_latent, 28','video_frame_offset -= prev_trimmed.shape[0]','order = sorted(range(len(cx))'):self.assertIn(s,t)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
 def test_workflow_presets(self):
  found=[];jc=gc=0
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if not n.endswith('.json'):continue
    jc+=1
    for g in graphs(json.loads(z.read(n))):
     gc+=1
     for node in g.get('nodes',[]):
      if node.get('type') in ('WanSCAILToVideo','SCAIL2ColoredMask'):found.append((node['type'],node.get('widgets_values'),node.get('mode',0)))
  self.assertEqual((512,768),(jc,gc));self.assertEqual(8,len(found));self.assertEqual(4,sum(t=='WanSCAILToVideo' and w==[512,896,65,1,1,0,1,0,5,True] and m==0 for t,w,m in found));self.assertEqual(4,sum(t=='SCAIL2ColoredMask' and w==['','left_to_right',True] and m==0 for t,w,m in found))
 def test_shape_math(self):
  self.assertEqual((1,16,17,112,64),(1,16,(65-1)//4+1,896//8,512//8));self.assertEqual(17,(65-1)//4+1);self.assertEqual(21,(81-1)//4+1);self.assertEqual(17,(65-1)//4+1)
if __name__=='__main__':unittest.main()
