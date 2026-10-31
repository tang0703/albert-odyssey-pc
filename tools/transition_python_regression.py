"""Run available Python checks; preserve nine missing-snapshot failures explicitly."""
import json
import os
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
KNOWN={
    'test_real_parameters_and_unsupported_settings',
    'test_snapshot_pages_and_negative_raw_source_matches',
    'test_full_source_vram_match','test_full_source_replay_matches_pinned_snapshot',
    'test_real_block_provenance_without_collision_claim','test_system_ram_boundaries_and_mutation',
    'test_all_visible_patterns_and_prior_viewports_match','test_pinned_region_registers_and_memory',
    'test_real_palette_samples_remain_diagnostic',
}

def run():
    base=ROOT/'reports/transition';temp=base/'temp';temp.mkdir(exist_ok=True)
    os.environ['TEMP']=os.environ['TMP']=str(temp)
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    with (base/'t5-python.log').open('w',encoding='utf-8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    known=[];unexpected=[]
    for case,error in result.errors:
        name=case.id().split('.')[-1]
        guards=('ValueError: Source hash mismatch:','ValueError: Pinned little-endian v13 state required','ValueError: Save-state fixture identity changed')
        if name in KNOWN and any(g in error for g in guards):known.append(case.id())
        else:unexpected.append({'test':case.id(),'error':error})
    unexpected.extend({'test':case.id(),'error':error} for case,error in result.failures)
    report={'schema':'ao_pc_transition_python_regression_v1','available_tests_passed':not unexpected,
            'all_tests_passed':result.wasSuccessful(),'tests':result.testsRun,
            'passed':result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
            'unavailable_old_snapshot':known,'skipped':[{'test':case.id(),'reason':why} for case,why in result.skipped],
            'unexpected':unexpected,'performance_tested':False}
    (base/'t5-python.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('skipped','unexpected','unavailable_old_snapshot')}))
    print('Known unavailable:',len(known),'Skipped:',len(result.skipped),'Unexpected:',len(unexpected))
    raise SystemExit(0 if not unexpected else 1)

if __name__=='__main__':run()
