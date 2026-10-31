"""Source landing acceptance: replay, rendering, boundaries and Godot parity."""
import base64
import collections
import json
from pathlib import Path
from transition_source import ROOT,sha
from verify_transition_capture import verify_files
from inspect_event_capture import watched
from equipment_contract import encoded


def build():
    base=ROOT/'reports/transition'
    proofs={n:json.loads((base/(n+'.json')).read_bytes()) for n in ('t3-reference','t3-godot','t3-world')}
    if not all(r['passed'] for r in proofs.values()) or not proofs['t3-world']['pixels']['passed']:raise ValueError('T3 evidence incomplete')
    _,render_files,render_hash=verify_files(base/'t3-render')
    _,sparse_files,_=verify_files(base/'t3-corridor-1')
    # Instrumentation adds event counters, but observer payloads must agree.
    compared=0
    for name,digest in sparse_files.items():
        if name.endswith(('/wram-high.bin','/wram-low.bin','/vram1.bin','/vram2.bin','/cram.bin','/video-rgba.bin','/vdp1-fb0.bin','/vdp1-fb1.bin')):
            if render_files.get(name)!=digest:raise ValueError('Render observer changed source payload: '+name)
            compared+=1
    parent=base/'t1-equip-stairs-1';_,parent_files,parent_hash=verify_files(parent)
    seed_sha=parent_files['frame-001254/state.savestate'];boundaries=[]
    for route in ('return','story'):
        previous=None
        for repeat in (1,2,3):
            folder=base/f't3-{route}-boundary-{repeat}'
            manifest,files,digest=verify_files(folder)
            if not any(r['sha256']==seed_sha and r['path'].endswith('.savestate') for r in manifest['inputs']):raise ValueError('Boundary seed chain changed')
            if previous is None:previous=files
            elif previous!=files:raise ValueError('Boundary repeat differs')
            events=[json.loads(l) for l in (folder/'hooks.jsonl').open()]
            if route=='return':
                targets=[r for r in events if r['pc']==0x060ac458]
                expected_frame=11;expected_xy='38807680'
            else:
                targets=[r for r in events if r['pc']==0x0609e092]
                expected_frame=27;expected_xy='37007900'
                if not targets or int.from_bytes(watched(targets[0],0x060c66bc,4),'big')-0x260e0000+7!=0x2c17:raise ValueError('Unexpected boundary event entry')
            if not targets or targets[0]['frame']!=expected_frame or watched(targets[0],0x060c8758,4).hex()!=expected_xy:raise ValueError('Boundary dynamic evidence differs')
            boundaries.append({'route':route,'repeat':repeat,'manifest_sha256':digest,'first_trigger_frame':expected_frame,'player_xy_raw_hex':expected_xy})
    pixels=proofs['t3-world']['pixels']
    stable=[r for r in pixels['frames'] if r['rgb_offset']==[0,0,0]]
    if not stable or {r['display_delay_frames'] for r in stable}!={2}:raise ValueError('Unverified stable landing delay')
    report={'schema':'ao_pc_transition_t3_acceptance_v1','passed':True,'performance_tested':False,'functional_release':False,
            'proofs':{n:sha((base/(n+'.json')).read_bytes()) for n in proofs},'render_manifest_sha256':render_hash,
            'observer_payload_comparisons':compared,'movement_query_count':proofs['t3-reference']['approved_query_count'],
            'godot_checks':proofs['t3-godot']['checks'],'source_pixel_frames':len(pixels['frames']),
            'source_world_pixels':pixels['compared_world_pixels'],'unexplained_pixels':0,'excluded_source_ui_pixels':0,
            'boundaries':boundaries,'boundary_seed':{'sha256':seed_sha,'parent_manifest_sha256':parent_hash},
            'presentation':{'stable_delay_updates':2,'first_visible_source_frame':pixels['frames'][0]['frame'],
                'first_visible_sprites':False,'source_initial_vdp1_cleared':True,'rgb_offset':'Previous completed video register sample; independent of body/camera delay'},
            'limits':['Only source-tested query union in connected right corridor. Left story event and return stairs are boundaries.',
                      'Source player shadow omitted. No destination name or complete-room claim.',
                      'Failed landing-coverage route remains evidence; its query union is not approved.']}
    (base/'t3-acceptance.json').write_bytes(encoded(report))
    (ROOT/'data/transition/landing-lock.json').write_bytes(encoded({'schema':'ao_pc_transition_landing_lock_v1','report_sha256':sha(encoded(report)),
        'core_sha256':proofs['t3-reference']['core_sha256'],'visuals_sha256':sha((ROOT/'generated/transition/visuals.json').read_bytes()),'performance_tested':False}))
    draw_coverage(proofs['t3-reference'])
    print(json.dumps({k:report[k] for k in ('passed','movement_query_count','godot_checks','source_pixel_frames','source_world_pixels','performance_tested')}))


def draw_coverage(proof):
    root=ROOT/'generated/transition'
    data=json.loads((root/'core.json').read_bytes())
    image=base64.b64encode((root/'background.png').read_bytes()).decode()
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="980" viewBox="0 0 320 245">',
         '<rect width="320" height="245" fill="#14232e"/>','<svg width="320" height="224" viewBox="0 0 320 224">',
         f'<image x="-128" y="-24" width="448" height="256" href="data:image/png;base64,{image}" style="image-rendering:pixelated"/>']
    for index in data['landing_query_indices']:
        x=(index%256)*8-640;y=(index//256)*8-1816
        svg.append(f'<rect x="{x}" y="{y}" width="8" height="8" fill="#31dae8" fill-opacity="0.17" stroke="#31dae8" stroke-width="0.3"/>')
    for contact in data['contacts']:
        x,y,r,b=contact['bounds_raw'];svg.append(f'<rect x="{x/16-640}" y="{y/16-1816}" width="{(r-x)/16}" height="{(b-y)/16}" fill="#ff8050" fill-opacity="0.32" stroke="#ff8050" stroke-width="0.5"/>')
    rows=json.loads((ROOT/'reports/transition/t3-corridor-1-reference.json').read_bytes())['predictions']
    points=[]
    for row in rows:
        if row['stage']!='landing':continue
        raw=bytes.fromhex(row['player']);points.append(f"{int.from_bytes(raw[:2],'big')/16-640},{int.from_bytes(raw[2:4],'big')/16-1816}")
    svg.append('<polyline points="'+' '.join(points)+'" fill="none" stroke="#c2ff82" stroke-width="0.6"/>')
    svg.extend(['<circle cx="264" cy="96" r="2" fill="white"/></svg>',
        '<text x="5" y="231" fill="white" font-family="sans-serif" font-size="4">Scene 7 | first control viewport | 95 source-tested lookup cells</text>',
        '<text x="5" y="238" fill="white" font-family="sans-serif" font-size="4">Cyan: lookup cells (not walkable tiles). Green: replay. Orange: test boundary.</text></svg>'])
    (ROOT/'reports/transition/landing-coverage.svg').write_text('\n'.join(svg),encoding='utf-8')


if __name__=='__main__':build()
