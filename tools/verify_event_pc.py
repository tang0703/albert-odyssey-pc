"""Compare converted PC scheduler with all six source-verified fixtures."""
import json
from pathlib import Path
from event_contract import build, sha
from event_pc_reference import PcModel
from verify_event_capture_links import ROUTES

ROOT = Path(__file__).resolve().parents[1]


def snapshot(model):
    return dict(player=model.player.hex(), decor=model.decor.hex(), ambient=model.ambient.hex(),
                effect=vars(model.effect) if model.effect else None, effect_xy=model.effect_xy,
                cameras=model.cameras, disabled=model.disabled, fixed_camera=model.fixed,
                camera_target=model.target, camera_speed=model.speed,
                root=vars(model.root) if model.root else None, child=vars(model.child) if model.child else None,
                runs=model.runs, story=model.story.hex(), commands=model.commands, requests=model.requests, update=model.update)


def main():
    gate=json.loads((ROOT/'reports/event/d1-acceptance.json').read_text())
    if gate.get('passed') is not True: raise ValueError('D1 must pass first')
    contract=build()
    source=(ROOT.parent/'work/extract/MAP001.TWN').read_bytes()
    twn=(ROOT.parent/'work/extract/TWN.BIN').read_bytes()
    reports=[]
    for route in ROUTES:
        folder=ROOT/'reports/event/d1-detail'/f'{route}-a'
        model=PcModel((folder/'frame-000000/wram-high.bin').read_bytes(),
                      (folder/'frame-000000/wram-low.bin').read_bytes(), source, twn, contract)
        fixture=json.loads((ROOT/'generated/event/reference'/f'{route}.json').read_text())
        checks=0
        for row in fixture['updates']:
            signals={k:row['input'][k] for k in ('resource_loaded','resource_playing','text_active')}
            model.step(row['input']['pad'],signals)
            actual=json.loads(json.dumps(snapshot(model)))
            for key,value in actual.items():
                if value!=row['expected'][key]: raise ValueError(f'{route} update {model.update}: {key}')
                checks+=1
        reports.append({'route':route,'updates':model.update,'checks':checks,'runs':model.runs})
    fixture=json.loads((ROOT/'generated/event/reference/center.json').read_text())
    data={'schema':'ao_pc_event_core_v1','contract':contract,'initial_state':fixture['initial_state'],
          'source_acceptance_sha256':sha((ROOT/'reports/event/d1-acceptance.json').read_bytes())}
    target=ROOT/'generated/event/core.json'
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    result={'schema':'ao_pc_event_converted_reference_v1','passed':True,'routes':reports,
            'scope':'Named PC instructions with source device acknowledgements; PC UI/audio providers separate.'}
    (ROOT/'reports/event/d2-python.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
