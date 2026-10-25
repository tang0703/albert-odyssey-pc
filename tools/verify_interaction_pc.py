"""Compare the named PC scheduler with source-verified interaction fixtures."""
import json
from pathlib import Path
from interaction_contract import build
from interaction_pc_reference import PcModel
from summarize_interaction_source import ROUTES, sha
from verify_event_pc import snapshot as base_snapshot
from interaction_animation import spawn_spark

ROOT=Path(__file__).resolve().parents[1]


def snapshot(model):
    return base_snapshot(model)|{'spark':model.spark.hex() if model.spark is not None else None,
        'spark_child':dict(vars(model.spark_child)) if model.spark_child else None,
        'item_count':model.item_count,'temporary_coordinates':{str(k):list(v) for k,v in model.temp.items()},'resource':model.resource}


def main():
    gate_raw=(ROOT/'reports/interaction/p1-acceptance.json').read_bytes()
    if json.loads(gate_raw).get('passed') is not True:raise ValueError('P1 must pass first')
    contract=build();source=(ROOT.parent/'work/extract/MAP001.TWN').read_bytes();twn=(ROOT.parent/'work/extract/TWN.BIN').read_bytes()
    reports=[]
    for route in ROUTES:
        base='p1-v1' if route in ('direct','reminder-first') else 'p1-v2'
        folder=ROOT/'reports/interaction'/base/f'{route}-a'
        model=PcModel((folder/'frame-000000/wram-high.bin').read_bytes(),(folder/'frame-000000/wram-low.bin').read_bytes(),source,twn,contract)
        fixture=json.loads((ROOT/'generated/interaction/reference'/f'{route}.json').read_text())
        checks=0
        for row in fixture['updates']:
            signals={k:row['input'][k] for k in ('resource_loaded','resource_playing','text_active')}
            model.step(row['input']['pad'],signals,row['input']['pressed'])
            actual=json.loads(json.dumps(snapshot(model)))
            for key,value in actual.items():
                if value!=row['expected'][key]:raise ValueError(f'{route} update {model.update}: {key}')
                checks+=1
        reports.append({'route':route,'updates':model.update,'checks':checks,'runs':model.runs})
        print(route,model.update,flush=True)
    seed=ROOT/'reports/interaction/p1-v1/direct-a/frame-000000'
    model=PcModel((seed/'wram-high.bin').read_bytes(),(seed/'wram-low.bin').read_bytes(),source,twn,contract)
    spark,spark_profile=spawn_spark(model.high,model.low,model.profile.base,(0,0))
    def records(profile,animation):
        result=[]
        for cursor in range(0,192,3):
            record=profile.read_record(animation,cursor);result.append(list(record))
            if not record[0]:return result
        raise ValueError('Unterminated animation')
    extra={'player':{str(n):records(model.profile,n) for n in (24,25)},'spark':{'2':records(spark_profile,2)},
           'spark_image_pointers':{str(n):spark_profile.image_pointer(n) for n in (*range(32,43),44,127)},
           'spark_spawn':spark.hex()}
    initial=json.loads((ROOT/'generated/interaction/reference/direct.json').read_text())['initial_state']
    data={'schema':'ao_pc_interaction_core_v1','contract':contract,'initial_state':initial,
          'interaction':model.interaction,'extra_animations':extra,'source_acceptance_sha256':sha(gate_raw)}
    (ROOT/'generated/interaction/core.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    result={'schema':'ao_pc_interaction_converted_reference_v1','passed':True,'routes':reports,
            'programs_sha256':sha(json.dumps(contract['programs'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()),
            'extra_animations_sha256':sha(json.dumps(extra,sort_keys=True,separators=(',',':')).encode()),
            'scope':'Named PC instructions; original device acknowledgements are explicit inputs.'}
    (ROOT/'reports/interaction/p2-python.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
