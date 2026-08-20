from __future__ import annotations
import hashlib,json,re,unittest,zipfile
from collections import Counter
from tools import catalog
SPECS={'core.text-overlay':('text-overlay','TextOverlay','sha256:0927c849101688ba5c171f2d9ce064660ab5eab0f1013893a67ee155dba2127f'),'core.webcam-capture':('webcam-capture','WebcamCapture','sha256:1ff51ff042074b56afd39bbafc028d58726c795f9a2d43f66be714f46f17a55e'),'core.generate-tracks':('generate-tracks','GenerateTracks','sha256:1c56bb99f1b42bfeed9b5eddfa549ddc7a8561e7276f15e30c744080aaf32d8d'),'core.uso-style-reference':('uso-style-reference','USOStyleReference','sha256:3809d82be5c234425702caec868cace9f8694ff3689e45a7592065c5b9c8c806')}
HASHES={'nodes_text_overlay.py':'9f247d9bf0e09bc7d7a6c9cb476f65b59d72cc56bf8a86cfb083a5383a621b0e','nodes_webcam.py':'51eb4c62e4cc2e301379c0d0817dc3b01e8d8e6210e0605e14172d7f42eed6a2','nodes_wanmove.py':'5dddfc51ff7d70bbe4da55b52fd66469fac5396f188b73b72100032f3b13d871','nodes_model_patch.py':'f8fd8b9281e8926536c71867ccf1529a41fe690ba2ed12db8f58251ba32cbc76'}
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  a_s=catalog.load_json(catalog.CONTENT/'schemas/article.schema.v1.json');r_s=catalog.load_json(catalog.CONTENT/'schemas/article-research.schema.v1.json');rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,a_s));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,r_s));self.assertFalse(q['checks']['exampleExecuted'])
  self.assertEqual([],e)
 def test_sources(self):
  base=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras'
  for n,h in HASHES.items():self.assertEqual(h,hashlib.sha256((base/n).read_bytes()).hexdigest())
  t=(base/'nodes_text_overlay.py').read_text('utf8');self.assertIn('images * (1.0 - overlay_alpha) + overlay_rgb * overlay_alpha',t);self.assertIn('ImageFont.load_default(size=size)',t)
  w=(base/'nodes_webcam.py').read_text('utf8');self.assertIn('get_annotated_filepath(image)',w);self.assertIn('super().IS_CHANGED(image)',w)
  frontend=catalog.ROOT/'.frontend-source-1.48.7/src/extensions/core/webcamCapture.ts';self.assertEqual('b20605703703aeef36b7a628c36ed486056de8de2e6355235a44ea8e7441f126',hashlib.sha256(frontend.read_bytes()).hexdigest());f=frontend.read_text('utf8');self.assertIn('navigator.mediaDevices.getUserMedia',f);self.assertIn("canvas.toDataURL('image/png')",f);self.assertIn("body.append('subfolder', 'webcam')",f);self.assertIn("body.append('type', 'temp')",f);self.assertIn('No webcam image captured',f);self.assertIn('secure context is required',f)
  m=(base/'nodes_wanmove.py').read_text('utf8');self.assertIn('t * t * (3 - 2 * t)',m);self.assertIn('(track_mask > 0).any(dim=(1, 2)).unsqueeze(-1)',m)
  u=(base/'nodes_model_patch.py').read_text('utf8');self.assertIn('all_hidden_states[:, -20]',u);self.assertIn('all_hidden_states[:, -11]',u)
 def test_webcam_absent_and_generated_tracks_official_presets(self):
  files=roots=subgraphs=nodes=0;hits=Counter();track_widgets=[];track_routes=Counter();overlay_hits=0
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
     graph_nodes=graph.get('nodes',[]);nodes+=len(graph_nodes);hits.update(node.get('type') for node in graph_nodes if node.get('type') in {'WebcamCapture','GenerateTracks'});overlay_hits+=sum(node.get('type')=='TextOverlay' for node in graph_nodes);by_id={node.get('id'):node for node in graph_nodes}
     for node in graph_nodes:
      if node.get('type')=='GenerateTracks':track_widgets.append(tuple(node.get('widgets_values',[])))
     for link in graph.get('links',[]):
      if isinstance(link,list) and len(link)>=6 and by_id.get(link[1],{}).get('type')=='GenerateTracks':track_routes[by_id.get(link[3],{}).get('type')]+=1
  self.assertEqual((512,496,272,8120),(files,roots,subgraphs,nodes));self.assertEqual(Counter({'GenerateTracks':3}),hits);self.assertEqual(0,overlay_hits);self.assertEqual(3,len(track_widgets));self.assertTrue(all(x[:2]==(720,480) and x[6]==81 and x[9] is True and x[12]=='linear' for x in track_widgets));self.assertEqual(Counter({5:2,7:1}),Counter(x[7] for x in track_widgets));self.assertEqual(Counter({0.007:1,0.012:1,0.017:1}),Counter(x[8] for x in track_widgets));self.assertEqual(Counter({'WanMoveConcatTrack':3}),track_routes)
 def test_uso_official_topology(self):
  count=0;routes=Counter()
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
    for graph in scopes(json.loads(archive.read(name))):
     by_id={node.get('id'):node for node in graph.get('nodes',[])}
     count+=sum(node.get('type')=='USOStyleReference' for node in by_id.values())
     for link in graph.get('links',[]):
      if not isinstance(link,dict):continue
      source=by_id.get(link.get('origin_id'));target=by_id.get(link.get('target_id'))
      if source and target and target.get('type')=='USOStyleReference':routes[(source.get('type'),link.get('type'),link.get('target_slot'))]+=1
  self.assertEqual(4,count);self.assertEqual(4,routes[('CLIPVisionEncode','CLIP_VISION_OUTPUT',2)])
if __name__=='__main__':unittest.main()
