"""Summarize freshly run functional regressions without performance claims."""
import json
from landing_event_source import ROOT, sha
from equipment_contract import encoded


def build():
    base=ROOT/'reports/landing-event';evidence={};counts={}
    def read(path):
        raw=path.read_bytes();text=raw.decode('utf-8',errors='replace')
        if any(s in text for s in ('SCRIPT ERROR:','Parse Error:','FAILED (','Assertion failed')):raise ValueError('Regression error: '+str(path))
        evidence[path.relative_to(ROOT).as_posix()]=sha(raw);return text
    for name,count in [('room',15183),('event',20037),('interaction',23910),('equipment',11064)]:
        text=read(ROOT/'reports/exploration'/f'test_{name}_ui.log')
        rows=[json.loads(line) for line in text.splitlines() if line.startswith('{')]
        if len(rows)!=1 or not rows[0]['passed'] or rows[0]['source_updates']!=count:raise ValueError('Missing old three-mode regression: '+name)
        counts[name]=count
    transfer=json.loads((ROOT/'reports/transition/t4-ui.json').read_bytes())
    if not transfer['passed'] or transfer['source_updates']!=10965:raise ValueError('Transfer regression differs')
    evidence['reports/transition/t4-ui.json']=sha((ROOT/'reports/transition/t4-ui.json').read_bytes());counts['transition']=10965
    movement=json.loads((ROOT/'reports/exploration/godot-movement-validation.json').read_bytes())
    if not movement['passed'] or movement['updates']!=1680:raise ValueError('Movement source regression differs')
    counts['movement']=1680;evidence['reports/exploration/godot-movement-validation.json']=sha((ROOT/'reports/exploration/godot-movement-validation.json').read_bytes())
    character=json.loads((base/'l5-character.json').read_bytes())
    if not character['passed'] or character['source_updates']!=6156 or character['hd_package_status']!='passed':raise ValueError('Character three-mode regression incomplete')
    counts['character']=6156;evidence['reports/landing-event/l5-character.json']=sha((base/'l5-character.json').read_bytes())
    for name,marker in [('l5-battle.log','Battle core, UI, presentation, timing and package checks passed.'),
        ('l5-exploration.log','Exploration Godot, bundle, package and QA acceptance tests passed.'),
        ('l5-runtime.log','"checks":14,"failures":[]'),('l5-workbench.log','"real_textures_loaded":true')]:
        if marker not in read(base/name):raise ValueError('Incomplete regression: '+name)
    result={'schema':'ao_pc_landing_event_regression_v1','passed':True,'performance_tested':False,'source_updates':counts,'evidence':evidence,
        'scope':'Available functional regressions. No load test or actual GPU FPS measurement.'}
    (base/'l5-regression.json').write_bytes(encoded(result));print(json.dumps(result))


if __name__=='__main__':build()
