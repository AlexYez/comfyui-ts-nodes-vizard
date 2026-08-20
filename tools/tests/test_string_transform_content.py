from __future__ import annotations
import hashlib,json,re,subprocess,sys,unittest,zipfile
from pathlib import Path
from typing import Any,Iterator
from tools import catalog
SPECS={
'core.case-converter':('case-converter','CaseConverter','sha256:0cfede9a07f458878da5da066e7e4527a06f1760bd64d7233c4dbbcbaaef785f','convert-text-case-title'),
'core.string-trim':('string-trim','StringTrim','sha256:aef68e8c7b07a9b5ac7c7d83af79f5136ba02876c3c8b094afdbf96b01e1c458','trim-text-both-sides'),
'core.string-replace':('string-replace','StringReplace','sha256:75afd25adba7bcd55179aefc0c3dfeb0479f23f1166754ff4b67dddcd56f4749','replace-text-placeholder'),
'core.string-concatenate':('string-concatenate','StringConcatenate','sha256:b2460674ecbc26b26f7c7352ecc056a9375f252c4ff1af150b264e6b3edd7e2a','concatenate-prompt-lines')}
DOCS={'CaseConverter':('8ab6f6e0fda2dc887e09fb764a2a6002f1abb01453234f894c79d0dbd4aab8df','5b6ea1c1196526c0e5472f1b00ac54a47287e22aa442a2c7e34120c4f1dc07cd'),'StringTrim':('0951a5f665ee0a1926ad9d964f2e477baad350fc874e30a66e8c05cce5b2220a','437a100ef9554b706accc9cee9f58dbd02483fb4ca4bb29d084c83b0dee6484c'),'StringReplace':('efab94497d6661d95e44191b0ec7ef1e77576e5637a3be789c385bcab658c066','5a5baec7266d637fde1d15224b29b2bade1ef78eb738518d4cf78c980de2ac7c'),'StringConcatenate':('6744fd12e6e57c5dba0fbdf2aeeda718dda317cfd1cb10451ff3a7407d430e6c','09e5ae277775e77867d7abf3a892c514391627d35b9a672ada7647b3e723877f')}
def graphs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x: yield from graphs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list): yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]): yield from graphs(y)
class StringTransformContentTests(unittest.TestCase):
 def test_schema_honesty_and_ten_sections(self):
  schemas={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']}; ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')}; errors=[]
  for aid,(d,ct,fp,rdir) in SPECS.items():
   ap=catalog.CONTENT/'articles/core'/d/'manifest.json'; a=catalog.load_json(ap); self.assertEqual([],catalog.json_schema_errors(a,schemas['article'])); catalog.validate_article(ap,a,errors); self.assertEqual(('draft','in_review'),(a['status'],a['editorial']['state'])); self.assertEqual(10,len(re.findall(r'^## ',(ap.parent/'ru.md').read_text(encoding='utf8'),re.M)))
   led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json'); self.assertEqual([],catalog.json_schema_errors(led,schemas['article-research'])); self.assertFalse(led['checks']['exampleExecuted'])
   rp=catalog.CONTENT/'recipes'/rdir/'recipe.json'; rec=catalog.load_json(rp); self.assertEqual([],catalog.json_schema_errors(rec,schemas['recipe'])); catalog.validate_recipe(rp,rec,ids,errors); self.assertNotIn('workflow',rec); self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),schemas['recipe-fragment']))
  self.assertEqual([],errors)
 def test_runtime_source_docs_and_probe_fail_closed(self):
  nodes=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'))
  for _,(_,ct,fp,_) in SPECS.items(): self.assertEqual(fp,catalog.schema_fingerprint(ct,nodes[ct])); self.assertEqual('comfy_extras.nodes_string',nodes[ct]['python_module']); self.assertFalse(nodes[ct]['experimental'] or nodes[ct]['deprecated'])
  src=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_string.py'; self.assertTrue(src.is_file()); self.assertEqual('2faa05e02a8d21580a60902a4a3ff38610fd33bae1190c0c500a56d209740f04',hashlib.sha256(src.read_bytes()).hexdigest())
  docs=catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl'; self.assertTrue(docs.is_file())
  with zipfile.ZipFile(docs) as z:
   for ct,(en,ru) in DOCS.items(): self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest()); self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
  out=subprocess.run([sys.executable,str(Path(__file__).with_name('string_transform_synthetic_probe.py'))],cwd=catalog.ROOT,text=True,capture_output=True,check=True); self.assertEqual('STRASSE',json.loads(out.stdout)['case'])
 def test_official_workflow_counts(self):
  wf=catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl'; self.assertTrue(wf.is_file()); counts={ct:0 for _,ct,_,_ in SPECS.values()}; jc=gc=0
  with zipfile.ZipFile(wf) as z:
   for n in z.namelist():
    if not n.endswith('.json'): continue
    jc+=1
    for g in graphs(json.loads(z.read(n))):
     gc+=1
     for node in g.get('nodes',[]):
      if node.get('type') in counts: counts[node['type']]+=1
  self.assertEqual((512,768),(jc,gc)); self.assertEqual({'CaseConverter':0,'StringTrim':0,'StringReplace':31,'StringConcatenate':62},counts)
 def test_natural_russian(self):
  bad=re.compile(r'official case|source-derived|root workflow|human approved|без воды|важно отметить',re.I)
  for d,_,_,r in SPECS.values():
   for p in [catalog.CONTENT/'articles/core'/d/'ru.md',catalog.CONTENT/'recipes'/r/'ru.md']: text=p.read_text(encoding='utf8'); self.assertNotRegex(text,bad); self.assertNotIn('\ufffd',text)
if __name__=='__main__': unittest.main()
