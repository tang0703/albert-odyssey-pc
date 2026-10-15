"""Bind detailed render observers to the three identical formal source replays."""
import argparse
import hashlib
import json
from pathlib import Path
from verify_character_capture import inspect

ROUTES=('center','top','bottom','reenter','wait','hold')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_outputs(observed,baseline):
    names=[name for name in observed if name.startswith('frame-') and name.endswith(('.bin','.savestate'))]
    if not names or not any(name.endswith('/video-rgba.bin') for name in names):
        raise ValueError('Missing synchronized source samples')
    for name in names:
        if name not in baseline or observed[name]!=baseline[name]:
            raise ValueError('Render observer changed original sample: '+name)
    return names


def verify(root,route):
    replay_path=root/'d1-v1'/f'{route}-replay.json'
    replay_bytes=replay_path.read_bytes();replay=json.loads(replay_bytes)
    if replay.get('schema')!='ao_pc_character_capture_replay_v2' or replay.get('passed') is not True or replay.get('replays')!=3 or replay.get('differing_outputs'):
        raise ValueError('Formal three-run gate is incomplete')
    baseline=root/'d1-v1'/f'{route}-a'
    match=[r for r in replay['captures'] if Path(r['folder']).resolve()==baseline.resolve()]
    if len(match)!=1 or digest(baseline/'manifest.json')!=match[0]['manifest_sha256']:
        raise ValueError('Replay baseline manifest changed')
    baseline_manifest=json.loads((baseline/'manifest.json').read_text(encoding='utf-8-sig'))
    folder=root/'d1-render'/f'{route}-a'
    evidence=inspect(folder)
    render_manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
    if render_manifest['inputs']!=baseline_manifest['inputs'] or render_manifest['build']!=baseline_manifest['build']:
        raise ValueError('Observer sources or backend differ')
    baseline_outputs={r['path']:r['sha256'] for r in baseline_manifest['outputs']}
    names=compare_outputs(evidence['outputs'],baseline_outputs)
    if evidence['capture']['frames']!=replay['frames_per_replay']:
        raise ValueError('Observer route length differs')
    return {'schema':'ao_pc_event_capture_link_v1','passed':True,'route':route,
        'render_manifest_sha256':evidence['manifest_sha256'],'formal_manifest_sha256':match[0]['manifest_sha256'],
        'replay_report_sha256':hashlib.sha256(replay_bytes).hexdigest(),'frames':evidence['capture']['frames'],
        'compared_sample_files':len(names),'sample_frames':sorted({int(n[6:12]) for n in names}),
        'scope':'Full render-capture integrity and synchronized CPU/VDP validation, then exact shared sample identity with the three-run formal baseline.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('reports/event'));p.add_argument('--routes',nargs='+',choices=ROUTES,default=ROUTES)
    a=p.parse_args()
    for route in a.routes:
        print('Checking render capture '+route,flush=True)
        result=verify(a.root,route)
        (a.root/f'd1-{route}-capture-link.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result),flush=True)
