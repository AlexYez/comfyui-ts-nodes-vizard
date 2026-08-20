from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from typing import Any,Iterator
from tools import catalog
SPECS={'core.rtdetr-detect':('rtdetr-detect','RTDETR_detect','sha256:aad1a4aacdc1dddddab55b0d30e98e8c3d20059740e38525fedd163ad66dd639','detect-person-rtdetr'),'core.draw-bboxes':('draw-bboxes','DrawBBoxes','sha256:7d3267ca7967c575280254d290f469865dd1f3a4ac1657922424b1d0cf30dd23','draw-detection-boxes')}
DOCS={'RTDETR_detect':('304892704e0e93491573d044492759a06112263424881ae173e20686e2a68dd6','8ab3fbf71f7bf854801f0f9a12676c64dc645ee3c3f60687bacac2fe78d5f584'),'DrawBBoxes':('046379ee92c8940fe9fc1902e9b31e815c4d8f4bbf2f9efe19fe6afbcf9842eb','8507f24e8603b13c8cc8299d2c3ac5557c0cf7a308e50457755ca708a5daff29')}
def graphs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from graphs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from graphs(y)
class RTDETRContentTests(unittest.TestCase):
 def test_schema_runtime_source_docs(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};nodes=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(d,ct,fp,r) in SPECS.items():
   ap=catalog.CONTENT/'articles/core'/d/'manifest.json';a=catalog.load_json(ap);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(ap,a,e);self.assertEqual(10,len(re.findall(r'^## ',(ap.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,nodes[ct]));led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,sch['article-research']));rp=catalog.CONTENT/'recipes'/r/'recipe.json';rec=catalog.load_json(rp);catalog.validate_recipe(rp,rec,ids,e);self.assertEqual([],catalog.json_schema_errors(rec,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],e);src=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_rtdetr.py';self.assertEqual('4cb826b5da8ff53cd49be4499a99a2a6cff3a9ae0d1124dc61af34f25d317e74',hashlib.sha256(src.read_bytes()).hexdigest());t=src.read_text(encoding='utf8');self.assertIn('for i in range(0, B, 32)',t);self.assertIn("det['scores'] > threshold",t);self.assertIn('bboxes = bboxes * B',t);self.assertIn('default=640',t)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
 def test_workflow_topology(self):
  found=[];draw_templates=set();jc=gc=0
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if not n.endswith('.json'):continue
    jc+=1
    for g in graphs(json.loads(z.read(n))):
     gc+=1;nodes={x.get('id'):x for x in g.get('nodes',[])}
     if any(x.get('type')=='DrawBBoxes' for x in nodes.values()):draw_templates.add(n)
     for node in nodes.values():
      if node.get('type')=='RTDETR_detect':found.append((n,node.get('widgets_values')))
  self.assertEqual((512,768),(jc,gc));self.assertEqual(2,len(found));self.assertEqual([[0.5,'person',1],[0.5,'person',2]],sorted((x[1] for x in found),key=lambda v:v[2]));self.assertEqual({x[0] for x in found},draw_templates)
if __name__=='__main__':unittest.main()
