"""Bind a fully sampled render observer to an identical three-run source route."""
import argparse
import hashlib
import json
from pathlib import Path
from verify_character_capture import inspect
from verify_event_capture_links import compare_outputs


def verify(formal_root, route, render):
    replay_raw=(formal_root/f'{route}-replay.json').read_bytes()
    replay=json.loads(replay_raw)
    if replay.get('passed') is not True or replay.get('replays')!=3 or replay.get('differing_outputs'):
        raise ValueError('Unpassed three-run route')
    baseline=formal_root/f'{route}-a'
    raw=(baseline/'manifest.json').read_bytes()
    matched=[r for r in replay['captures'] if Path(r['folder']).resolve()==baseline.resolve()]
    if len(matched)!=1 or hashlib.sha256(raw).hexdigest()!=matched[0]['manifest_sha256']:
        raise ValueError('Changed formal baseline')
    manifest=json.loads(raw.decode('utf-8-sig'))
    evidence=inspect(render)
    observed=json.loads((render/'manifest.json').read_text(encoding='utf-8-sig'))
    if manifest['inputs']!=observed['inputs'] or manifest['build']!=observed['build']:
        raise ValueError('Source inputs or capture backend differ')
    expected={r['path']:r['sha256'] for r in manifest['outputs']}
    names=compare_outputs(expected,evidence['outputs'])
    if evidence['capture']['frames']!=replay['frames_per_replay']:
        raise ValueError('Source route length changed')
    return {'schema':'ao_pc_interaction_capture_link_v1','passed':True,
            'formal_manifest_sha256':matched[0]['manifest_sha256'],'render_manifest_sha256':evidence['manifest_sha256'],
            'replay_sha256':hashlib.sha256(replay_raw).hexdigest(),'frames':evidence['capture']['frames'],
            'shared_sample_files':len(names),'scope':'Complete render capture integrity plus unchanged shared formal samples.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('formal_root',type=Path);p.add_argument('route');p.add_argument('render',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=verify(a.formal_root,a.route,a.render);a.out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
