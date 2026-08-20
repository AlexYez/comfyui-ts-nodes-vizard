from __future__ import annotations
import hashlib,re,unittest
from tools import catalog
SPECS={'core.wan-image-to-video':('wan-image-to-video','WanImageToVideo','sha256:185a9c575745982b108a6dc3cadadf637bb14e695501446fa049eeb0dce46c83'),'core.wan-first-last-frame-to-video':('wan-first-last-frame-to-video','WanFirstLastFrameToVideo','sha256:77a867d2728434887b18dcc59a5c97e541a934b243f36aa44f8666b13e7f7620'),'core.wan-fun-control-to-video':('wan-fun-control-to-video','WanFunControlToVideo','sha256:b5770d45598c45a1bc81ce09ba2e21117e90bee17620af5e4733ee6eb68ffc2d'),'core.wan-fun-inpaint-to-video':('wan-fun-inpaint-to-video','WanFunInpaintToVideo','sha256:e4c3f9c653e93ed084252cac2c94273820fbaeac27bc4b19026421b1afeefab3')}
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  a_s=catalog.load_json(catalog.CONTENT/'schemas/article.schema.v1.json');r_s=catalog.load_json(catalog.CONTENT/'schemas/article-research.schema.v1.json');rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,a_s));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,r_s));self.assertFalse(q['checks']['exampleExecuted'])
  self.assertEqual([],e)
 def test_source(self):
  p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_wan.py';self.assertEqual('39ff111cc45c8d2a75cab1aa3b97ad9bf9037868178af2468bc52b34dbd0d96d',hashlib.sha256(p.read_bytes()).hexdigest());s=p.read_text('utf8');self.assertIn('torch.ones((length, height, width, start_image.shape[-1])',s);self.assertIn('concat_latent = concat_latent.repeat(1, 2',s);self.assertIn('mask[:, :, :start_image.shape[0] + 3] = 0.0',s);self.assertIn('flfv = WanFirstLastFrameToVideo()',s)
if __name__=='__main__':unittest.main()
