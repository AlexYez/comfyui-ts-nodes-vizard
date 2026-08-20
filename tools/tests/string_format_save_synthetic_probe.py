from __future__ import annotations
import ast,json,os,tempfile
from pathlib import Path
class NodeOutput:
 def __init__(self,*values,ui=None):self.values=values;self.ui=ui
class IO:
 class ComfyNode:pass
 class FolderType:output='output'
 NodeOutput=NodeOutput
class UI:
 @staticmethod
 def SavedResult(file,subfolder,kind):return {'file':file,'subfolder':subfolder,'kind':kind}
class FolderPaths:
 def __init__(self,root):self.root=root
 def get_output_directory(self):return str(self.root)
 def get_save_image_path(self,prefix,output,*args):
  parts=prefix.replace('\\','/').split('/');sub='/'.join(parts[:-1]);folder=self.root/sub;folder.mkdir(parents=True,exist_ok=True);return str(folder),parts[-1],1,sub,prefix
def run(root:Path):
 sp=root/'.comfyui-source-0.32.0/comfy_extras/nodes_string.py';tree=ast.parse(sp.read_text(encoding='utf8'));names={'StringFormat','ConvertDictionaryToString','ConvertArrayToString'};body=[n for n in tree.body if (isinstance(n,ast.FunctionDef) and n.name=='_dump_json') or (isinstance(n,ast.ClassDef) and n.name in names)];scope={'io':IO,'json':json};exec(compile(ast.Module(body=body,type_ignores=[]),str(sp),'exec'),scope);fmt,dct,arr=(scope[x] for x in ['StringFormat','ConvertDictionaryToString','ConvertArrayToString']);assert fmt.execute({'a':1024,'b':768},'Size: {a}×{b}').values==('Size: 1024×768',);assert fmt.execute({'a':1.234},'{a:.2f}').values==('1.23',);assert fmt.execute({},'{{x}}').values==('{x}',)
 assert dct.execute({'текст':'да','items':[1,None]},2).values[0]=='{\n  "текст": "да",\n  "items": [\n    1,\n    null\n  ]\n}';assert arr.execute(['я',1],0).values==('["я", 1]',)
 tp=root/'.comfyui-source-0.32.0/comfy_extras/nodes_text.py';tt=ast.parse(tp.read_text(encoding='utf8'));cls=next(n for n in tt.body if isinstance(n,ast.ClassDef) and n.name=='SaveTextNode')
 with tempfile.TemporaryDirectory() as td:
  sc={'io':IO,'ui':UI,'folder_paths':FolderPaths(Path(td)),'json':json,'os':os};exec(compile(ast.Module(body=[cls],type_ignores=[]),str(tp),'exec'),sc);save=sc['SaveTextNode'];out=save.execute('{"текст":"да"}','Text/report','json');p=Path(td)/'Text/report_00001.json';assert p.is_file();assert p.read_text(encoding='utf8')=='{\n  "текст": "да"\n}';save.execute('{bad','Text/bad','json');assert (Path(td)/'Text/bad_00001.json').read_text(encoding='utf8')=='{bad';save.execute('a,b','Text/table','csv');assert (Path(td)/'Text/table_00001.csv').read_text(encoding='utf8')=='a,b';assert out.values==('{"текст":"да"}',)
 return {'format':'Size: 1024×768','compact':'["я", 1]','saved':True}
if __name__=='__main__':print(json.dumps(run(Path(__file__).resolve().parents[2]),ensure_ascii=True,sort_keys=True))
