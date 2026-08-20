from __future__ import annotations

import hashlib, json, re, subprocess, sys, unittest, zipfile
from pathlib import Path
from typing import Any, Iterator
from tools import catalog

SPECS={
"core.string-compare":("string-compare","StringCompare","sha256:f4ba9134218ba53330ec54b1015fff6ea627d126c2adfa61e4a92d77e0f560cd","compare-text-prefix"),
"core.string-contains":("string-contains","StringContains","sha256:cf2e50fba64d1de1a51a678ded30d7ea4f2234d4e44a4ba1fa0658adf209f571","contains-text-literal"),
"core.string-length":("string-length","StringLength","sha256:9a1efb643f9e54e23f55530936a77867c692b971bf396e3279649d0bd25b9bf5","measure-text-length"),
"core.string-substring":("string-substring","StringSubstring","sha256:22842e4689dbc388ea0621d0f5897a4994a78860c502eaa5d32cae15adeae1b2","substring-first-characters")}
DOCS={"StringCompare":("92571c2437627416c4b36fc1841456586e2fa53fc57d041e85fc268cf3640350","552d26311d7dae7916572a4511c08461604c42939d930a7fe5dea1b25735b3a5"),"StringContains":("3e3512acbd21ae42093f63917cc34926d87c5ef837185cda455b02343053dfb2","53e66598191f9f2febdb6e1c2e6188b06278fc1c3f107b5433a29705757eb440"),"StringLength":("0d0fe43c03f4281cb4f7e8946e788ac8c21bfac7fff6417335ce38a58e89505c","19efc146ab132f4e2897a9761dee929dc9b2ecf122215dad723c82e8eebf90d3"),"StringSubstring":("3d3ef28410b463747fca413df79c54e225962724e84d3259447301aa5c90c6a5","ca68fb0945ada8606792f081dfb95b382322d80370d609cb9ee13d3e63112c2f")}

def graphs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x: yield from graphs(y)
 elif isinstance(x,dict):
  if isinstance(x.get("nodes"),list): yield x
  d=x.get("definitions")
  if isinstance(d,dict):
   for y in d.get("subgraphs",[]): yield from graphs(y)

class StringCompareSliceContentTests(unittest.TestCase):
 def test_content_schemas_status_and_ten_sections(self):
  schemas={n:catalog.load_json(catalog.CONTENT/f"schemas/{n}.schema.v1.json") for n in ["article","recipe","recipe-fragment","article-research"]}; ids={catalog.load_json(p)["articleId"] for p in (catalog.CONTENT/"articles").rglob("manifest.json")}; errors=[]
  for aid,(directory,ct,fp,recipe_dir) in SPECS.items():
   p=catalog.CONTENT/"articles/core"/directory/"manifest.json"; a=catalog.load_json(p); self.assertEqual([],catalog.json_schema_errors(a,schemas["article"])); catalog.validate_article(p,a,errors); self.assertEqual("draft",a["status"]); self.assertEqual("in_review",a["editorial"]["state"]); self.assertEqual(10,len(re.findall(r"^## ",(p.parent/"ru.md").read_text(encoding="utf8"),re.M)))
   r=catalog.load_json(catalog.CONTENT/"research/reviews"/f"{aid}.json"); self.assertEqual([],catalog.json_schema_errors(r,schemas["article-research"])); self.assertFalse(r["checks"]["exampleExecuted"])
   rp=catalog.CONTENT/"recipes"/recipe_dir/"recipe.json"; rec=catalog.load_json(rp); self.assertEqual([],catalog.json_schema_errors(rec,schemas["recipe"])); catalog.validate_recipe(rp,rec,ids,errors); self.assertNotIn("workflow",rec); frag=catalog.load_json(rp.parent/"fragment.json"); self.assertEqual([],catalog.json_schema_errors(frag,schemas["recipe-fragment"]))
  self.assertEqual([],errors)
 def test_runtime_and_exact_source_probe(self):
  nodes=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/"runtime/comfyui-0.32.0.object-info.json"))
  for aid,(directory,ct,fp,_) in SPECS.items():
   self.assertEqual(fp,catalog.schema_fingerprint(ct,nodes[ct])); self.assertEqual("comfy_extras.nodes_string",nodes[ct]["python_module"]); self.assertFalse(nodes[ct]["experimental"]); self.assertFalse(nodes[ct]["deprecated"])
  src=catalog.ROOT/".comfyui-source-0.32.0/comfy_extras/nodes_string.py"; self.assertTrue(src.is_file()); self.assertEqual("2faa05e02a8d21580a60902a4a3ff38610fd33bae1190c0c500a56d209740f04",hashlib.sha256(src.read_bytes()).hexdigest())
  p=subprocess.run([sys.executable,str(Path(__file__).with_name("string_compare_slice_synthetic_probe.py"))],cwd=catalog.ROOT,text=True,capture_output=True,check=True); self.assertEqual(3,json.loads(p.stdout)["length"])
 def test_docs_and_workflow_census_fail_closed(self):
  docs=catalog.ROOT/".upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl"; wf=catalog.ROOT/".upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"; self.assertTrue(docs.is_file()); self.assertTrue(wf.is_file())
  with zipfile.ZipFile(docs) as z:
   for ct,(en,ru) in DOCS.items(): self.assertEqual(en,hashlib.sha256(z.read(f"comfyui_embedded_docs/docs/{ct}/en.md")).hexdigest()); self.assertEqual(ru,hashlib.sha256(z.read(f"comfyui_embedded_docs/docs/{ct}/ru.md")).hexdigest())
  counts={ct:0 for _,ct,_,_ in SPECS.values()}; vals=[]; gc=jc=0
  with zipfile.ZipFile(wf) as z:
   for n in z.namelist():
    if not n.endswith(".json"): continue
    jc+=1
    for g in graphs(json.loads(z.read(n))):
     gc+=1
     for node in g.get("nodes",[]):
      if node.get("type") in counts: counts[node["type"]]+=1; vals.append(node.get("widgets_values"))
  self.assertEqual((512,768),(jc,gc)); self.assertEqual({"StringCompare":1,"StringContains":0,"StringLength":0,"StringSubstring":0},counts); self.assertEqual([["Nano Banana 2","nano banana 2","Starts With",False]],vals)
 def test_natural_russian(self):
  for directory,_,_,recipe in SPECS.values():
   for p in [catalog.CONTENT/"articles/core"/directory/"ru.md",catalog.CONTENT/"recipes"/recipe/"ru.md"]:
    text=p.read_text(encoding="utf8"); self.assertNotIn("\ufffd",text); self.assertNotRegex(text,re.compile(r"official case|source-derived|root workflow|human approved",re.I))

if __name__=="__main__": unittest.main()
