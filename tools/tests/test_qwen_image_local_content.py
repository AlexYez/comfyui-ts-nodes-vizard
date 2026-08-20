from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter,defaultdict
from typing import Any,Iterator
from tools import catalog
SPECS={'core.text-encode-qwen-image-edit':('text-encode-qwen-image-edit','TextEncodeQwenImageEdit','sha256:4cd57736df608bb9b2a8ab292738e086f8ca8b8f5f3c7ea4b33f1222d19ac85a','qwen-image-edit-one-reference'),'core.text-encode-qwen-image-edit-plus':('text-encode-qwen-image-edit-plus','TextEncodeQwenImageEditPlus','sha256:44e7530b246383fe7d304d91c284b815a2f061068064c891276d87db053add08','qwen-image-edit-plus-two-references'),'core.empty-qwen-image-layered-latent-image':('empty-qwen-image-layered-latent-image','EmptyQwenImageLayeredLatentImage','sha256:c5ebb21b09a79570fdf14ed2f93ce5a6338b47f2920d55299df2268de3fbbe52','empty-qwen-layered-latent')}
DOCS={'TextEncodeQwenImageEdit':('74510e7628db241f0e60fdeeb4af143ead496c03ddcd6f5f7991b9990dc02627','d9fbedd3bb7a2884033c80f3d179cc7c7efd684bccfa50a0b41ef53308ac5895'),'TextEncodeQwenImageEditPlus':('99abf485f696d669e1283c4f7ba02ff99549b026721770e15b161bb1e36a1442','cbb9b061cf376656f26a6c0ad2266402784b0bab55f7bb8778334cef72082592'),'EmptyQwenImageLayeredLatentImage':('d158b55e00d8d733ab9b93eae40f95d677bd72d28b478ab7f8bc77c850063a70','d108024de0641c603b9a1ecc6292368102934a66ef650793bb5d80209067b870')}
def gs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from gs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from gs(y)
class QwenLocalTests(unittest.TestCase):
 def test_schema_identity(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};e=[]
  for aid,(slug,ct,fp,r) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));self.assertFalse(rt[ct].get('api_node',False));led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,sch['article-research']));rp=catalog.CONTENT/'recipes'/r/'recipe.json';rec=catalog.load_json(rp);catalog.validate_recipe(rp,rec,ids,e);self.assertEqual([],catalog.json_schema_errors(rec,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],e)
 def test_source_docs_and_census(self):
  p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_qwen.py';self.assertEqual('32d9c6e7b0b838bdefab05829c0465043c5576626f4cc654b79cca8a0e9a5097',hashlib.sha256(p.read_bytes()).hexdigest());t=p.read_text(encoding='utf8')
  for s in ('total = int(1024 * 1024)','total = int(384 * 384)','round(samples.shape[3] * scale_by / 8.0) * 8','Picture {}: <|vision_start|>','[batch_size, 16, layers + 1, height // 8, width // 8]'):self.assertIn(s,t)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
  c=Counter();w=defaultdict(list);jc=gc=0;layered_edges=Counter()
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if not n.endswith('.json'):continue
    jc+=1
    for g in gs(json.loads(z.read(n))):
     gc+=1
     nodes={q.get('id'):q for q in g.get('nodes',[])}
     for q in nodes.values():
      if q.get('type') in {v[1] for v in SPECS.values()}:c[q['type']]+=1;w[q['type']].append(q.get('widgets_values',[]))
     for link in g.get('links',[]):
      if not isinstance(link,dict):continue
      source=nodes.get(link.get('origin_id'));target=nodes.get(link.get('target_id'))
      if source and source.get('type')=='EmptyQwenImageLayeredLatentImage':layered_edges[(link.get('type'),target.get('type'),link.get('target_slot'))]+=1
  self.assertEqual((512,768),(jc,gc));self.assertEqual({'TextEncodeQwenImageEditPlus':55,'TextEncodeQwenImageEdit':4,'EmptyQwenImageLayeredLatentImage':3},dict(c));self.assertEqual([[640,640,2,1]]*3,w['EmptyQwenImageLayeredLatentImage']);self.assertEqual(3,layered_edges[('LATENT','KSampler',3)])
 def test_fragments(self):
  self.assertEqual({'width':640,'height':640,'layers':2,'batch_size':1},catalog.load_json(catalog.CONTENT/'recipes/empty-qwen-layered-latent/fragment.json')['nodes'][0]['settings'])
if __name__=='__main__':unittest.main()
