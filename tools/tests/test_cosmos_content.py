from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter
from typing import Any,Iterator
from tools import catalog
SPECS={'core.empty-cosmos-latent-video':('empty-cosmos-latent-video','EmptyCosmosLatentVideo','sha256:466794773df86542f826fc09e12a107daee661ffecae4cf92a461d9b620b265a','empty-cosmos-latent-121'),'core.cosmos-image-to-video-latent':('cosmos-image-to-video-latent','CosmosImageToVideoLatent','sha256:20bd3436cc60546840762e47a1ace6f4cea8c73dc574e1d4a281804d37d0d22a','cosmos-i2v-start-frame'),'core.cosmos-predict2-image-to-video-latent':('cosmos-predict2-image-to-video-latent','CosmosPredict2ImageToVideoLatent','sha256:38c731a02fcbdea13a267959bfcb5d4ac3e69b736d137ced8773a44f53aea6ab','cosmos-predict2-i2v-start-frame')}
DOCS={'EmptyCosmosLatentVideo':('8ad90c80e3e962c7bfb1ed2fff036bf183c882d5de8c1758c7fde54b87feac8a','f5380a39e11ead21ed2f51631f469f53b5228433905d55dfcd296e89b8345dcd'),'CosmosImageToVideoLatent':('babf962caf88cec6a3456e0fe046fbcb03e902e9ba5e76277efaaa00bb97d43d','19569573a43cd791347b9913cdb6480e23cbba671f8771a3e7de9af1c691d302'),'CosmosPredict2ImageToVideoLatent':('3a8609c3484bb6a3dd5e258cd7e97339d66c8a7b3298a39b14d4793ae9691b30','a333aa02f8faad2ef11197d69a6926cabd2ce45aa83b6a52562399344ce09bee')}
def graphs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from graphs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from graphs(y)
class CosmosContentTests(unittest.TestCase):
 def test_schema_identity_honesty(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};nodes=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(d,ct,fp,r) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/d/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,nodes[ct]));self.assertFalse(any(nodes[ct].get(k,False) for k in ['experimental','deprecated','dev_only','api_node']));led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,sch['article-research']));self.assertFalse(led['checks']['exampleExecuted']);rp=catalog.CONTENT/'recipes'/r/'recipe.json';rec=catalog.load_json(rp);catalog.validate_recipe(rp,rec,ids,e);self.assertEqual([],catalog.json_schema_errors(rec,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],e)
 def test_source_docs(self):
  p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_cosmos.py';self.assertEqual('d228995fdff7b2de28226a6daaeda9ad114663bd3cf61c702c83d2e96d2579b6',hashlib.sha256(p.read_bytes()).hexdigest());t=p.read_text(encoding='utf8')
  for s in ('((length - 1) // 8) + 1','padding=1','return io.NodeOutput(out_latent)','((length - 1) // 4) + 1','comfy.latent_formats.Wan21()','latent_format.process_out(latent) * mask + latent * (1.0 - mask)'):self.assertIn(s,t)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
 def test_zero_workflow_census(self):
  c=Counter();jc=gc=0;targets={v[1] for v in SPECS.values()}
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if not n.endswith('.json'):continue
    jc+=1
    for g in graphs(json.loads(z.read(n))):
     gc+=1
     for q in g.get('nodes',[]):
      if q.get('type') in targets:c[q['type']]+=1
  self.assertEqual((512,768),(jc,gc));self.assertEqual({},dict(c))
 def test_shape_math_and_fragments(self):
  self.assertEqual((1,16,16,88,160),(1,16,(121-1)//8+1,704//8,1280//8));self.assertEqual((1,16,24,60,106),(1,16,(93-1)//4+1,480//8,848//8));
  for _,(_,ct,_,r) in SPECS.items():self.assertEqual(ct,catalog.load_json(catalog.CONTENT/'recipes'/r/'fragment.json')['nodes'][0]['classType'])
if __name__=='__main__':unittest.main()
