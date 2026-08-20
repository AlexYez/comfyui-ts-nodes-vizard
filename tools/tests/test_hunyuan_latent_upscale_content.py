from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter,defaultdict
from typing import Any,Iterator
from tools import catalog
SPECS={'core.latent-upscale-model-loader':('latent-upscale-model-loader','LatentUpscaleModelLoader','sha256:fefa7d1773ca04f09c62822ca4a20916f03075570479f5915ad79329fa52ad92','hunyuan-video15-latent-upscale'),'core.hunyuan-video15-latent-upscale-with-model':('hunyuan-video15-latent-upscale-with-model','HunyuanVideo15LatentUpscaleWithModel','sha256:26416bfcf01834e81f95178829168675d81df3f0386b2e9d152d23e80b1b101c','hunyuan-video15-latent-upscale'),'core.empty-hunyuan-image-latent':('empty-hunyuan-image-latent','EmptyHunyuanImageLatent','sha256:9748f0795bc5f24e7c4b2c90d053a890424795dd4fafd34f34fb0dcd268deb42','empty-hunyuan-image-latent')}
DOCS={'LatentUpscaleModelLoader':('12033ee579531953cf24cc716d3d3adc93d427ec819c28103d1475b5154f3553','54f840375aba9f4000ce8930258323398b2872093e7d0557b5c92afa9766b819'),'HunyuanVideo15LatentUpscaleWithModel':('cf7223b2dc82afb9856368072e02cb978101f740d9a6bf03e6f0709c1943688f','f4245d4663c118e9fc2064b58167189937b20218e78f3b79d29e06a269faae45'),'EmptyHunyuanImageLatent':('ec7cbb49ae97c414fcfdfddf4a3defe50a9996ea53f8221237380468b8aab453','c878c1c437db40b749cb9f9268ccdc6db8401ae0e264cc2cfe0155fb1ebf8c0d')}
def graphs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from graphs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from graphs(y)
class HunyuanLatentUpscaleContentTests(unittest.TestCase):
 def test_schema_identity_honesty(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};errors=[];seen=set()
  for aid,(slug,ct,fp,recipe) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(p,a,errors);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));self.assertFalse(any(rt[ct].get(k,False) for k in ['api_node','experimental','deprecated','dev_only']));led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,sch['article-research']));self.assertFalse(led['checks']['exampleExecuted'])
   if recipe not in seen:
    seen.add(recipe);rp=catalog.CONTENT/'recipes'/recipe/'recipe.json';r=catalog.load_json(rp);self.assertEqual([],catalog.json_schema_errors(r,sch['recipe']));catalog.validate_recipe(rp,r,ids,errors);self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],errors)
 def test_source_docs(self):
  p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_hunyuan.py';self.assertEqual('97b684150cd18f9318d681abf4a4bc77929655d6f83ac49ad294ce913a60cc03',hashlib.sha256(p.read_bytes()).hexdigest());t=p.read_text(encoding='utf8')
  for s in ('return_metadata=True','"blocks.0.block.0.conv.weight"','"up.0.block.0.conv1.conv.weight"','width // 16, height // 16','{"samples": s.cpu().float()}','[batch_size, 64, height // 32, width // 32]'):self.assertIn(s,t)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
 def test_census_and_fragments(self):
  c=Counter();w=defaultdict(list);jc=gc=0;targets={v[1] for v in SPECS.values()}
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if not n.endswith('.json'):continue
    jc+=1
    for g in graphs(json.loads(z.read(n))):
     gc+=1
     for q in g.get('nodes',[]):
      if q.get('type') in targets:c[q['type']]+=1;w[q['type']].append(q.get('widgets_values',[]))
  self.assertEqual((512,768),(jc,gc));self.assertEqual(18,c['LatentUpscaleModelLoader']);self.assertEqual(2,c['HunyuanVideo15LatentUpscaleWithModel']);self.assertEqual(0,c['EmptyHunyuanImageLatent']);self.assertEqual([['bilinear',1920,1080,'disabled']]*2,w['HunyuanVideo15LatentUpscaleWithModel'])
  f=catalog.load_json(catalog.CONTENT/'recipes/hunyuan-video15-latent-upscale/fragment.json');self.assertEqual(['LatentUpscaleModelLoader','HunyuanVideo15LatentUpscaleWithModel'],[n['classType'] for n in f['nodes']]);self.assertEqual({'width':2048,'height':2048,'batch_size':1},catalog.load_json(catalog.CONTENT/'recipes/empty-hunyuan-image-latent/fragment.json')['nodes'][0]['settings'])
if __name__=='__main__':unittest.main()
