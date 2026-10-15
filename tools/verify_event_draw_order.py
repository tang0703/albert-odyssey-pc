"""Diagnostic per-frame world draw ordering; capture integrity is a separate gate."""
import argparse
import json
from pathlib import Path
from event_draw_order import scene
from character_draw_order import compare_commands
from character_graphics import sha


def validate(folder,frames):
    manifest_raw=(folder/'manifest.json').read_bytes();manifest=json.loads(manifest_raw.decode('utf-8-sig'))
    records={r['path']:r for r in manifest['outputs']}
    def read(name):
        raw=(folder/name).read_bytes()
        if len(raw)!=records[name]['bytes'] or sha(raw)!=records[name]['sha256']:raise ValueError('Changed capture: '+name)
        return raw
    events={n:[] for n in frames};digest=__import__('hashlib').sha256()
    with (folder/'vdp-events.jsonl').open('rb') as stream:
        for line in stream:
            digest.update(line);row=json.loads(line)
            if row['frame'] in events and row['kind']=='command_execute_before':events[row['frame']].append(row)
    if digest.hexdigest()!=records['vdp-events.jsonl']['sha256']:raise ValueError('Changed execution trace')
    results=[];errors=[]
    for frame,commands in events.items():
        prefix=f'frame-{frame-2:06d}/'
        try:
            current=scene(read(prefix+'wram-high.bin'),read(prefix+'wram-low.bin'))
            order=compare_commands(current,commands)
            results.append({'frame':frame,'source_snapshot':frame-2,**order})
        except ValueError as exc:
            from character_draw_order import _matches
            unmatched=[{'address':e['command_address'],'raw':e['command_hex']} for e in commands
                       if not any(_matches(p,bytes.fromhex(e['command_hex'])) for p in current['ordered_pieces'])]
            errors.append({'frame':frame,'reason':str(exc),'unmatched':unmatched,
                           'predicted_effect':[p for p in current['ordered_pieces'] if p['id'].startswith('actor_1:')]})
    return {'schema':'ao_pc_event_draw_order_diagnostic_v1','passed':not errors,
        'capture_integrity_required':True,'capture_manifest_sha256':sha(manifest_raw),
        'source_render_delay_assumption':'Two video-frame difference under test, not a confirmed event-wide contract.',
        'frames':results,'errors':errors}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--frames',type=int,nargs='+',required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=validate(a.capture,a.frames);a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':r['passed'],'checked':len(r['frames']),'errors':r['errors']}))
    raise SystemExit(0 if r['passed'] else 1)
