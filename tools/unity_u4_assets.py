"""Freeze/verify the explicit Unity art inputs; reviews are separate artifacts."""
from pathlib import Path
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'art/unity/startroom-u4'
def identity(path):
    raw=path.read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def files():
    materials=json.loads((ART/'materials.json').read_bytes())['materials']
    return sorted(['player-rig.fbx','room.fbx','cirrus.fbx','startroom-rig.blend','rig.json','materials.json']+[m['albedo'] for m in materials if 'albedo' in m])
def verify():
    lock=json.loads((ART/'asset-lock.json').read_bytes())
    if set(lock['files'])!=set(files()):raise ValueError('Unapproved art input list')
    for name,row in lock['files'].items():
        p=(ART/name).resolve()
        if not p.is_relative_to(ART.resolve()) or p.is_symlink() or identity(p)!=row:raise ValueError('Changed art: '+name)
    if identity(ROOT/'unity-remake/SourceContracts/source-baseline.json')['sha256']!=lock['source_baseline_sha256']:raise ValueError('Changed source baseline')
    return lock
def freeze():
    if (ART/'accepted.json').exists():raise ValueError('Accepted art is immutable; create a new art version')
    lock={'schema':'ao_unity_u4_art_v1','approval':'../startroom-v2/review-lock.json','source_baseline_sha256':identity(ROOT/'unity-remake/SourceContracts/source-baseline.json')['sha256'],'performance_tested':False,'files':{name:identity(ART/name) for name in files()}}
    (ART/'asset-lock.json').write_text(json.dumps(lock,indent=2)+'\n',encoding='utf-8')
    return verify()
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','verify']);args=parser.parse_args()
    print(json.dumps({'passed':True,'files':len((freeze() if args.action=='freeze' else verify())['files']),'performance_tested':False}))
