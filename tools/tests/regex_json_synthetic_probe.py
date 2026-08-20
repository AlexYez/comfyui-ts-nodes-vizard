from __future__ import annotations
import ast,json,re
from pathlib import Path
class NodeOutput:
 def __init__(self,*values):self.values=values
class IO:
 class ComfyNode:pass
 NodeOutput=NodeOutput
def run(root:Path):
 p=root/'.comfyui-source-0.32.0/comfy_extras/nodes_string.py';assert p.is_file();tree=ast.parse(p.read_text(encoding='utf8'));names={'RegexMatch','RegexExtract','RegexReplace','JsonExtractString'};body=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name in names];scope={'io':IO,'re':re,'json':json};exec(compile(ast.Module(body=body,type_ignores=[]),str(p),'exec'),scope);m,e,r,j=(scope[x] for x in ['RegexMatch','RegexExtract','RegexReplace','JsonExtractString'])
 assert m.execute('ok\nERROR: x','^error:',True,True,False).values==(True,);assert m.execute('x','(',True,False,False).values==(False,)
 s='a=1 b=22'; assert e.execute(s,r'(\w)=(\d+)','First Match',False,False,False,1).values==('a=1',);assert e.execute(s,r'(\w)=(\d+)','All Matches',False,False,False,1).values==('a\nb',);assert e.execute(s,r'(\w)=(\d+)','First Group',False,False,False,2).values==('1',);assert e.execute(s,r'(\w)=(\d+)','All Groups',False,False,False,2).values==('1\n22',);assert e.execute(s,r'(\w)=(\d+)','First Group',False,False,False,0).values==('a=1',)
 assert r.execute('A1 B22',r'\d+','#',False,False,False,1).values==('A# B22',);assert r.execute('a=1',r'(\w)=(\d)',r'\2:\1',False,False,False,0).values==('1:a',)
 raised=False
 try:r.execute('x','(','',False,False,False,0)
 except re.error:raised=True
 assert raised
 assert j.execute('{"s":"x","n":2,"b":true,"z":null,"a":[1]}','s').values==('x',);assert j.execute('{"b":true}','b').values==('True',);assert j.execute('{"a":[1]}','a').values==('[1]',);assert j.execute('{"z":null}','z').values==('',);assert j.execute('[]','x').values==('',);assert j.execute('{','x').values==('',)
 return {'match':True,'all_matches':'a\nb','replace_error':raised,'json_bool':'True'}
if __name__=='__main__':print(json.dumps(run(Path(__file__).resolve().parents[2]),sort_keys=True))
