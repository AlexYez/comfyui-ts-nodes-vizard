from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter,defaultdict
from typing import Any,Iterator
from tools import catalog
SPECS={'core.reference-latent':('reference-latent','ReferenceLatent','sha256:94067f5312eb49d03cb7c4957166b05b1ca00c7fee9de8e2b9e91f2eb5b8ed33'),'core.lotus-conditioning':('lotus-conditioning','LotusConditioning','sha256:e7123beed81fe1fdbe24cbff090cfc9f46f08a7ddd8a0c586532c74038e75938'),'core.pid-conditioning':('pid-conditioning','PiDConditioning','sha256:e14004a9cfbcc0b47d67c81e7fc514b75e4a57a67d93e38e7b6f22e770da02a5'),'core.bernini-conditioning':('bernini-conditioning','BerniniConditioning','sha256:70bbc6f01135a8abb49e796ef23dd8035585b330a37dcead686eebcefde29ad2')}
HASHES={'nodes_edit_model.py':'3773fd748c404758ee36a3bac24cfea6e10c1b9990fa388cc440c56db1dc6a4a','nodes_lotus.py':'22214b949a7f060fe0a9d1bbe68dc5ed3473dadd1fa0752354d7f41c3f083021','nodes_pid.py':'f55f3308be386edff8b11820146dee9276ab62803b8685d854d6891fcbe610f5','nodes_bernini.py':'c928d6d487d7533f8e30b3b5b0bcbb3d97adc4ccb907f14ddcb07cedd1d9e264'}
DOCS={'ReferenceLatent':('2c10d037ca363d0ac2b3d49e1434a6d7bf51dd9f0ccdffb8b19b3db4ed906eeb','7209a16387800409c028a502cc5e530ee1f9ec5c9003ca1b875fa8e23f52470c'),'LotusConditioning':('8d997ad6d7790b538700b5f0c07feeeaad2fe624301b53c833392bb5ebb8416e','642ed00cab35af6b0957f2630c833db520c8020355d358a57409bebb6f4058b3'),'PiDConditioning':('42a91e5899fe749ade4e3ba70f6e3831054b24a22076cdb64064c7984c11155d','a17c8514ba75e36fcf5f17d996c35090ddccb0362eefdcd0d5d4b63e9182afe8'),'BerniniConditioning':('6fe13a327199374eba2f0b8de994871cfafc4b774d0ab21af0e9fac5c9b041a5','ac9f1b6a1764e59886a74f0e9776797110b36bf6aa4835fb2befad5d24e736e9')}
def gs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from gs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  for y in (x.get('definitions') or {}).get('subgraphs',[]):yield from gs(y)
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,sch['article-research']));self.assertFalse(q['checks']['exampleExecuted'])
  for slug in ['reference-latent-edit','lotus-null-conditioning','pid-flux-clean-latent','bernini-video-edit-official']:
   p=catalog.CONTENT/'recipes'/slug/'recipe.json';r=catalog.load_json(p);catalog.validate_recipe(p,r,ids,e);self.assertEqual([],catalog.json_schema_errors(r,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(p.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],e)
 def test_sources(self):
  for n,h in HASHES.items():self.assertEqual(h,hashlib.sha256((catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras'/n).read_bytes()).hexdigest())
  ref=(catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_edit_model.py').read_text('utf8');self.assertIn('{"reference_latents": [latent["samples"]]}, append=True',ref)
  pid=(catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_pid.py').read_text('utf8');self.assertIn('samples.shape[1] == 128',pid);self.assertIn('lq_latent[:, :, 0]',pid)
  bern=(catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_bernini.py').read_text('utf8');self.assertIn('((length - 1) // 4) + 1',bern);self.assertIn('for name in sorted(reference_images)',bern)
 def test_docs_and_census(self):
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
  c=Counter();w=defaultdict(list)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   names=[n for n in z.namelist() if n.endswith('.json')];self.assertEqual(512,len(names))
   for n in names:
    for g in gs(json.loads(z.read(n))):
     for q in g.get('nodes',[]):
      if q.get('type') in {x[1] for x in SPECS.values()}:c[q['type']]+=1;w[q['type']].append(q.get('widgets_values',[]))
  self.assertEqual({'ReferenceLatent':46,'LotusConditioning':5,'PiDConditioning':1,'BerniniConditioning':2},dict(c));self.assertEqual([['flux',0]],w['PiDConditioning']);self.assertCountEqual([[928,1280,1,1,848],[480,832,81,1,848]],w['BerniniConditioning'])
 def test_shapes_and_fragments(self):
  self.assertEqual((1,16,21,104,60),(1,16,((81-1)//4)+1,832//8,480//8));f=catalog.load_json(catalog.CONTENT/'recipes/bernini-video-edit-official/fragment.json');self.assertEqual({'width':480,'height':832,'length':81,'batch_size':1,'ref_max_size':848},f['nodes'][0]['settings']);self.assertEqual('flux',catalog.load_json(catalog.CONTENT/'recipes/pid-flux-clean-latent/fragment.json')['nodes'][0]['settings']['latent_format'])
if __name__=='__main__':unittest.main()
