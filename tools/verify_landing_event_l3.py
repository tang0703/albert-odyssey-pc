"""Seal complete source world/pixel evidence and independently measured update lag."""
import bisect
import json
from pathlib import Path
from landing_event_source import ROOT, sha
from equipment_contract import encoded
from verify_transition_capture import verify_files


def build():
    base = ROOT/'reports/landing-event'
    folder = base/'l1-render-complete'
    raw = (base/'landing-world-diagnostic.json').read_bytes()
    world = json.loads(raw)
    if not world['passed'] or not world['pixels']['passed'] or world['errors']:
        raise ValueError('Source world or pixel comparison failed')
    _, files, digest = verify_files(folder)
    if digest != world['capture_manifest_sha256']:
        raise ValueError('Rendering evidence changed')
    sparse = json.loads((base/'l1-equip-1/manifest.json').read_text(encoding='utf-8-sig'))
    compared = 0
    for row in sparse['outputs']:
        name = row['path']
        if name.endswith(('/wram-high.bin','/wram-low.bin','/vram1.bin','/vram2.bin','/cram.bin','/video-rgba.bin','/vdp1-fb0.bin','/vdp1-fb1.bin')):
            if files.get(name) != row['sha256']: raise ValueError('Render observer changed source: '+name)
            compared += 1
    indices = []; active = False
    for line in (folder/'hooks.jsonl').open(encoding='utf-8'):
        row = json.loads(line)
        if row['pc'] == 0x060ac458: active = True
        if active and row['pc'] == 0x060915b2: indices.append(row['event_index'])
    ends = {r['frame']:r['event_index'] for r in map(json.loads,(folder/'frames.jsonl').open(encoding='utf-8'))}
    frames = world['pixels']['frames']
    delays = [bisect.bisect_right(indices,ends[r['frame']])-r['model_update'] for r in frames]
    if not frames or set(delays) != {2}: raise ValueError('Unverified logical presentation delay')
    presentation = {'logical_update_delay':2,'verified_frames':len(frames),
        'basis':'Completed actor/camera/object updates versus consumed source VDP submission and scanout; measured for this event.',
        'initial_submission_empty':True,'fade':'Current source fade tick, separate from world queue'}
    visuals_path = ROOT/'generated/landing-event/visuals.json'
    visuals = json.loads(visuals_path.read_bytes()); visuals['presentation'] = presentation
    visuals_path.write_bytes(encoded(visuals))
    result = {'schema':'ao_pc_landing_event_l3_acceptance_v1','passed':True,'performance_tested':False,
        'world_report_sha256':sha(raw),'render_manifest_sha256':digest,'observer_payload_comparisons':compared,
        'source_draw_frames':len(world['frames']),'source_pixel_frames':len(frames),
        'compared_pixels':world['pixels']['compared_world_pixels'],'unexplained_pixels':0,
        'presentation':presentation,'visuals_sha256':sha(visuals_path.read_bytes()),
        'limits':['Exact source dialogue window and source shadows excluded from pixel equality.',
                  'HD dialogue and Godot renderer require separate functional checks.',
                  'NPC forced path does not grant free-player movement permission.']}
    (base/'l3-acceptance.json').write_bytes(encoded(result))
    (ROOT/'data/landing-event/visual-lock.json').write_bytes(encoded({'schema':'ao_pc_landing_event_visual_lock_v1',
        'report_sha256':sha(encoded(result)),'visuals_sha256':result['visuals_sha256'],'performance_tested':False}))
    print(json.dumps(result))


if __name__ == '__main__': build()
