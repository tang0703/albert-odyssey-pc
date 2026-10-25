"""Preserve passed functional evidence without promoting deferred performance."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'reports/interaction'


def build():
    evidence={}
    def read(name):
        raw=(BASE/name).read_bytes();evidence[name]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
    phases={name:read(name+'.json') for name in ('p1-acceptance','p2-python','p2-godot','p3-ui','p3-gpu')}
    if not all(v['passed'] is True for v in phases.values()):raise ValueError('Functional gate incomplete')
    if phases['p1-acceptance']['replays']!=39 or phases['p3-ui']['source_updates']!=23910 or phases['p3-ui']['checks']<96:raise ValueError('Functional coverage differs')
    if any(sum(r['updates'] for r in phases[name]['routes'])!=7970 for name in ('p2-python','p2-godot')):raise ValueError('Core coverage differs')
    if len(phases['p3-gpu']['cases'])!=34 or any(r['differences'] for r in phases['p3-gpu']['cases']):raise ValueError('GPU evidence differs')
    visual=read('p5-visual-review.json')
    if visual['passed'] is not True or len(visual['screens'])!=15:raise ValueError('Visual review incomplete')
    for name,digest in visual['screens'].items():
        if hashlib.sha256((BASE/name).read_bytes()).hexdigest()!=digest:raise ValueError('Reviewed screenshot changed')
        evidence[name]=digest
        for leaf in ('report.json','launch.json','package-before.json','package-after.json'):read(str(Path(name).parent/leaf))
    candidate=read('candidate.json');folder=Path(candidate['directory'])
    if candidate['dirty']:raise ValueError('Dirty binary source')
    first=read('soak-release-01/soak-4k/acceptance.json');profile=read('p5-profile.json')
    for name in ('p4-python.log','p4-exploration.log','p4-character.log','p4-battle.log','p4-runtime.log','p4-workbench.log','p4-qa-fixtures.log','p5-package-tests.log'):
        evidence[name]=hashlib.sha256((BASE/name).read_bytes()).hexdigest()
    result={'schema':'ao_pc_interaction_candidate_validation_v1','passed':False,'status':'performance_validation_deferred_by_user',
        'user_instruction':'先不進行負載測試','functional_validation_passed':True,'visual_validation_passed':True,
        'binary_source_commit':candidate['source_commit'],'executable_sha256':hashlib.sha256((folder/'MAP001-Interaction.exe').read_bytes()).hexdigest(),
        'pck_sha256':hashlib.sha256((folder/'MAP001-Interaction.pck').read_bytes()).hexdigest(),
        'source_replays':39,'core_updates_per_model':7970,'three_appearance_updates':23910,'ui_checks':96,'gpu_source_windows':34,
        'first_soak':first,'diagnostic':{'completed':profile['completed'],'seconds':profile['measured_seconds'],'cycles':profile['routes_completed'],'maximum_frame_ms':profile['distributions']['post_to_post_ms']['max']},
        'pending':['Independent 600-second repeat deferred by user.','Initial >100ms spikes remain unconfirmed; diagnostic did not reproduce them.','Formal P5 completion is not granted.'],
        'limits':['No equipment menu or adjacent room. Source post-pickup stairs warn and retreat.','Source shadows, actual GPU 120 FPS and Stage B incomplete.','Nine missing old snapshot tests retain original locks.','Source assets and ZIP remain local.'],
        'evidence_sha256':evidence}
    (BASE/'p5-candidate-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result

def delivery():
    evidence={}
    def read(path):
        raw=path.read_bytes();evidence[str(path.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
    validation=read(BASE/'p5-candidate-validation.json')
    archive=read(BASE/'p5-candidate-zip-audit.json')
    if validation['passed'] is not False or validation['status']!='performance_validation_deferred_by_user':
        raise ValueError('Candidate requires explicit deferred acceptance')
    if archive['passed'] is not True or archive['runtime_acceptance'] is not False:
        raise ValueError('Candidate archive audit differs')
    zip_path=Path(archive['path'])
    if zip_path.name!='MAP001-Interaction-Candidate-Windows-x64.zip' or hashlib.sha256(zip_path.read_bytes()).hexdigest()!=archive['sha256']:
        raise ValueError('Candidate ZIP identity differs')
    extracted=Path(archive['extraction'])
    if read(extracted/'INTERACTION_VALIDATION.json')!=validation:
        raise ValueError('Packaged validation differs')
    launches=[]
    for case,text_id,page in [('1920x1080-pickup-0','map001_00b061',0),('1920x1080-stairs-1','map001_00b0b5',1)]:
        folder=BASE/'candidate-extracted-qa'/case
        report=read(folder/'report.json');launch=read(folder/'launch.json')
        if not report['passed'] or report['actual_viewport']!=[1920,1080] or report['dialogue_id']!=text_id or report['dialogue_page']!=page:
            raise ValueError('Extracted UI state differs')
        if not launch['fresh_process'] or not launch['binary_identity_unchanged'] or launch['source_dirty']:
            raise ValueError('Extracted launch identity differs')
        if Path(launch['executable_path']).resolve()!=(extracted/'MAP001-Interaction.exe').resolve() or launch['source_commit']!=validation['binary_source_commit']:
            raise ValueError('Extracted executable source differs')
        for key,filename in [('executable_sha256','MAP001-Interaction.exe'),('pck_sha256','MAP001-Interaction.pck')]:
            if launch[key]!=validation[key] or hashlib.sha256((extracted/filename).read_bytes()).hexdigest()!=validation[key]:
                raise ValueError('Extracted binary hash differs')
        for leaf in ('package-before.json','package-after.json'):
            if read(folder/leaf)['passed'] is not True:raise ValueError('Extracted package audit failed')
        launches.append({'case':case,'passed':True,'dialogue_id':text_id,'page':page,'process_id':launch['process_id'],'source_commit':launch['source_commit']})
    result={'schema':'ao_pc_interaction_candidate_release_v1','formal_acceptance':False,
        'candidate_package_verified':True,'status':validation['status'],'user_instruction':validation['user_instruction'],
        'binary_source_commit':validation['binary_source_commit'],'archive':archive,'extracted_launches':launches,
        'functional_validation_passed':True,'visual_validation_passed':True,'pending':validation['pending'],
        'limits':validation['limits'],'evidence_sha256':evidence}
    (ROOT/'docs/INTERACTION_CANDIDATE_RELEASE.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    zip_path.with_suffix('.zip.sha256').write_text(archive['sha256']+'  '+zip_path.name+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--delivery',action='store_true');args=parser.parse_args()
    result=delivery() if args.delivery else build()
    print(json.dumps({'formal_acceptance':False,'status':result['status']}))
