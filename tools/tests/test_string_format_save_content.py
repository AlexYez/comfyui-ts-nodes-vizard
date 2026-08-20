from __future__ import annotations
import hashlib,json,re,subprocess,sys,unittest,zipfile
from pathlib import Path
from typing import Any,Iterator
from tools import catalog
SPECS={'core.string-format':('string-format','StringFormat','sha256:d2ef9a4897cb4c2218f774acf303bdb29f99206bbc03ef8c7cee1ad3516f0544','format-text-dimensions'),'core.convert-dictionary-to-string':('convert-dictionary-to-string','ConvertDictionaryToString','sha256:995c61869ec912f7816f71a37531fca8a30b42aa3ef0dd1ceb79d9fa7a126f4c','dictionary-to-json-pretty'),'core.convert-array-to-string':('convert-array-to-string','ConvertArrayToString','sha256:bc92ad15da2fd361b8332e5774b75cf1ad816cd771145e3b07530a3d255401ec','array-to-json-compact'),'core.save-text':('save-text','SaveText','sha256:9f57a4da42b1f61e83689d43868f13591d1cf0289bd133eef3d7b5acdf1a00a1','save-text-json-output')}
DOCS={'StringFormat':('124d201a9c2e08d22137043cc13c0a5b5a0a0f6cbd825227745be95e50d51c5a','33bb90294b6a638611f8973890803335892a198866b75264e332c25b54d44625'),'ConvertDictionaryToString':('6b89ddc4936d0454fbeb8538783c5687d672d5bbab111472062509af93be31da','1150ff5d3aa508f4006880fa3202efefd53eda9127203fb862e8b138b35b735f'),'ConvertArrayToString':('b7ced1676d91717e8b2c9007746208594e00208229b2238e9d727d75594bdc79','b7323fa552e8b04754dd8a385e5346dd87f384697e1d93f4d175bd28c509db45'),'SaveText':('20b986d5dd73e672ec6973cbf164725b8c25727f1fbc77763fe630e9e4242bdd','2c41031c5cc0871a1f6e61a52bc556ddd66f89f95112e6358d218920af2c7729')}
def graphs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from graphs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from graphs(y)
class StringFormatSaveContentTests(unittest.TestCase):
 def test_schemas_sections_status(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};errors=[]
  for aid,(d,ct,fp,rdir) in SPECS.items():
   ap=catalog.CONTENT/'articles/core'/d/'manifest.json';a=catalog.load_json(ap);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(ap,a,errors);self.assertEqual(('draft','in_review'),(a['status'],a['editorial']['state']));self.assertEqual(10,len(re.findall(r'^## ',(ap.parent/'ru.md').read_text(encoding='utf8'),re.M)));led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,sch['article-research']));self.assertFalse(led['checks']['exampleExecuted']);rp=catalog.CONTENT/'recipes'/rdir/'recipe.json';rec=catalog.load_json(rp);self.assertEqual([],catalog.json_schema_errors(rec,sch['recipe']));catalog.validate_recipe(rp,rec,ids,errors);self.assertNotIn('workflow',rec);self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],errors)
 def test_runtime_docs_source_and_safe_probe(self):
  nodes=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'))
  for _,(_,ct,fp,_) in SPECS.items():self.assertEqual(fp,catalog.schema_fingerprint(ct,nodes[ct]));self.assertFalse(nodes[ct]['experimental'] or nodes[ct]['deprecated'])
  self.assertEqual('2faa05e02a8d21580a60902a4a3ff38610fd33bae1190c0c500a56d209740f04',hashlib.sha256((catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_string.py').read_bytes()).hexdigest());self.assertEqual('396565301e4f0a9cf0f9eaf823871569d02f7a198d6fdce5f9db936c105ceacc',hashlib.sha256((catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_text.py').read_bytes()).hexdigest());docs=catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl';self.assertTrue(docs.is_file())
  with zipfile.ZipFile(docs) as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
  out=subprocess.run([sys.executable,str(Path(__file__).with_name('string_format_save_synthetic_probe.py'))],cwd=catalog.ROOT,text=True,capture_output=True,check=True);self.assertTrue(json.loads(out.stdout)['saved'])
 def test_workflow_census(self):
  wf=catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl';counts={ct:0 for _,ct,_,_ in SPECS.values()};jc=gc=0
  with zipfile.ZipFile(wf) as z:
   for n in z.namelist():
    if not n.endswith('.json'):continue
    jc+=1
    for g in graphs(json.loads(z.read(n))):
     gc+=1
     for node in g.get('nodes',[]):
      if node.get('type') in counts:counts[node['type']]+=1
  self.assertEqual((512,768),(jc,gc));self.assertEqual({'StringFormat':0,'ConvertDictionaryToString':0,'ConvertArrayToString':0,'SaveText':11},counts)
 def test_natural_russian(self):
  bad=re.compile(r'official case|source-derived|root workflow|human approved|Recipe fragment|Actual source|exact nodes|in 768 graphs',re.I)
  for aid,(d,_,_,r) in SPECS.items():
   for p in [catalog.CONTENT/'articles/core'/d/'ru.md',catalog.CONTENT/'recipes'/r/'ru.md',catalog.CONTENT/'research/reviews'/f'{aid}.json']:
    text=p.read_text(encoding='utf8');self.assertNotRegex(text,bad);self.assertNotIn('\ufffd',text)
if __name__=='__main__':unittest.main()
