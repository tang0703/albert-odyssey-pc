"""T1 gate: nine full routes and three frame-by-frame held-input transfers.

This gate certifies source study only. It cannot approve a runtime or ZIP.
"""
import json
from pathlib import Path
from transition_source import ROOT,build,sha
from verify_transition_capture import run,verify_files
from verify_transition_initialization import validate


def main():
    base=ROOT/'reports/transition'
    result=run(base)
    parent=base/'probes/precommit'
    parent_manifest,parent_files,parent_sha=verify_files(parent)
    seed_name='frame-001090/state.savestate'
    seed_sha=parent_files[seed_name]
    if seed_sha!='e5083a0fce124e0f2af8eeb95e4c1f0b977a282cc1d2db274481fdd5db0e2c31':
        raise ValueError('Named precommit seed changed')
    initial_sha='72d9fa56fbf525dbb71ae3a21d8e3aaa45f23b7711bfdce2b95d6c6472776b54'
    if not any(Path(r['path']).suffix=='.savestate' and r['sha256']==initial_sha for r in parent_manifest['inputs']):
        raise ValueError('Derivative seed lost original named-state chain')
    reference=None;details=[]
    folders=[base/'probes/hold-through',base/'t1-hold-through-2',base/'t1-hold-through-3']
    for folder in folders:
        manifest,files,digest=verify_files(folder)
        if not any(Path(r['path']).suffix=='.savestate' and r['sha256']==seed_sha for r in manifest['inputs']):
            raise ValueError('Detailed transfer used a different initial state')
        if reference is None:reference=files
        elif files!=reference:raise ValueError('Detailed transfer repeats differ')
        proof=validate(folder)
        if not proof['passed']:raise ValueError('Initialization component comparison failed')
        (base/(folder.name+'-proof.json')).write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
        details.append({k:proof[k] for k in ('capture','capture_manifest_sha256','checks','actor_camera_updates',
            'fade_out_begin_frame','initialization_frame','fade_in_begin_frame','first_visible_destination_frame','first_accepted_movement_frame')})
    result.update(t1_complete=True,remaining_t1_evidence=[],detailed_replays=details,
        named_precommit_seed={'path':(parent/seed_name).relative_to(ROOT).as_posix(),'sha256':seed_sha,
                              'capture_manifest_sha256':parent_sha,'parent_state_sha256':initial_sha},
        downstream_gates=['Continuous transition scheduler and Godot parity','Landing coverage and pixel composition',
                          'PC input/reset integration','Short visual/package acceptance'],
        performance_status='deferred_by_user_no_test_performed')
    high=(ROOT/'reports/exploration/e1-nav-05/frame-000600/wram-high.bin').read_bytes()
    inventory=build(bytes([7])+high[0x36939:0x369b8])
    (base/'source-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n',encoding='utf-8')
    out=base/'t1-acceptance.json'
    out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    # Metadata only: no original art, binary script, RAM or state enters Git.
    lock={'schema':'ao_pc_transition_t1_source_lock_v1','baseline_commit':'8649f33de29d72979be59173796aab8dc53df42d',
          'gate_report':out.relative_to(ROOT).as_posix(),'gate_report_sha256':sha(out.read_bytes()),
          'source_inventory_sha256':sha((base/'source-inventory.json').read_bytes()),
          'named_precommit_seed':result['named_precommit_seed'],
          'replays':[{k:r[k] for k in ('route','repeat','manifest_sha256')} for r in result['replays']],
          'detailed_replays':details,'t1_complete':True,'runtime_approved':False,'performance_tested':False}
    (ROOT/'data/transition/source-lock.json').write_text(json.dumps(lock,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'t1_complete':True,'formal_replays':9,'detailed_replays':3,'runtime_approved':False,'performance_tested':False}))


if __name__=='__main__':main()
