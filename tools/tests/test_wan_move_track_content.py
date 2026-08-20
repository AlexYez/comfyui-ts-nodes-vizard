from __future__ import annotations
import hashlib,re,unittest
from tools import catalog
SPECS={'core.wan-move-concat-track':('wan-move-concat-track','WanMoveConcatTrack','sha256:855dff604137c5f5261d41c34b0b5e028b696eccdc6144c0f7d2b1c002fc813d'),'core.wan-move-track-to-video':('wan-move-track-to-video','WanMoveTrackToVideo','sha256:e95f333dd3dca3d4b779ae007e32f5d6e2f54e7132c2af0b04760157ca4206fb'),'core.wan-move-tracks-from-coords':('wan-move-tracks-from-coords','WanMoveTracksFromCoords','sha256:401af1b1fd9dac83a2cff2833fb44d0b199466fa670154bcf3de7123f40f935a'),'core.wan-move-visualize-tracks':('wan-move-visualize-tracks','WanMoveVisualizeTracks','sha256:4442fb109b9f413536929d36afd2e5e4b1be1356a4f5ad80247c59be457d9021')}
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  a_s=catalog.load_json(catalog.CONTENT/'schemas/article.schema.v1.json');r_s=catalog.load_json(catalog.CONTENT/'schemas/article-research.schema.v1.json');rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,a_s));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,r_s));self.assertFalse(q['checks']['exampleExecuted'])
  self.assertEqual([],e)
 def test_source(self):
  p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_wanmove.py';self.assertEqual('5dddfc51ff7d70bbe4da55b52fd66469fac5396f188b73b72100032f3b13d871',hashlib.sha256(p.read_bytes()).hexdigest());s=p.read_text('utf8');self.assertIn('torch.cat([tracks_1["track_path"], tracks_2["track_path"]], dim=1)',s);self.assertIn('len(tracks_data[0])',s);self.assertIn('repeat_count = track_path.shape[1] // images.shape[0]',s);self.assertIn('replace_feature(concat_latent_image, track_pos, strength)',s)
if __name__=='__main__':unittest.main()
