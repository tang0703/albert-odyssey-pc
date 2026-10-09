"""Assemble R5 evidence, without converting pending soak results into success."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
from room_bundle import encoded,sha

ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'reports/room'

def assemble(qa: Path,soak: Path|None=None,environment_pre: Path|None=None,environment_post: Path|None=None) -> dict:
    qa=qa.resolve()
    if soak is not None:soak=soak.resolve()
    identities={}
    def read(path: Path):
        raw=path.read_bytes();identities[str(path.relative_to(ROOT))]=sha(raw)
        return json.loads(raw.decode('utf-8-sig'))
    r1=read(REPORTS/'r1-survey.json')
    if sha((REPORTS/'r1-survey.json').read_bytes())!='a6144d7ee9dda764d27234d27030725fa6a0405d5ba300d1857a6fcad0548d69':raise ValueError('R1 source coverage report changed')
    core=read(REPORTS/'r2-godot.json')
    graphics=read(REPORTS/'graphics-validation.json')
    ui=read(REPORTS/'r4-ui.json')
    gpu=read(REPORTS/'r4-gpu.json')
    old_ui=read(REPORTS/'r4-old-character-ui.json')
    movement=read(ROOT/'reports/exploration/godot-movement-validation.json')
    for name,value in [('core',core),('graphics',graphics),('ui',ui),('gpu',gpu),('old_ui',old_ui),('movement',movement)]:
        if value.get('passed') is not True:raise ValueError('Required gate failed: '+name)
    if ui['source_updates']!=15183 or old_ui['source_updates']!=6156 or movement['updates']!=1680:
        raise ValueError('Required source update coverage changed')
    if len(gpu['cases'])!=32 or any(c['differences'] for c in gpu['cases']):raise ValueError('GPU source view comparison failed')
    screenshots=[]
    for size in ('1920x1080','2560x1440','3840x2160'):
        engine=read(qa/size/'report.json');launch=read(qa/size/'launch.json')
        if (engine.get('schema')!='ao_pc_room_ui_qa_v1' or not engine.get('passed') or engine.get('error')
                or engine['actual_viewport']!=[int(n) for n in size.split('x')]
                or not launch['binary_identity_unchanged'] or launch['source_dirty']):
            raise ValueError('Screen/launch evidence failed')
        screenshots.append({'resolution':size,'file':str((qa/size/'screen.png').relative_to(ROOT)),
                            'sha256':sha((qa/size/'screen.png').read_bytes()),
                            'cold_process_first_surface_observed_ms':launch['launch_to_first_surface_observed_ms'],
                            'os_disk_cache_flushed':False})
    py=(REPORTS/'r5-python.log').read_text(encoding='utf-8-sig')
    known={'test_real_parameters_and_unsupported_settings','test_snapshot_pages_and_negative_raw_source_matches',
           'test_full_source_vram_match','test_full_source_replay_matches_pinned_snapshot',
           'test_real_block_provenance_without_collision_claim','test_system_ram_boundaries_and_mutation',
           'test_all_visible_patterns_and_prior_viewports_match','test_pinned_region_registers_and_memory',
           'test_real_palette_samples_remain_diagnostic'}
    errors=re.findall(r'^ERROR: (\w+) ',py,re.M)
    if set(errors)!=known or len(errors)!=9 or 'Ran 354 tests' not in py or 'FAILED (errors=9)' not in py:
        raise ValueError('Python regression outcome differs from the known missing snapshot boundary')
    result={'schema':'ao_pc_room_acceptance_v1','passed':False,'status':'awaiting_isolated_4k_soak',
            'source_commit':launch['source_commit'],'executable_sha256':launch['executable_sha256'],'pck_sha256':launch['pck_sha256'],
            'room_manifest_sha256':launch['room_manifest_sha256'],
            'source':{'routes':8,'replays_each':3,'captured_frames':16332,'verified_query_cells':613,
                      'actor_updates':core['actor_updates'],'completed_camera_updates':core['completed_camera_updates'],
                      'godot_core_checks':core['checks'],'graphics_frames':sum(c['frames'] for c in graphics['captures']),
                      'compared_non_shadow_pixels':sum(c['compared_non_shadow_pixels'] for c in graphics['captures']),
                      'unexplained_pixels':0,'gpu_cases':len(gpu['cases']),'gpu_compared_pixels':sum(c['compared'] for c in gpu['cases'])},
            'ui':{'checks':ui['checks'],'three_mode_updates':ui['source_updates'],'mismatches':0},
            'regressions':{'old_movement_updates':movement['updates'],'old_three_mode_updates':old_ui['source_updates'],
                           'python_full_run':354,'python_full_run_passed':345,'old_snapshot_unavailable':sorted(known),
                           'additional_room_package_tests':5,'old_snapshot_sha256':'615107b20f67b779d4d373a1cc79fce318f5f1a0093893dc7a963014ac80a7ab'},
            'screenshots':screenshots,'performance':None,'evidence_sha256':identities,
            'limits':['Original shadow omitted.','Exit is a test boundary; no adjacent scene or stair event.',
                      'Full MAP001 and Stage B remain unaccepted.','Actual GPU 120 FPS not part of this release target.']}
    if soak is not None:
        if environment_pre is None or environment_post is None:raise ValueError('Preflight and postflight host observations required')
        environments=[read(p.resolve()) for p in (environment_pre,environment_post)]
        if any(not e.get('assessment',{}).get('isolated_preflight_passed') for e in environments):raise ValueError('Host observation requires review')
        acceptance=read(soak/'soak-4k/acceptance.json')
        engine=read(soak/'soak-4k/report.json')
        identity=read(soak/'soak-4k/launch.json')
        if not acceptance.get('passed') or not acceptance.get('full_acceptance'):
            raise ValueError('Soak did not meet full acceptance; retain report and diagnose before packaging')
        if any(identity[k]!=result[k] for k in ('source_commit','executable_sha256','pck_sha256','room_manifest_sha256')):
            raise ValueError('Soak and screenshot binary identities differ')
        if engine['measured_seconds']<600 or engine['screenshots_during_measurement']!=0:raise ValueError('Invalid isolated measurement')
        result.update(passed=True,status='MAP001 同一室內擴展探索與鏡頭驗證通過',performance=acceptance)
        result['environment_observation_scope']='Read-only preflight/postflight sample windows; no process terminated and no whole-run causal attribution.'
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--qa',type=Path,required=True);p.add_argument('--soak',type=Path);p.add_argument('--environment-pre',type=Path);p.add_argument('--environment-post',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=assemble(a.qa,a.soak,a.environment_pre,a.environment_post);a.out.write_bytes(encoded(result))
    print(json.dumps({'passed':result['passed'],'status':result['status']},ensure_ascii=False))
