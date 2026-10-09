"""Produce local shared Python/Godot room fixtures after fresh source comparisons."""
import argparse
import hashlib
import json
from pathlib import Path
import exploration_movement as movement
from validate_room_trace import validate
from verify_room_survey import MOVEMENT_ROUTES, VIDEO_ROUTES


def build(report_path: Path, output: Path) -> None:
    report_raw=report_path.read_bytes();report=json.loads(report_raw)
    if not report.get('passed') or not report.get('stage_r1_complete') or report['unobserved_required_queries']:
        raise ValueError('Room reference requires the completed R1 gate')
    traces=[]
    for name in (*MOVEMENT_ROUTES,*VIDEO_ROUTES):
        capture=Path(report['comparisons'][name]['capture'])
        result,fixture=validate(capture)
        if result != report['comparisons'][name]:
            raise ValueError('R1 source comparison changed: '+name)
        traces.append({'id':name,**fixture})
        print('Fresh room fixture: '+name,flush=True)
    first=Path(report['comparisons']['interior']['capture'])/'frame-000000'
    profile=movement.profile_from_snapshot((first/'wram-high.bin').read_bytes(),
        (first/'wram-low.bin').read_bytes(),report['verified_query_indices'])
    value={'schema':'ao_pc_room_reference_v1','r1_report_sha256':hashlib.sha256(report_raw).hexdigest(),
           'movement_profile':profile.metadata(),'boundaries':report['boundaries'],
           'camera_profile':traces[0]['camera_profile'],'traces':traces}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();build(args.report,args.out)
