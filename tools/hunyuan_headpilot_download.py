"""Download pinned official weights locally; never upload reference images."""
from pathlib import Path
import hashlib, json, urllib.request

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT.parent/'tools/pc-remake'
metadata=json.loads((TOOLS/'downloads/hunyuan-2mv-model-metadata.json').read_bytes())
revision=metadata['sha']
target=TOOLS/'hunyuan-models/tencent/Hunyuan3D-2mv'
target.mkdir(parents=True,exist_ok=True)
names=['LICENSE','hunyuan3d-dit-v2-mv/config.yaml','hunyuan3d-dit-v2-mv/model.fp16.safetensors']
records={}
for name in names:
    entry=next(x for x in metadata['siblings'] if x['rfilename']==name)
    expected=entry.get('lfs',{}).get('sha256')
    destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists():
        url=f'https://huggingface.co/tencent/Hunyuan3D-2mv/resolve/{revision}/{name}?download=true'
        temporary=destination.with_suffix(destination.suffix+'.partial')
        request=urllib.request.Request(url,headers={'User-Agent':'MAP001-local-art-study/1.0'})
        print('Downloading',name,entry['size'],flush=True)
        count=0;next_notice=256*1024*1024
        with urllib.request.urlopen(request,timeout=120) as response,temporary.open('wb') as stream:
            while block:=response.read(8*1024*1024):
                stream.write(block);count+=len(block)
                if count>=next_notice:
                    print(name,count,'bytes',flush=True);next_notice+=256*1024*1024
        assert count==entry['size'],(name,count,entry['size'])
        temporary.replace(destination)
    h=hashlib.sha256()
    with destination.open('rb') as stream:
        while block:=stream.read(8*1024*1024):h.update(block)
    assert destination.stat().st_size==entry['size']
    if expected:assert h.hexdigest()==expected,name
    records[name]={'bytes':destination.stat().st_size,'sha256':h.hexdigest(),'upstream_lfs_sha256':expected}
    print('Verified',name,h.hexdigest(),flush=True)
(target/'download-lock.json').write_text(json.dumps({'repository':'tencent/Hunyuan3D-2mv','revision':revision,'files':records},indent=2)+'\n',encoding='utf-8')
