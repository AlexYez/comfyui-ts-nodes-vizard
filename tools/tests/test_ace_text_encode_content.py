from __future__ import annotations
import hashlib,re,unittest
from tools import catalog
SPECS={'core.text-encode-ace-step-audio':('text-encode-ace-step-audio','TextEncodeAceStepAudio','sha256:ee74b14edc9bc6f83b9ec5cd8c5c85ba3655f0b4e958dfa15cf3d0addb1397cd'),'core.text-encode-ace-step-audio-15':('text-encode-ace-step-audio-15','TextEncodeAceStepAudio1.5','sha256:40a31df29bacea90c80143b94b756192101fdd83425a81dbc7dbcb953b5d52d5')}
class BatchTests(unittest.TestCase):
 def test_contracts(self):
  a_s=catalog.load_json(catalog.CONTENT/'schemas/article.schema.v1.json');r_s=catalog.load_json(catalog.CONTENT/'schemas/article-research.schema.v1.json');rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));e=[]
  for aid,(slug,ct,fp) in SPECS.items():
   p=catalog.CONTENT/'articles/core'/slug/'manifest.json';a=catalog.load_json(p);self.assertEqual([],catalog.json_schema_errors(a,a_s));catalog.validate_article(p,a,e);self.assertEqual(10,len(re.findall(r'^## ',(p.parent/'ru.md').read_text('utf8'),re.M)));self.assertEqual(fp,catalog.schema_fingerprint(ct,rt[ct]));q=catalog.load_json(catalog.CONTENT/'research/reviews'/f'{aid}.json');self.assertEqual([],catalog.json_schema_errors(q,r_s));self.assertFalse(q['checks']['exampleExecuted'])
  self.assertEqual([],e)
 def test_source_and_ports(self):
  p=catalog.ROOT/'.comfyui-source-0.32.0/comfy_extras/nodes_ace.py';self.assertEqual('9f3142cb53801a25fd214388b4852c578ad71ac58d557884833175b0d02a7bfd',hashlib.sha256(p.read_bytes()).hexdigest());s=p.read_text('utf8');self.assertIn('conditioning_set_values(conditioning, {"lyrics_strength": lyrics_strength})',s);self.assertIn('timesignature=int(timesignature)',s);rt=catalog.object_info_nodes(catalog.load_json(catalog.CONTENT/'runtime/comfyui-0.32.0.object-info.json'));self.assertEqual(15,len(rt['TextEncodeAceStepAudio1.5']['input_order']['required']));self.assertEqual(2000.0,rt['TextEncodeAceStepAudio1.5']['input']['required']['top_p'][1]['max']);self.assertIn('ru',rt['TextEncodeAceStepAudio1.5']['input']['required']['language'][1]['options'])
if __name__=='__main__':unittest.main()
