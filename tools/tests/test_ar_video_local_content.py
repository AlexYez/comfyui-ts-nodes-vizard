from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter,defaultdict
from typing import Any,Iterator
from tools import catalog
SPECS={'core.empty-ar-video-latent':('empty-ar-video-latent','EmptyARVideoLatent','sha256:0dc8b4c29d05242d6ee225f02d734f2c8c50a4f628b5ae8bdfaa88ec5b3a5726','empty-ar-video-latent'),'core.ar-video-i2v':('ar-video-i2v','ARVideoI2V','sha256:14ab675c422778cfc48f106a08e765f70b1006bff29502e12e5af8647242d9b2','ar-video-i2v')}
DOCS={'EmptyARVideoLatent':('b77d5f58cb23bb37c4d812ca9239c3cf611536de2d2cade3afd29ccbfe68f9d9','023b6e62ede8d0a5e69f2b4f13320d8c596d0ab826f90a6823c1bbd240240a56'),'ARVideoI2V':('1e92c0639e6fd3bb7424976be1022b365a858d35095b514625f8b732b41ac735','49cc14e776643e4c1f69e96dfd7e1c5444af036c5c79db406c0eefc2ac9561fc')}
def gs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from gs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from gs(y)
class ARVideoLocalTests(unittest.TestCase):
 def test_all(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};e=[]
  for aid,(slug,ct,fp,r) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));rp=catalog.CONTENT/'recipes'/r/'recipe.json';rec=catalog.load_json(rp);catalog.validate_recipe(rp,rec,ids,e);self.assertEqual([],catalog.json_schema_errors(rec,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),sch['recipe-fragment']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json'),sch['article-research']))
  self.assertEqual([],e);p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_ar_video.py';self.assertEqual('197337ea3fd11fa89b4e5f0347bd1bb4ee2741623bcf7f8886d3f62fe3aa1ad1',hashlib.sha256(p.read_bytes()).hexdigest());t=p.read_text(encoding='utf8');self.assertIn('ar_cfg["initial_latent"] = initial_latent',t);self.assertIn('((length - 1) // 4) + 1',t)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
  c=Counter();w=defaultdict(list)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if n.endswith('.json'):
     for g in gs(json.loads(z.read(n))):
      for q in g.get('nodes',[]):
       if q.get('type') in {'EmptyARVideoLatent','ARVideoI2V'}:c[q['type']]+=1;w[q['type']].append(q.get('widgets_values',[]))
  self.assertEqual({'ARVideoI2V':1},dict(c));self.assertEqual([[832,480,81,1]],w['ARVideoI2V'])

 def test_runtime_contract_and_pinned_ar_semantics(self):
  rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'))
  empty=rt['EmptyARVideoLatent'];i2v=rt['ARVideoI2V']
  self.assertEqual(['width','height','length','batch_size'],empty['input_order']['required'])
  self.assertEqual([16,8192,16],[empty['input']['required']['width'][1][k] for k in ('min','max','step')])
  self.assertEqual([1,1024,4],[empty['input']['required']['length'][1][k] for k in ('min','max','step')])
  self.assertEqual([1,64],[empty['input']['required']['batch_size'][1][k] for k in ('min','max')])
  self.assertEqual(['LATENT'],empty['output']);self.assertEqual(['LATENT'],empty['output_name'])
  self.assertEqual(['model','vae','start_image','width','height','length','batch_size'],i2v['input_order']['required'])
  self.assertEqual(['MODEL','LATENT'],i2v['output']);self.assertEqual(['MODEL','LATENT'],i2v['output_name'])
  source=(catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_ar_video.py').read_text(encoding='utf8')
  for marker in ('start_image[:1]','start_image[:, :, :, :3]','m = model.clone()','to = m.model_options.setdefault("transformer_options", {})','ar_cfg = to.setdefault("ar_config", {})','ar_cfg["initial_latent"] = initial_latent','[batch_size, 16, lat_t, height // 8, width // 8]'):
   self.assertIn(marker,source)
  sampler=(catalog.ROOT/'.comfyui-source-0.32.0/comfy/k_diffusion/sampling.py').read_text(encoding='utf8')
  for marker in ('initial_latent = transformer_options.get("ar_config", {}).get("initial_latent", None)','output[:, :, :n_init] = initial_latent','_ = model(initial_latent, zero_sigma * s_in, **extra_args)','current_start_frame = n_init','remaining = lat_t - n_init','transformer_options.pop("ar_state", None)'):
   self.assertIn(marker,sampler)

 def test_full_workflow_census_is_fail_closed(self):
  counts=Counter();json_count=root_count=subgraph_count=node_count=0
  wheel=catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl'
  with zipfile.ZipFile(wheel) as z:
   for name in z.namelist():
    if not name.endswith('.json'):continue
    json_count+=1;payload=json.loads(z.read(name))
    if not isinstance(payload,dict):continue
    scopes=list(gs(payload));has_root=isinstance(payload.get('nodes'),list)
    root_count+=int(has_root);subgraph_count+=len(scopes)-int(has_root)
    for graph in scopes:
     nodes=[node for node in graph.get('nodes',[]) if isinstance(node,dict)];node_count+=len(nodes)
     for node in nodes:
      if node.get('type') in {'EmptyARVideoLatent','ARVideoI2V'}:counts[node['type']]+=1
  self.assertEqual((512,496,272,8120),(json_count,root_count,subgraph_count,node_count))
  self.assertEqual(Counter({'ARVideoI2V':1}),counts)
if __name__=='__main__':unittest.main()
