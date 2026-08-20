from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter
from typing import Any,Iterator
from tools import catalog
SPECS={'core.frame-interpolation-model-loader':('frame-interpolation-model-loader','FrameInterpolationModelLoader','sha256:3ec66050284348929e57a70da0f32f03d3fb8ba8a9ef34df4c2cb6fed51d4bb3'),'core.frame-interpolate':('frame-interpolate','FrameInterpolate','sha256:04ed5363c8c2647326e14e33d9a6691526dc7774288f2024128e88c4b1e7c601'),'core.optical-flow-loader':('optical-flow-loader','OpticalFlowLoader','sha256:0e4b67a85e2a7806c3a373214a358e5550feb939868f0b58cc0660d8a63ca1ec'),'core.glsl-shader':('glsl-shader','GLSLShader','sha256:fa342b5af953ef31bd00a6d6e005d97c5d2fd24c4ab5c3f1695c447b32b49e43')}
HASHES={'nodes_frame_interpolation.py':'ff30a5795d371ed833019d5b156d5139325ac05f2f87f2ec0ab61960b8f0e394','nodes_void.py':'242dcd84baf0a7934cd3c980f01d6c73992abc7f4b2e18d87712619a7425af90','nodes_glsl.py':'8d9d661a480855155b7d1207597ca38257b85ca7f7cdaf5c7af6fd51a5a68a50'}
def scopes(value:Any)->Iterator[dict[str,Any]]:
 if isinstance(value,list):
  for item in value:yield from scopes(item)
 elif isinstance(value,dict):
  if isinstance(value.get('nodes'),list):yield value
  definitions=value.get('definitions')
  if isinstance(definitions,dict):
   for item in definitions.get('subgraphs',[]):yield from scopes(item)
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  a_s=catalog.load_json(catalog.CONTENT/'schemas/article.schema.v1.json');r_s=catalog.load_json(catalog.CONTENT/'schemas/article-research.schema.v1.json');rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,a_s));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,r_s));self.assertFalse(q['checks']['exampleExecuted'])
  self.assertEqual([],e)
 def test_sources(self):
  base=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras'
  for n,h in HASHES.items():self.assertEqual(h,hashlib.sha256((base/n).read_bytes()).hexdigest())
  f=(base/'nodes_frame_interpolation.py').read_text('utf8');self.assertIn('total_out_frames = total_pairs * multiplier + 1',f);self.assertIn('batch = max(1, batch // 2)',f);self.assertIn('Unrecognized frame interpolation model format',f);self.assertIn('load_torch_file(model_path, safe_load=True)',f);self.assertIn('torch.empty((total_out_frames, 3, H, W)',f);self.assertIn('multi_fn = None  # fall through to single-timestep path',f);self.assertIn('return io.NodeOutput(images)',f)
  v=(base/'nodes_void.py').read_text('utf8');self.assertIn('feature_encoder.',v);self.assertIn('raft_large(weights=None',v)
  g=(base/'nodes_glsl.py').read_text('utf8');self.assertIn('At least one input image is required',g);self.assertIn('u_resolution',g);self.assertIn('layout(location = 3)',g);self.assertIn("re.search(r'#pragma\\s+passes\\s+(\\d+)'",g);self.assertIn('gl.GL_RGBA32F',g);self.assertIn('batch_outputs.append(black_img)',g);self.assertIn('img_tensor[batch_idx].cpu().numpy().astype(np.float32)',g)
 def test_official_workflow_cases(self):
  wanted={'FrameInterpolationModelLoader','FrameInterpolate','OpticalFlowLoader'};counts=Counter();widgets={};members={};links=[];glsl_count=0;glsl_modes=Counter();glsl_members=Counter();files=roots=subgraphs=nodes=0
  wheel=catalog.ROOT/'.upstream-cache/comfyui_workflow_templates_json-0.1.42-py3-none-any.whl'
  with zipfile.ZipFile(wheel) as archive:
   for name in archive.namelist():
    if not name.endswith('.json'):continue
    files+=1;all_scopes=list(scopes(json.loads(archive.read(name))));roots+=bool(all_scopes);subgraphs+=max(0,len(all_scopes)-1)
    for graph in all_scopes:
     nodes+=len(graph.get('nodes',[]));shader_nodes=[node for node in graph.get('nodes',[]) if node.get('type')=='GLSLShader'];glsl_count+=len(shader_nodes);glsl_members.update([name]*len(shader_nodes));glsl_modes.update(node.get('widgets_values',[None,None])[1] for node in shader_nodes)
     for node in graph.get('nodes',[]):
      node_type=node.get('type')
      if node_type not in wanted:continue
      counts[node_type]+=1;widgets[node_type]=node.get('widgets_values',[]);members[node_type]=name
      for link in graph.get('links',[]):
       if isinstance(link,dict) and (link.get('origin_id')==node.get('id') or link.get('target_id')==node.get('id')):links.append((node_type,link.get('type')))
  self.assertEqual(Counter({'FrameInterpolationModelLoader':1,'FrameInterpolate':1,'OpticalFlowLoader':1}),counts)
  self.assertEqual((512,496,272,8120,10),(files,roots,subgraphs,nodes,glsl_count));self.assertEqual(Counter({'from_input':10}),glsl_modes);self.assertEqual(1,len(glsl_members));self.assertTrue(next(iter(glsl_members)).endswith('basic_image_color_adjustment.json'))
  self.assertEqual(['film_net_fp16.safetensors'],widgets['FrameInterpolationModelLoader']);self.assertEqual([2],widgets['FrameInterpolate']);self.assertEqual(['raft_large_C_T_SKHT_V2-ff5fadd5.safetensors'],widgets['OpticalFlowLoader'])
  self.assertTrue(members['FrameInterpolate'].endswith('utility_video_frame_interpolation.json'));self.assertTrue(members['OpticalFlowLoader'].endswith('utility_void_video_inpainting.json'))
  self.assertIn(('FrameInterpolationModelLoader','INTERP_MODEL'),links);self.assertIn(('FrameInterpolate','IMAGE'),links);self.assertIn(('OpticalFlowLoader','OPTICAL_FLOW'),links)
if __name__=='__main__':unittest.main()
