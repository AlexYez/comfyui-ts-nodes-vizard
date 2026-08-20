from __future__ import annotations
import hashlib,json,re,subprocess,sys,unittest,zipfile
from pathlib import Path
from typing import Any,Iterator
from tools import catalog
SPECS={'core.regex-match':('regex-match','RegexMatch','sha256:24a465edf3c6c384600d459890b1e95a3f399b119abeb8222365626856784d14','regex-match-error-line'),'core.regex-extract':('regex-extract','RegexExtract','sha256:eb12903dc704cae05422cbb38775b779dccd8e7a50f8f0003116e35c99aa7dac','regex-extract-after-separator'),'core.regex-replace':('regex-replace','RegexReplace','sha256:efe42d9447d88e8da40217452315154dadd0434fb95dfa2aa8550990073f7c88','regex-strip-code-fence'),'core.json-extract-string':('json-extract-string','JsonExtractString','sha256:885c782fb93f5226ad487d08048e640839327a32a53bafd44b26eb75bcdcde41','json-extract-positive-prompt')}
DOCS={'RegexMatch':('d55b6cca8a9accaa1130976ae779262172f2409d063360883a3330830fbeaceb','22cfd806e8c692c43bd0c6e0a1f2f16e52a440ec218d435ddd7d4a08adfce478'),'RegexExtract':('7a61615ae5166ff9fecefd5b603db142bac6fa5ecb4fa528dca1087fd607f771','636e5071dfd08d144c33c820160f17ec494ebf287a129a4b2f0330fec31c9422'),'RegexReplace':('84cc193be8d7f642bae20858b3e3d5ae9b56e4daa4836c9cfaed236c61f7ba39','86eb075ba6a07120cf898e67a5e1ee7ea2387168979b02b9a564c1817decc8fe'),'JsonExtractString':('039e5cdcb895e05c0a7db1775af398397ac3cdc4b82ad03ec8f1d02f98fd4e35','b11309fb145f9c1723c006ac43d9a790f8133e1e3fbf9baca9cda6904412c91b')}
def graphs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from graphs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from graphs(y)
class RegexJsonContentTests(unittest.TestCase):
 def test_schemas_status_honesty_and_sections(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};errors=[]
  for aid,(d,ct,fp,rdir) in SPECS.items():
   ap=catalog.CONTENT/'articles/core'/d/'manifest.json';a=catalog.load_json(ap);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(ap,a,errors);self.assertEqual(('draft','in_review'),(a['status'],a['editorial']['state']));self.assertEqual(10,len(re.findall(r'^## ',(ap.parent/'ru.md').read_text(encoding='utf8'),re.M)))
   led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,sch['article-research']));self.assertFalse(led['checks']['exampleExecuted'])
   rp=catalog.CONTENT/'recipes'/rdir/'recipe.json';rec=catalog.load_json(rp);self.assertEqual([],catalog.json_schema_errors(rec,sch['recipe']));catalog.validate_recipe(rp,rec,ids,errors);self.assertNotIn('workflow',rec);self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],errors)
 def test_runtime_docs_source_probe_fail_closed(self):
  nodes=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'))
  for _,(_,ct,fp,_) in SPECS.items():self.assertEqual(fp,catalog.schema_fingerprint(ct,nodes[ct]));self.assertEqual('comfy_extras.nodes_string',nodes[ct]['python_module']);self.assertFalse(nodes[ct]['deprecated'] or nodes[ct]['experimental'])
  src=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_string.py';self.assertTrue(src.is_file());self.assertEqual('2faa05e02a8d21580a60902a4a3ff38610fd33bae1190c0c500a56d209740f04',hashlib.sha256(src.read_bytes()).hexdigest());docs=catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl';self.assertTrue(docs.is_file())
  with zipfile.ZipFile(docs) as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
  out=subprocess.run([sys.executable,str(Path(__file__).with_name('regex_json_synthetic_probe.py'))],cwd=catalog.ROOT,text=True,capture_output=True,check=True);self.assertTrue(json.loads(out.stdout)['replace_error'])
 def test_workflow_census(self):
  wf=catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl';self.assertTrue(wf.is_file());counts={ct:0 for _,ct,_,_ in SPECS.values()};jc=gc=0
  with zipfile.ZipFile(wf) as z:
   for n in z.namelist():
    if not n.endswith('.json'):continue
    jc+=1
    for g in graphs(json.loads(z.read(n))):
     gc+=1
     for node in g.get('nodes',[]):
      if node.get('type') in counts:counts[node['type']]+=1
  self.assertEqual((512,768),(jc,gc));self.assertEqual({'RegexMatch':0,'RegexExtract':14,'RegexReplace':10,'JsonExtractString':14},counts)
 def test_natural_russian(self):
  bad=re.compile(r'official case|source-derived|root workflow|human approved|No official|Human approval|Full API|Full LLM',re.I)
  for d,_,_,r in SPECS.values():
   for p in [catalog.CONTENT/'articles/core'/d/'ru.md',catalog.CONTENT/'recipes'/r/'ru.md',catalog.CONTENT/'research/reviews'/f"core.{d}.json"]:
    text=p.read_text(encoding='utf8');self.assertNotRegex(text,bad);self.assertNotIn('\ufffd',text)
if __name__=='__main__':unittest.main()
