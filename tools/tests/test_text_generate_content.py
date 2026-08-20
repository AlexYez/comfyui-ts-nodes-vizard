from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from typing import Any,Iterator
from tools import catalog
SPECS={'core.text-generate':('text-generate','TextGenerate','sha256:6b4c83043530f7a2dd1bdbd89f130465f17ef4fc9e02ce15b6c63607955c3c92','generate-multimodal-text'),'core.text-generate-ltx2-prompt':('text-generate-ltx2-prompt','TextGenerateLTX2Prompt','sha256:b1360b6b6f8f2030d707f3ef8be8a922139709bd7cc508f57b1a6d01ee26405d','enhance-ltx2-video-prompt')}
DOCS={'TextGenerate':('d0ed7daea748dff76069bfda6f7e296b7c6b3da3287dfd96a95423a880db45b3','26439ccaa1362d6478c19725b838235de340662c151131b197672b2f362239f7'),'TextGenerateLTX2Prompt':('0247ca6cdc43fd1600669caf015cc0a75c3a37cbad778a3c5f2617e04af64f28','8f19e497a406c3c639351ba29d1d64bbbc5a124ddd2b5639cfdbb64822c111f3')}
def graphs(x:Any)->Iterator[dict[str,Any]]:
 if isinstance(x,list):
  for y in x:yield from graphs(y)
 elif isinstance(x,dict):
  if isinstance(x.get('nodes'),list):yield x
  d=x.get('definitions')
  if isinstance(d,dict):
   for y in d.get('subgraphs',[]):yield from graphs(y)
class TextGenerateContentTests(unittest.TestCase):
 def test_schema_runtime_docs_source(self):
  sch={n:catalog.load_json(catalog.CONTENT/f'schemas/{n}.schema.v1.json') for n in ['article','recipe','recipe-fragment','article-research']};ids={catalog.load_json(p)['articleId'] for p in (catalog.CONTENT/'articles').rglob('manifest.json')};nodes=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(d,ct,fp,r) in SPECS.items():
   ap=catalog.CONTENT/'articles/core'/d/'manifest.json';a=catalog.load_json(ap);self.assertEqual([],catalog.json_schema_errors(a,sch['article']));catalog.validate_article(ap,a,e);self.assertEqual(10,len(re.findall(r'^## ',(ap.parent/'ru.md').read_text(encoding='utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,nodes[ct]));self.assertFalse(nodes[ct]['experimental'] or nodes[ct]['deprecated']);led=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(led,sch['article-research']));rp=catalog.CONTENT/'recipes'/r/'recipe.json';rec=catalog.load_json(rp);catalog.validate_recipe(rp,rec,ids,e);self.assertEqual([],catalog.json_schema_errors(rec,sch['recipe']));self.assertEqual([],catalog.json_schema_errors(catalog.load_json(rp.parent/'fragment.json'),sch['recipe-fragment']))
  self.assertEqual([],e);src=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_textgen.py';self.assertEqual('af31d647c7be5fa4d406e3286a1f042710d78a8811707353faf5bffcb8014fbf',hashlib.sha256(src.read_bytes()).hexdigest());t=src.read_text(encoding='utf8');self.assertIn('clip.generate(',t);self.assertIn('is_gemma4 = "gemma4" in',t);self.assertIn('re.sub(r"<think>.*?</think>"',t)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_embedded_docs-0.5.9-py3-none-any.whl') as z:
   for ct,(en,ru) in DOCS.items():self.assertEqual(en,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/en.md')).hexdigest());self.assertEqual(ru,hashlib.sha256(z.read(f'comfyui_embedded_docs/docs/{ct}/ru.md')).hexdigest())
 def test_exact_workflow_census(self):
  c={'TextGenerate':0,'TextGenerateLTX2Prompt':0};modes=[];widgets=[];jc=gc=0
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as z:
   for n in z.namelist():
    if not n.endswith('.json'):continue
    jc+=1
    for g in graphs(json.loads(z.read(n))):
     gc+=1
     for node in g.get('nodes',[]):
      if node.get('type') in c:c[node['type']]+=1;modes.append((node['type'],node.get('mode',0)));widgets.append((n,node['type'],node.get('widgets_values',[])))
  self.assertEqual((512,768),(jc,gc));self.assertEqual({'TextGenerate':13,'TextGenerateLTX2Prompt':9},c);self.assertEqual(1,sum(t=='TextGenerateLTX2Prompt' and m==4 for t,m in modes));self.assertEqual(3,sum(t=='TextGenerateLTX2Prompt' and len(w)>7 and w[1]==600 and w[7]==1.15 for _,t,w in widgets))
if __name__=='__main__':unittest.main()
