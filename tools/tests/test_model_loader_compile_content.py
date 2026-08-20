from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from tools import catalog
SPECS={'core.lora-loader-bypass':('lora-loader-bypass','LoraLoaderBypass','sha256:163c448507fd27590a51e30fa770bba4bde86d62bb179986e5228f8b6a4abdec'),'core.lora-loader-bypass-model-only':('lora-loader-bypass-model-only','LoraLoaderBypassModelOnly','sha256:6bc5784a7a8629107dcff3162f832c97bdde4e67b77746f96de366541d075548'),'core.model-patch-loader':('model-patch-loader','ModelPatchLoader','sha256:534b86bcf51b687b68e5b6fac64aa42a0701a3a26ba867b42c8e9b271c38b3ed'),'core.torch-compile-model':('torch-compile-model','TorchCompileModel','sha256:e8367cdc1d324a311d698299d212b4874894ee749baf62df24a2c990c95ceae3')}
HASHES={'nodes_lora_debug.py':'5fdda8b51e0a8148c97deb898f5e4947a6eaa1904fdd8e2b7a94ded224e8ab25','nodes_model_patch.py':'f8fd8b9281e8926536c71867ccf1529a41fe690ba2ed12db8f58251ba32cbc76','nodes_torch_compile.py':'2b1a0c2a0f912c69f9249a88e57f8ce27034ed06632bba6bbadfa06f8796ceb1'}
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  a_s=catalog.load_json(catalog.CONTENT/'schemas/article.schema.v1.json');r_s=catalog.load_json(catalog.CONTENT/'schemas/article-research.schema.v1.json');rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,a_s));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,r_s));self.assertFalse(q['checks']['exampleExecuted'])
  self.assertEqual([],e)
 def test_sources(self):
  base=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras'
  for n,h in HASHES.items():self.assertEqual(h,hashlib.sha256((base/n).read_bytes()).hexdigest())
  l=(base/'nodes_lora_debug.py').read_text('utf8');self.assertIn('strength_model == 0 and strength_clip == 0',l);self.assertIn('load_bypass_lora_for_models',l);self.assertIn('if self.loaded_lora[0] == lora_path:',l)
  sd=catalog.ROOT/'.comfyui-source-0.32.0/comfy/sd.py';self.assertEqual('51e72a263e8bd77812aefcebcf3cfaf9fda57150d763897b6d8b4890d7fee207',hashlib.sha256(sd.read_bytes()).hexdigest());s=sd.read_text('utf8');self.assertIn('bypass_patches = {}',s);self.assertIn('regular_patches = {}',s);self.assertIn('isinstance(patch_data, comfy.weight_adapter.WeightAdapterBase)',s);self.assertIn('new_modelpatcher.add_patches(regular_patches, strength_model)',s);self.assertIn('set_injections("bypass_lora", injections)',s);self.assertIn('logging.warning(f"NOT LOADED: {x}',s)
  p=(base/'nodes_model_patch.py').read_text('utf8');self.assertIn("'lllite_conditioning1.conv1.weight'",p);self.assertIn('duration_head.attention_pooler.query_tokens',p);self.assertIn('audio_proj.proj1.weight',p);self.assertIn('input_hint_block.0.weight',p)
  t=(base/'nodes_torch_compile.py').read_text('utf8');self.assertIn('clone(disable_dynamic=True)',t);self.assertIn('guard_filter_fn',t)
  helper=catalog.ROOT/'.comfyui-source-0.32.0/comfy_api/torch_helpers/torch_compile.py';self.assertEqual('203e4a407fc0e81bba6304deff4c6d9806d9251d32d89d0cbea6aa8b3373feae',hashlib.sha256(helper.read_bytes()).hexdigest());h=helper.read_text('utf8');self.assertIn('keys: list[str]=["diffusion_model"]',h);self.assertIn('model.remove_wrappers_with_key',h);self.assertIn('model.model_options[TORCH_COMPILE_KWARGS] = compile_kwargs',h);self.assertIn('finally:',h)
 def test_bypass_nodes_absent_from_official_workflows(self):
  files=roots=subgraphs=nodes=hits=0
  def scopes(value):
   if isinstance(value,list):
    for item in value:yield from scopes(item)
   elif isinstance(value,dict):
    if isinstance(value.get('nodes'),list):yield value
    definitions=value.get('definitions')
    if isinstance(definitions,dict):
     for item in definitions.get('subgraphs',[]):yield from scopes(item)
  with zipfile.ZipFile(catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl') as archive:
   for name in archive.namelist():
    if not name.endswith('.json'):continue
    files+=1;all_scopes=list(scopes(json.loads(archive.read(name))));roots+=bool(all_scopes);subgraphs+=max(0,len(all_scopes)-1)
    for graph in all_scopes:
     graph_nodes=graph.get('nodes',[]);nodes+=len(graph_nodes);hits+=sum(node.get('type') in {'LoraLoaderBypass','LoraLoaderBypassModelOnly','TorchCompileModel'} for node in graph_nodes)
  self.assertEqual((512,496,272,8120,0),(files,roots,subgraphs,nodes,hits))
if __name__=='__main__':unittest.main()
