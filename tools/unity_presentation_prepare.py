"""Prepare only sealed source audio; no images, replay states or original disc."""
from pathlib import Path
from unity_source_baseline import ROOT,SOURCE,verify,identity
import json

def main():
    verify()
    baseline=json.loads((ROOT/'unity-remake/SourceContracts/source-baseline.json').read_bytes())
    dest=ROOT/'unity-remake/Assets/StreamingAssets/PresentationLocal'
    dest.mkdir(parents=True,exist_ok=True)
    files={'event.wav':'event/cirrus-event.wav','pickup.wav':'interaction/cirrus-pickup.wav'}
    rows=[]
    for target,source in files.items():
        item=identity(SOURCE/source)
        if item!=baseline['files'][source]: raise ValueError('Audio identity changed')
        (dest/target).write_bytes((SOURCE/source).read_bytes())
        rows.append(f'    new SourceIdentity("{target}",{item["bytes"]},"{item["sha256"]}")')
    extra=[p for p in dest.rglob('*') if p.is_file() and p.suffix!='.meta' and p.name not in files]
    if extra: raise ValueError('Unapproved presentation files: '+str(extra))
    code='namespace Ao.SourceContracts { public static class PresentationPins { public static readonly SourceIdentity[] Files = {\n'+',\n'.join(rows)+'\n}; } }\n'
    (ROOT/'unity-remake/Assets/Scripts/Core/PresentationPins.cs').write_text(code,encoding='utf-8',newline='\n')

if __name__=='__main__':main()
