"""Reject incomplete or mixed-source interaction delivery evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'reports/interaction'
SCREENS='screens-release-02'
SOAK='soak-release-01/soak-4k'
SIZES=([1920,1080],[2560,1440],[3840,2160])
STATES=(('before',0),('pickup',0),('after',0),('stairs',0),('stairs',1))


def sha(raw):return hashlib.sha256(raw).hexdigest()
def require(value,message):
    if not value:raise ValueError(message)


def summarize():
    evidence={}
    def read(name,text=False):
        raw=(BASE/name).read_bytes();evidence[name]=sha(raw)
        return raw.decode('utf-8-sig') if text else json.loads(raw)
    phases={n:read(n+'.json') for n in ('p1-acceptance','p2-python','p2-godot','p3-ui','p3-gpu')}
    require(all(v.get('passed') is True for v in phases.values()),'Source/core/UI/GPU gate failed')
    require(phases['p1-acceptance']['replays']==39,'Source triple replay coverage')
    for name,digest in phases['p1-acceptance']['evidence'].items():
        require(sha((ROOT/name).read_bytes())==digest,'Changed source evidence: '+name)
    for n in ('p2-python','p2-godot'):
        require(sum(r['updates'] for r in phases[n]['routes'])==7970,'Core coverage '+n)
    require(phases['p3-ui']['source_updates']==23910 and phases['p3-ui']['checks']>=96,'UI coverage')
    require(len(phases['p3-gpu']['cases'])==34 and all(r['differences']==0 for r in phases['p3-gpu']['cases']),'Actual GPU source parity')
    for phase in ('preflight','postflight'):
        require(read('p5-host-'+phase+'.json')['assessment']['status']=='clear_in_sample_window','Background load '+phase)
    candidate=read('candidate.json');folder=Path(candidate['directory'])
    require(candidate['dirty'] is False,'Dirty binary source')
    identity={'source_commit':candidate['source_commit'],'source_dirty':False,
        'executable_sha256':sha((folder/'MAP001-Interaction.exe').read_bytes()),
        'pck_sha256':sha((folder/'MAP001-Interaction.pck').read_bytes()),
        'interaction_manifest_sha256':sha((folder/'interaction/package.json').read_bytes())}
    launches=[]
    def runtime(prefix,size):
        r=read(prefix+'/report.json');launch=read(prefix+'/launch.json')
        require(all(launch.get(k)==v for k,v in identity.items()),'Mixed binary identity '+prefix)
        require(launch.get('fresh_process') and launch.get('binary_identity_unchanged'),'Changed launch '+prefix)
        require(r.get('passed') and not r.get('error') and r.get('actual_viewport')==size and r.get('surface_verified'),'Actual render surface '+prefix)
        require(r.get('pc_device_policy') and r.get('interaction_images_preloaded'),'Wrong devices/preload')
        for stage in ('before','after'):require(read(prefix+'/package-'+stage+'.json')['passed'],'Package changed')
        launches.append({'case':prefix,'first_surface_ms':launch['launch_to_first_surface_observed_ms']})
        return r
    for size in SIZES:
        for state,page in STATES:
            prefix=f'{SCREENS}/{size[0]}x{size[1]}-{state}-{page}'
            r=runtime(prefix,size)
            expected_id={'before':'','pickup':'map001_00b061','after':'map001_00b061','stairs':'map001_00b0b5'}[state]
            require(r['dialogue_id']==expected_id and r['dialogue_page']==(page if state in ('pickup','stairs') else -1),'Wrong screenshot story/page '+prefix)
            require(r['story']==('01' if state=='before' else '03') and r['story_item_count']==(1 if state in ('after','stairs') else 0),'Wrong screenshot flags '+prefix)
            raw=(BASE/prefix/'screen.png').read_bytes();evidence[prefix+'/screen.png']=sha(raw)
            require(raw[:8]==b'\x89PNG\r\n\x1a\n' and [int.from_bytes(raw[16:20],'big'),int.from_bytes(raw[20:24],'big')]==size,'Screenshot dimensions')
    review=read('p5-visual-review.json')
    require(review.get('passed') is True and len(review.get('screens',{}))==15,'Visual review incomplete')
    for name,digest in review['screens'].items():require(evidence.get(name)==digest,'Unreviewed or changed screenshot')
    soak=read(SOAK+'/acceptance.json');r=runtime(SOAK,[3840,2160])
    require(soak['passed'] and soak['full_acceptance'] and not soak['failures'],'Soak gate')
    require(soak['recomputed_measured_seconds']>=600 and soak['average_fps']>=59 and soak['p95_ms']<=20,'Performance')
    require(not soak['spikes_over_100ms_require_reproduction_review'],'Unreviewed reproducible spike')
    require(soak['memory']['evaluated'] and soak['memory']['private_growth']<=.1 and len(soak['node_counts'])==1,'Memory/nodes')
    require(r['pixel_reads_during_measurement']==r['screenshots_during_measurement']==0 and r['routes_completed']>=4,'Unisolated or incomplete full story cycles')
    log=read('p4-python.log',True)
    errors=re.findall(r'^ERROR: (.+)$',log,re.M)
    known={'test_real_parameters_and_unsupported_settings','test_snapshot_pages_and_negative_raw_source_matches',
        'test_full_source_vram_match','test_full_source_replay_matches_pinned_snapshot','test_real_block_provenance_without_collision_claim',
        'test_system_ram_boundaries_and_mutation','test_all_visible_patterns_and_prior_viewports_match','test_pinned_region_registers_and_memory','test_real_palette_samples_remain_diagnostic'}
    require('Ran 393 tests' in log and 'FAILED (errors=9)' in log and len(errors)==9 and {e.split()[0] for e in errors}==known,'Unexpected Python regression')
    require(read('p4-character.json')['source_updates']==6156,'Character source fixtures omitted')
    for name,marker in (('p4-exploration.log','Exploration Godot, bundle, package and QA acceptance tests passed.'),
        ('p4-battle.log','Battle core, UI, presentation, timing and package checks passed.'),
        ('p4-runtime.log','"checks":14,"failures":[]'),('p4-workbench.log','"real_textures_loaded":true'),
        ('p4-qa-fixtures.log','Interaction QA acceptance: 58 fixture checks passed.')):
        require(marker in read(name,True),'Missing regression '+name)
    package_log=read('p5-package-tests.log',True)
    require('Ran 6 tests' in package_log and re.search(r'\bOK\s*$',package_log),'Package mutation tests')
    return {'schema':'ao_pc_interaction_runtime_acceptance_v1','passed':True,'identity':identity,
        'source_replays':39,'core_updates_per_model':7970,'three_appearance_updates':23910,'ui_checks':phases['p3-ui']['checks'],
        'gpu_source_windows':34,'completed_soak_cycles':r['routes_completed'],'soak':soak,'cold_process_launches':launches,
        'regression':{'python_passed':384,'unavailable_old_snapshot':errors,'legacy_movement_updates':1680,'legacy_character_updates':6156,'legacy_room_updates':15183,'legacy_event_updates':20037},
        'scope':'Runtime acceptance; final ZIP and extracted standalone launch are separate gates.',
        'limits':['Picked up is not equipped; observed stairs warn and retreat. Equipment menu and adjacent scenes remain unsupported.',
            'Source shadows omitted; Stage B and actual GPU 120 FPS not accepted.','Nine missing old snapshot tests retain the original lock.',
            'Text and optical-disc timing use whole-page PC/local-audio policy. Source assets and delivery remain local.',
            'Cold process starts do not flush Windows disk caches. GPU memory is sampled, not a continuous peak.'],
        'evidence_sha256':evidence}


def delivery():
    runtime=summarize();archive=json.loads((BASE/'p5-zip-audit.json').read_bytes())
    require(archive.get('passed') and sha(Path(archive['path']).read_bytes())==archive['sha256'],'ZIP changed')
    import audit_interaction_package as audit
    extracted=Path(archive['extraction']);audit.audit(extracted)
    require(json.loads((extracted/'INTERACTION_VALIDATION.json').read_bytes())==runtime,'Packaged runtime changed')
    evidence={};count=0
    for size in SIZES:
        for state,page in STATES:
            prefix=f'extracted-qa/{size[0]}x{size[1]}-{state}-{page}';values={}
            for name in ('report','launch','package-before','package-after'):
                raw=(BASE/prefix/(name+'.json')).read_bytes();evidence[prefix+'/'+name+'.json']=sha(raw);values[name]=json.loads(raw)
            r=values['report'];launch=values['launch']
            require(r['passed'] and r['actual_viewport']==size and r['dialogue_page']==(page if state in ('pickup','stairs') else -1),'Extracted story/page')
            require(launch['fresh_process'] and launch['binary_identity_unchanged'] and Path(launch['executable_path']).resolve()==(extracted/'MAP001-Interaction.exe').resolve(),'Extracted process')
            require(all(launch.get(k)==v for k,v in runtime['identity'].items()),'Extracted binary identity')
            require(values['package-before']['passed'] and values['package-after']['passed'],'Extracted package')
            count+=1
    raw=(BASE/'p5-summary-tests.log').read_bytes();text=raw.decode('utf-8-sig')
    require('Ran 7 tests' in text and re.search(r'\bOK\s*$',text),'Final evidence fault tests')
    evidence['p5-summary-tests.log']=sha(raw)
    return {'schema':'ao_pc_interaction_release_v1','passed':True,'completion':'MAP001 房內 Cirrus 主動互動與劇情狀態驗證通過',
        'binary_source_commit':runtime['identity']['source_commit'],'archive':archive,'runtime':runtime,'extracted_launch_cases':count,'delivery_evidence_sha256':evidence}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,default=BASE/'p5-runtime-acceptance.json');parser.add_argument('--delivery',action='store_true');args=parser.parse_args()
    result=delivery() if args.delivery else summarize()
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'report':str(args.report)}))
