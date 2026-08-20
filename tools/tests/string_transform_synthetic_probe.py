from __future__ import annotations
import ast,json
from pathlib import Path
class NodeOutput:
 def __init__(self,*values): self.values=values
class IO:
 class ComfyNode: pass
 NodeOutput=NodeOutput
def run(root:Path):
 p=root/'.comfyui-source-0.32.0/comfy_extras/nodes_string.py'; assert p.is_file(); tree=ast.parse(p.read_text(encoding='utf8')); names={'CaseConverter','StringTrim','StringReplace','StringConcatenate'}; body=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name in names]; scope={'io':IO}; exec(compile(ast.Module(body=body,type_ignores=[]),str(p),'exec'),scope)
 case,trim,replace,concat=(scope[x] for x in ['CaseConverter','StringTrim','StringReplace','StringConcatenate'])
 assert case.execute('straße','UPPERCASE').values==('STRASSE',); assert case.execute('ПРИВЕТ мир','Capitalize').values==('Привет мир',); assert case.execute('the old MAN','Title Case').values==('The Old Man',)
 assert trim.execute('\u00a0\u2003 x  y \n','Both').values==('x  y',); assert trim.execute('  x  ','Left').values==('x  ',); assert trim.execute('  x  ','Right').values==('  x',)
 assert replace.execute('aaa','aa','X').values==('Xa',); assert replace.execute('ab','','-').values==('-a-b-',); assert replace.execute('a.b','.','!').values==('a!b',)
 assert concat.execute('a','b',', ').values==('a, b',); assert concat.execute('','',';').values==(';',); assert concat.execute('','b','/').values==('/b',)
 return {'case':'STRASSE','trim':'x  y','replace':['Xa','-a-b-'],'concat':['a, b',';']}
if __name__=='__main__': print(json.dumps(run(Path(__file__).resolve().parents[2]),ensure_ascii=False,sort_keys=True))
