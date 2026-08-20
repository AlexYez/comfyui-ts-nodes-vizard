from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter,defaultdict
from typing import Any,Iterator
from tools import catalog
SPECS={'core.empty-chroma-radiance-latent-image':('empty-chroma-radiance-latent-image','EmptyChromaRadianceLatentImage','sha256:cc068235ccceb75a419d041d28f41ad9307a03a32a55b7ac680c3fab1285b462'),'core.chroma-radiance-options':('chroma-radiance-options','ChromaRadianceOptions','sha256:0d4248b9e29a31457f3154178e3974037280c42de1936701d9e8663d48a5586d')}
DOCS={'EmptyChromaRadianceLatentImage':('7f0a24f125769e2d4a748fee813f8f6869ee527bb494e2ff16b5cca3290737e4','2081f84668e557a9071197fd40326a3e7ef4d344caed53c04e87fbb69adaa217'),'ChromaRadianceOptions':('261de9115633d5a2864df31b91ea0e0586cc3efa8259052d72f3f0f4eed3b809','db433e51ada7ec8947e75e43b363886bc06891bc8f55dfb90fffae53c3d778aa')}
def gs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from gs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from gs(y)
class ChromaTests(unittest.TestCase):
 def test_all(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json'),sch['article-research']))
  for slug in ['empty-chroma-radiance-latent','chroma-radiance-tile-32']:
   rp=catalog.CONTENT/'recipes'/slug/'recipe.json';r=catalog.load_json(rp);catalog.validate_recipe(rp,r,ids,e);self.assertEqual([],catalog.json_schema_errors(r,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],e);p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_chroma_radiance.py';self.assertEqual('dbbdaa1d26592fa877529c562f38f3a8e804624e3fd12f1bb1d79e0215eaa2cc',hashlib.sha256(p.read_bytes()).hexdigest());t=p.read_text(encoding='utf8');self.assertIn('(batch_size, 3, height, width)',t);self.assertIn('if not radiance_options:',t);self.assertIn('return io.NodeOutput(model)',t);self.assertIn('sigma = args["timestep"].max().detach().cpu().item()',t);self.assertIn('if end_sigma <= sigma <= start_sigma:',t);self.assertIn('args | {"c": c}',t)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
  c=Counter();w=defaultdict(list);routes=Counter()
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if n.endswith('.json'):
     for g in gs(json.loads(z.read(n))):
      nodes={q.get('id'):q for q in g.get('nodes',[])}
      for q in nodes.values():
       if q.get('type') in {'EmptyChromaRadianceLatentImage','ChromaRadianceOptions'}:c[q['type']]+=1;w[q['type']].append(q.get('widgets_values',[]))
      for link in g.get('links',[]):
       if not isinstance(link,dict):continue
       source=nodes.get(link.get('origin_id'));target=nodes.get(link.get('target_id'))
       if source and source.get('type')=='EmptyChromaRadianceLatentImage':routes[(target.get('type'),link.get('target_slot'),link.get('type'))]+=1
  self.assertEqual({'EmptyChromaRadianceLatentImage':3,'ChromaRadianceOptions':1},dict(c));self.assertEqual(Counter({(1024,1024,1):2,(4096,4096,1):1}),Counter(map(tuple,w['EmptyChromaRadianceLatentImage'])));self.assertEqual([[True,1,0,-1]],w['ChromaRadianceOptions']);self.assertEqual(Counter({('SamplerCustomAdvanced',4,'LATENT'):1,('KSampler',3,'LATENT'):1,('SamplerCustom',5,'LATENT'):1}),routes)
if __name__=='__main__':unittest.main()
