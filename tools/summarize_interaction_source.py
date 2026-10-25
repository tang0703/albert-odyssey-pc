"""Fail-closed P1 gate. Local evidence and source art are never copied to Git."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ROUTES=('direct','reminder-first','left-edge','right-edge','near-edge','wrong-facing','hold','rapid',
        'left-inside','right-inside','near-inside','east-facing','west-facing')
NEGATIVE={'left-edge','right-edge','near-edge','wrong-facing','east-facing','west-facing'}


def sha(raw):return hashlib.sha256(raw).hexdigest()


def summarize():
    root=ROOT/'reports/interaction';evidence={};routes=[];queries=set()
    def read(path):
        raw=path.read_bytes();row=json.loads(raw)
        if row.get('passed') is not True:raise ValueError('Unpassed gate: '+str(path))
        evidence[str(path.relative_to(ROOT)).replace('\\','/')]=sha(raw)
        return row
    for route in ROUTES:
        base=root/('p1-v1' if route in ('direct','reminder-first') else 'p1-v2')
        replay=read(base/f'{route}-replay.json');model=read(base/f'{route}-model.json');trigger=read(base/f'{route}-trigger.json')
        if replay.get('replays')!=3 or replay.get('differing_outputs'):raise ValueError('Incomplete replay evidence')
        first=base/f'{route}-a';identity=sha((first/'manifest.json').read_bytes())
        if identity not in [r['manifest_sha256'] for r in replay['captures']] or model['capture_manifest_sha256']!=identity or trigger['capture_manifest_sha256']!=identity:
            raise ValueError('Mixed source capture evidence')
        for row in replay['captures']:
            if sha((Path(row['folder'])/'manifest.json').read_bytes())!=row['manifest_sha256']:raise ValueError('Replay manifest changed')
        last=model['final_observed'];negative=route in NEGATIVE
        if (last['story'],last['item_count'],last['control_disabled'],last['root_active'])!=('01' if negative else '03',0 if negative else 1,0,False):
            raise ValueError('Unexpected final story/control state')
        if model['updates']!=replay['frames_per_replay'] or model['errors'] or trigger['errors']:raise ValueError('Incomplete source comparison')
        queries.update(model['query_indices'])
        routes.append({'id':route,'frames':model['updates'],'checks':model['checks'],'runs':model['runs'],
                       'trigger_attempts':len(trigger['attempts']),'final':last,'capture_manifest_sha256':identity})
    confirmations=0;text_checks=0
    for route,count in (('direct',3),('reminder-first',5),('hold',1),('rapid',1)):
        base=root/('p1-v1' if route in ('direct','reminder-first') else 'p1-v2')
        report=read(base/f'{route}-text-input.json')
        if len(report['accepted_confirmations'])!=count:raise ValueError('Source confirmation count differs')
        confirmations+=count;text_checks+=report['checks']
    link=read(root/'p1-direct-capture-link.json');world=read(root/'p1-direct-world.json')
    if world['capture_manifest_sha256']!=link['render_manifest_sha256'] or world['errors'] or world['pixels']['passed'] is not True:
        raise ValueError('Mixed or incomplete world comparison')
    sprites_raw=(ROOT/'generated/interaction/source-sprites/source-sprites.json').read_bytes();sprites=json.loads(sprites_raw)
    if sprites['capture_manifest_sha256']!=link['render_manifest_sha256'] or not sprites['source_binding_passed'] or len(sprites['sprites'])!=16:
        raise ValueError('Unverified source sprites')
    for row in sprites['sprites']:
        if sha((ROOT/'generated/interaction/source-sprites'/row['file']).read_bytes())!=row['sha256']:raise ValueError('Source sprite changed')
    evidence['generated/interaction/source-sprites/source-sprites.json']=sha(sprites_raw)
    audio_raw=(ROOT/'generated/interaction/source-audio/source-audio.json').read_bytes();audio=json.loads(audio_raw)
    if not audio['pcm_roundtrip_passed'] or sha((ROOT/'generated/interaction/source-audio/cirrus-pickup.wav').read_bytes())!=audio['output_sha256']:
        raise ValueError('Changed source audio')
    evidence['generated/interaction/source-audio/source-audio.json']=sha(audio_raw)
    return {'schema':'ao_pc_interaction_p1_acceptance_v1','passed':True,'pc_runtime_acceptance':False,
            'routes':routes,'replays':len(routes)*3,'comparison_points':sum(r['frames'] for r in routes),
            'complete_logic_updates':sum(r['frames']-1 for r in routes),'checks':sum(r['checks'] for r in routes),
            'query_indices':sorted(queries),'source_confirmation_checks':text_checks,'accepted_source_confirmations':confirmations,
            'world_draws':len(world['frames']),'world_pixel_count':world['pixels']['compared_world_pixels'],
            'evidence':evidence,'limitations':['Original UI pixels and shadow excluded from world composition.',
                'Equipped-story bit is unverified; observed post-pickup stairs still warn and retreat.',
                'P2-P5, Windows/Godot/input/performance acceptance remain separate gates.']}


if __name__=='__main__':
    result=summarize();path=ROOT/'reports/interaction/p1-acceptance.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('routes','query_indices','evidence','limitations')}))
