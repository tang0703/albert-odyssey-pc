"""Source-pinned, local-only character package kept separate from the scene."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

from PIL import Image

import character_animation as animation
import character_graphics as graphics
import exploration_bundle as scene
from exploration_capture import stable_read

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'ao_pc_character_bundle_v1'
PIN_SCHEMA = 'ao_pc_character_bundle_pin_v1'
APPEARANCE_SCHEMA = 'ao_pc_character_appearances_v1'
DEFAULT_OUT = ROOT/'exploration-demo/generated/character'
DEFAULT_PIN = ROOT/'exploration-demo/character-pin.json'
ART = ROOT/'reports/character/reference-art'
ANIMATION_REPORT = ROOT/'reports/character/animation-validation.json'
PRESENTATION_INDEX = ROOT/'reports/character/presentation-index.json'
FOREGROUND = ROOT/'reports/character/foreground-source'
PROPS_SOURCE = ROOT/'reports/character/scene-props-source'
ORDER_REPORT = ROOT/'reports/character/draw-order-validation.json'
FOREGROUND_RULE = {'sprite_priority':2,'foreground_priority':3,'layers':[0,1],'equal_background_priority_winner':0}
SEED_SHA = '72d9fa56fbf525dbb71ae3a21d8e3aaa45f23b7711bfdce2b95d6c6472776b54'
DIRECTIONS = {'down':2, 'left':4, 'right':0, 'up':6}
IDLE = {'down':0, 'left':1, 'right':1, 'up':2}
WALK = {'down':5, 'left':9, 'right':9, 'up':13}
ROUTES = ('cardinal','corners','open','release')
COUNTS = {'cardinal':364,'corners':170,'open':118,'release':32}
PNG_FILES = {f'{d}-{action}.png' for d in DIRECTIONS for action in ['idle',*[f'walk-{n:02d}' for n in range(4)]]}
PROP_FILES={f'prop-{slot:02d}.png' for slot in range(6)}
PAYLOADS = PNG_FILES | PROP_FILES | {'profile.json','animation-bank.bin','image-table.bin','appearances.json','layers.json','nbg-priority-foreground.png'}
FILES = PAYLOADS | {'package.json'}
DELAY = {'executed_actor_sample_lag':1,'executed_body_source_sample_lag':2,
         'executed_body_camera_sample_lag':0,'draw_to_presented_video_lag':1,
         'presented_body_source_sample_lag':3}
SOURCES = {'PARTY0.PTY':graphics.PARTY_SHA256,'MAP001.TWN':graphics.MAP_SHA256,'TWN.BIN':graphics.TWN_SHA256}
LAYER_SCHEMA='ao_pc_character_layers_v1'
SCOPE='Original player and six static props with source foreground; objects 6/7 and shadow omitted'
SORTING={'bucket_count':768,'initial_bucket_min':40,'initial_bucket_max':700,'bucket_bias':256,
    'divisor':16,'objects_before_actor':True,'collision':'next_free_bucket','priority_limit':256,
    'actor_slot':0,'actor_command_priority':10,'actor_sprite_priority':2,'actor_y_sorted':True}


def expected_props() -> list[dict]:
    world=[[12800,27904],[10880,26368],[11424,27136],[12032,27136],[12032,27920],[12112,28096]]
    anchors=[[14,19],[24,40],[21,24],[21,24],[8,40],[8,32]]
    dimensions=[[24,24],[48,40],[32,24],[32,24],[16,24],[16,16]]
    return [{'id':f'object_{slot}','slot':slot,'file':f'prop-{slot:02d}.png','world_xy_raw':world[slot],
        'anchor':anchors[slot],'dimensions':dimensions[slot],'y_sorted':True,'command_priority':10,
        'sprite_priority':2 if slot<4 else 3,'render_flags':18 if slot<4 else 19} for slot in range(6)]


def expected_frames() -> list[dict]:
    rows=[]
    for direction,heading in DIRECTIONS.items():
        for primary in [None,0,1,2,3]:
            moving=primary is not None
            suffix=f'walk-{primary:02d}' if moving else 'idle'
            rows.append({'id':f'map001_player/{direction}/{suffix}','direction':direction,'heading':heading,
                'action':'walk' if moving else 'idle','primary_index':primary,
                'animation_index':heading+(8 if moving else 0),'animation_cursor':primary*3 if moving else 0,
                'duration_updates':10 if moving else 1,'image_index':WALK[direction]+primary if moving else IDLE[direction],
                'baked_mirror_x':direction=='right','anchor':[16,36 if direction=='up' and moving else 35],
                'dimensions':[32,40],'file':f'{direction}-{suffix}.png'})
    return rows


def exact_files(folder: Path) -> None:
    scene.no_redirect(folder)
    if not folder.is_dir() or {p.name for p in folder.iterdir()} != FILES:
        raise ValueError('Character package must contain exactly its 33 approved files')
    for path in folder.iterdir():
        scene.no_redirect(path)
        if not path.is_file() or path.resolve().parent != folder.resolve():
            raise ValueError('Character package entry is not a direct regular file')


def _png(raw: bytes, dimensions: tuple[int,int]=(32,40)) -> Image.Image:
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != 'PNG' or image.mode != 'RGBA' or image.size != dimensions:
            raise ValueError('Original image must be RGBA PNG with its source dimensions')
        image.verify()
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        result=image.copy()
        if any(alpha not in (0,255) for alpha in result.getchannel('A').getdata()):
            raise ValueError('Original source layers require binary alpha for exact priority composition')
        return result


def load_foreground(index_raw: bytes) -> tuple[dict,bytes,str]:
    raw=stable_read(FOREGROUND/'manifest.json')
    manifest=scene.decoded(raw)
    if (not isinstance(manifest,dict) or set(manifest) != {'schema','source_local_only','camera','viewport','rule',
            'source_hashes','presentation_index_sha256','files','limits'} or manifest['schema'] != 'ao_pc_character_foreground_v1' or
            manifest['source_local_only'] is not True or manifest['camera'] != [544,1536] or manifest['viewport'] != [320,224] or
            manifest['rule'] != FOREGROUND_RULE or manifest['source_hashes'] != {'MAP001.TWN':graphics.MAP_SHA256} or
            manifest['presentation_index_sha256'] != scene.digest(index_raw)):
        raise ValueError('Unknown or unbound source foreground')
    name='nbg-priority-foreground.png'
    if not isinstance(manifest['files'],dict) or set(manifest['files']) != {name}:
        raise ValueError('Unexpected source foreground files')
    record=manifest['files'][name]
    if (not isinstance(record,dict) or set(record) != {'bytes','sha256','rgba_sha256','width','height'} or
            not scene.valid_hash(record['sha256']) or not scene.valid_hash(record['rgba_sha256']) or
            (record['width'],record['height']) != (320,224)):
        raise ValueError('Invalid source foreground dimensions or identity')
    png=stable_read(FOREGROUND/name)
    image=_png(png,(320,224))
    if len(png) != record['bytes'] or scene.digest(png) != record['sha256'] or scene.digest(image.tobytes()) != record['rgba_sha256']:
        raise ValueError('Source foreground PNG or decoded pixels changed')
    return {'file':name,'dimensions':[320,224],'rule':FOREGROUND_RULE,'rgba_sha256':record['rgba_sha256']},png,scene.digest(raw)


def load_props(captures: dict) -> tuple[dict,str,str]:
    import character_draw_order as order
    raw=stable_read(PROPS_SOURCE/'manifest.json')
    manifest=scene.decoded(raw)
    if (manifest.get('schema') != 'ao_pc_character_scene_props_v1' or manifest.get('passed') is not True or
            manifest.get('source_local_only') is not True or manifest.get('camera') != [544,1536] or manifest.get('viewport') != [320,224]):
        raise ValueError('Unknown source furniture export')
    expected_sources={'MAP001.TWN':graphics.MAP_SHA256,'MAP001.V1N':graphics.MAP_V1N_SHA256,
        'TWN.BIN':graphics.TWN_SHA256,'0':animation.movement.p.CORE_HASH}
    if {name:record['sha256'] for name,record in manifest.get('source_files',{}).items()} != expected_sources:
        raise ValueError('Unknown furniture source identities')
    proof_raw=stable_read(ORDER_REPORT)
    proof=scene.decoded(proof_raw)
    if (manifest.get('order_proof',{}).get('sha256') != scene.digest(proof_raw) or
            proof.get('schema') != 'ao_character_draw_order_validation_v1' or proof.get('passed') is not True or
            proof.get('frame_count') != sum(COUNTS.values())):
        raise ValueError('Source furniture lacks the complete draw-order proof')
    source_ranges=order.verify_source(stable_read(ROOT.parent/'work/extract/TWN.BIN'),stable_read(ROOT.parent/'work/extract/0'))
    if proof.get('source_ranges') != source_ranges: raise ValueError('Draw-order source pins changed')
    proof_captures={Path(row['folder']).name:row['manifest_sha256'] for row in proof.get('captures',[])}
    required={r+'-a':captures[r+'-a'] for r in ROUTES}
    if proof_captures != required: raise ValueError('Draw-order captures differ from character validation')
    immutable=manifest.get('immutable_prop_evidence',{})
    if (immutable.get('passed') is not True or immutable.get('samples_compared') != sum(COUNTS.values())+4 or
            immutable.get('slots') != list(range(6)) or immutable.get('capture_manifests') != required):
        raise ValueError('Static furniture has not been proved immutable over all source samples')
    props=manifest.get('props')
    files=manifest.get('files')
    if not isinstance(props,list) or len(props)!=6 or not isinstance(files,dict) or set(files)!=PROP_FILES:
        raise ValueError('Six source furniture images are required')
    payload={}
    for expected,prop in zip(expected_props(),props):
        pieces=prop.get('pieces',[])
        if len(pieces) != 1: raise ValueError('Multi-piece furniture is outside this package profile')
        projected={key:prop.get(key) for key in ('id','slot','file','world_xy_raw','anchor','y_sorted','render_flags')}
        projected.update({'dimensions':[prop.get('width'),prop.get('height')],
            'command_priority':pieces[0].get('effective_priority'),'sprite_priority':pieces[0].get('sprite_priority')})
        if scene.encoded(projected) != scene.encoded({key:expected[key] for key in projected}):
            raise ValueError('Furniture source geometry or priorities differ from the pinned room')
        record=files[expected['file']]
        if set(record) != {'bytes','sha256','rgba_sha256','width','height'} or [record['width'],record['height']] != expected['dimensions']:
            raise ValueError('Invalid furniture image identity')
        image_raw=stable_read(PROPS_SOURCE/expected['file'])
        image=_png(image_raw,tuple(expected['dimensions']))
        if len(image_raw) != record['bytes'] or scene.digest(image_raw) != record['sha256'] or scene.digest(image.tobytes()) != record['rgba_sha256']:
            raise ValueError('Furniture PNG or decoded pixels changed')
        payload[expected['file']]=image_raw
    return payload,scene.digest(raw),scene.digest(proof_raw)


def _presentation(value: dict) -> None:
    if not isinstance(value,dict) or set(value) != {'state','delay_profile','scope'}:
        raise ValueError('Unknown character presentation metadata')
    if value['state'] != 'source_draw_and_visibility_verified' or value['delay_profile'] != DELAY:
        raise ValueError('Unverified character presentation or delay')
    if any(type(v) is not int for v in value['delay_profile'].values()):
        raise ValueError('Presentation delay must be integral')
    if value['scope'] != SCOPE:
        raise ValueError('Unknown presentation scope')


def verify(bundle: Path, expected_manifest_sha: str, scene_bundle: Path=scene.DEFAULT_OUT,
           expected_scene_sha: str|None=None) -> dict:
    if not scene.valid_hash(expected_manifest_sha) or not scene.valid_hash(expected_scene_sha):
        raise ValueError('Trusted character and scene manifest hashes are required')
    scene.verify(scene_bundle,expected_scene_sha)
    bundle=Path(bundle)
    exact_files(bundle)
    raw_manifest=stable_read(bundle/'package.json')
    if scene.digest(raw_manifest) != expected_manifest_sha:
        raise ValueError('Character manifest differs from trusted pin')
    package=scene.decoded(raw_manifest)
    if not isinstance(package,dict) or set(package) != {'schema','character_id','source_local_only','scene_manifest_sha256',
            'camera','viewport','files','source','presentation'}:
        raise ValueError('Unknown character package fields')
    if (package['schema'] != SCHEMA or package['character_id'] != 'map001_player' or package['source_local_only'] is not True or
            package['scene_manifest_sha256'] != expected_scene_sha or package['camera'] != [544,1536] or
            package['viewport'] != [320,224] or any(type(v) is not int for v in package['camera']+package['viewport'])):
        raise ValueError('Character package scene/identity differs from its verified profile')
    _presentation(package['presentation'])
    provenance=package['source']
    if (not isinstance(provenance,dict) or set(provenance) != {'seed_sha256','source_files','reference_art_manifest_sha256',
            'animation_validation_sha256','presentation_reports','capture_manifests','presentation_index_sha256',
            'foreground_manifest_sha256','props_manifest_sha256','draw_order_validation_sha256','map_v1n_sha256'} or provenance['seed_sha256'] != SEED_SHA or
            provenance['source_files'] != SOURCES):
        raise ValueError('Unknown character source identities')
    for key in ['reference_art_manifest_sha256','animation_validation_sha256','presentation_index_sha256',
                'foreground_manifest_sha256','props_manifest_sha256','draw_order_validation_sha256']:
        if not scene.valid_hash(provenance[key]): raise ValueError('Invalid source report identity')
    if provenance['map_v1n_sha256'] != graphics.MAP_V1N_SHA256: raise ValueError('Unknown prop texture source')
    reports=provenance['presentation_reports']
    manifests=provenance['capture_manifests']
    if (not isinstance(reports,dict) or set(reports) != set(ROUTES) or not all(scene.valid_hash(v) for v in reports.values()) or
            not isinstance(manifests,dict) or set(manifests) != {f'{r}-{n}' for r in ROUTES for n in 'abc'} or
            not all(scene.valid_hash(v) for v in manifests.values()) or len(set(manifests.values())) != 12):
        raise ValueError('Missing four presentation reports or twelve capture identities')
    records=package['files']
    if not isinstance(records,dict) or set(records) != PAYLOADS:
        raise ValueError('Character file names differ from the exact allowlist')
    payload={}
    for name in sorted(PAYLOADS):
        record=records[name]
        if (not isinstance(record,dict) or set(record) != {'bytes','sha256'} or type(record['bytes']) is not int or
                record['bytes'] <= 0 or not scene.valid_hash(record['sha256'])):
            raise ValueError('Invalid character payload identity')
        raw=stable_read(bundle/name)
        if len(raw) != record['bytes'] or scene.digest(raw) != record['sha256']:
            raise ValueError('Changed or truncated character payload: '+name)
        payload[name]=raw
    base=scene.load_profile(stable_read(scene_bundle/'profile.json'),stable_read(scene_bundle/'flags.bin'))
    profile=scene.decoded(payload['profile.json'])
    if not isinstance(profile,dict) or 'initial_state' not in profile:
        raise ValueError('Missing animation profile')
    model=animation.CharacterProfile(base,payload['animation-bank.bin'],payload['image-table.bin'],profile['initial_state'])
    if json.dumps(profile,sort_keys=True) != json.dumps(model.metadata(),sort_keys=True):
        raise ValueError('Unknown or altered animation profile')
    appearance=scene.decoded(payload['appearances.json'])
    if appearance != {'schema':APPEARANCE_SCHEMA,'character_id':'map001_player','frames':expected_frames()}:
        raise ValueError('Unknown character mapping, anchor, mirror or primary pose')
    # Avoid Python bool==int accepting altered raw metadata.
    if scene.encoded(appearance) != scene.encoded({'schema':APPEARANCE_SCHEMA,'character_id':'map001_player','frames':expected_frames()}):
        raise ValueError('Non-integral character mapping')
    layers=scene.decoded(payload['layers.json'])
    if (not isinstance(layers,dict) or set(layers) != {'schema','foreground','props','sorting','omitted_object_slots','shadow_omitted'} or
            layers['schema'] != LAYER_SCHEMA or scene.encoded(layers['props']) != scene.encoded(expected_props()) or
            scene.encoded(layers['sorting']) != scene.encoded(SORTING) or layers['omitted_object_slots'] != [6,7] or
            layers['shadow_omitted'] is not True):
        raise ValueError('Unknown source prop mapping, sorting or scene scope')
    foreground=layers['foreground']
    if (not isinstance(foreground,dict) or set(foreground) != {'file','dimensions','rule','rgba_sha256'} or
            foreground['file'] != 'nbg-priority-foreground.png' or foreground['dimensions'] != [320,224] or
            foreground['rule'] != FOREGROUND_RULE or not scene.valid_hash(foreground['rgba_sha256'])):
        raise ValueError('Unknown source foreground mapping')
    foreground_image=_png(payload['nbg-priority-foreground.png'],(320,224))
    if scene.digest(foreground_image.tobytes()) != foreground['rgba_sha256']:
        raise ValueError('Source foreground decoded pixels differ')
    for name in PNG_FILES: _png(payload[name])
    for prop in layers['props']: _png(payload[prop['file']],tuple(prop['dimensions']))
    exact_files(bundle)
    if stable_read(bundle/'package.json') != raw_manifest or any(stable_read(bundle/name) != raw for name,raw in payload.items()):
        raise ValueError('Character package changed during verification')
    return {'schema':'ao_pc_character_bundle_verification_v1','passed':True,'manifest_sha256':expected_manifest_sha,
            'scene_manifest_sha256':expected_scene_sha,'files':len(FILES),'original_frames':20,'source_local_only':True}


def _accepted_evidence(animation_raw: bytes, reports: dict[str,bytes]) -> dict:
    suite=scene.decoded(animation_raw)
    if (not isinstance(suite,dict) or suite.get('schema') != 'ao_pc_character_animation_suite_v1' or suite.get('passed') is not True or
            suite.get('updates_compared') != sum(COUNTS.values())*3 or suite.get('mismatched_updates') != 0):
        raise ValueError('Complete formal animation validation has not passed')
    captures={}
    for report in suite.get('captures',[]):
        name=Path(report['capture']).name
        if (name in captures or name not in {f'{r}-{n}' for r in ROUTES for n in 'abc'} or report.get('passed') is not True or
                report.get('source_bank_each_hook_verified') is not True or report.get('later_actor_state_injection') is not False or
                report.get('updates_compared') != COUNTS[name.rsplit('-',1)[0]] or report.get('mismatched_updates') != 0):
            raise ValueError('Invalid formal animation capture result')
        captures[name]=report['manifest_sha256']
        if scene.digest(stable_read(ROOT/'reports/character'/name/'manifest.json')) != captures[name]:
            raise ValueError('Capture manifest changed after animation validation')
    if len(captures) != 12: raise ValueError('Twelve formal animation captures are required')
    if set(reports) != set(ROUTES): raise ValueError('Four presentation reports are required')
    for route,raw in reports.items():
        report=scene.decoded(raw)
        if (report.get('schema') != 'ao_pc_character_presentation_v1' or
                report.get('capture_manifest_sha256') != captures[route+'-a'] or report.get('source_hashes') != SOURCES or
                report.get('frames') != COUNTS[route] or any(report.get(flag) is not True for flag in
                ['source_command_binding_passed','command_execution_verified','observed_delay_profile_passed',
                 'visible_composition_passed'])):
            raise ValueError('Source draw, timing or visible pixels have not passed: '+route)
        if {k:report.get('delay_profile',{}).get(k) for k in DELAY} != DELAY:
            raise ValueError('Unknown presentation delay profile')
        rows=report.get('presentation')
        if not isinstance(rows,list) or len(rows) != COUNTS[route]:
            raise ValueError('Incomplete source presentation frames')
        for frame,row in enumerate(rows,1):
            composition=row.get('composition',{})
            visible=row.get('visible',{})
            counts=composition.get('explained_pixels',{})
            if (row.get('video_frame') != frame or composition.get('passed') is not True or
                    composition.get('unexplained_pixels') != 0 or composition.get('differences') != [] or
                    visible.get('outside_viewport_pixels') != 0 or not isinstance(counts,dict) or not counts or
                    set(counts)-{'body','vdp1_prop','nbg_foreground'} or any(type(v) is not int or v<0 for v in counts.values()) or
                    sum(counts.values()) != visible.get('matching_opaque_pixels',0)+visible.get('mismatched_opaque_pixels',0)):
                raise ValueError('Unexplained or incomplete source composition frame')
        if report.get('counts',{}).get('unexplained_pixels') != 0:
            raise ValueError('Presentation mismatches remain unresolved')
    return captures


def build(output: Path=DEFAULT_OUT, pin_path: Path=DEFAULT_PIN, presentation_index: Path=PRESENTATION_INDEX) -> dict:
    output,pin_path=Path(output),Path(pin_path)
    if pin_path.resolve().is_relative_to(output.resolve()): raise ValueError('Character trust pin must be outside package')
    scene_pin=scene.decoded(stable_read(scene.DEFAULT_PIN))
    expected_scene=scene_pin['manifest_sha256']
    scene.verify(scene.DEFAULT_OUT,expected_scene)
    old=None
    if pin_path.exists():
        scene.no_redirect(pin_path)
        old=scene.decoded(stable_read(pin_path))
        if (not isinstance(old,dict) or set(old) != {'schema','manifest_sha256','scene_manifest_sha256'} or
                old['schema'] != PIN_SCHEMA or not scene.valid_hash(old['manifest_sha256']) or
                not scene.valid_hash(old['scene_manifest_sha256'])):
            raise ValueError('Existing pin file is not an approved character pin')
    if output.exists():
        if old is None: raise ValueError('Existing character package lacks a valid pin')
        verify(output,old['manifest_sha256'],scene.DEFAULT_OUT,expected_scene)
    elif output.is_symlink(): raise ValueError('Character output may not be a link')
    animation_raw=stable_read(ANIMATION_REPORT)
    index_raw=stable_read(presentation_index)
    index=scene.decoded(index_raw)
    if (not isinstance(index,dict) or set(index) != {'schema','passed','reports'} or
            index['schema'] != 'ao_pc_character_presentation_index_v1' or index['passed'] is not True or
            not isinstance(index['reports'],dict) or set(index['reports']) != set(ROUTES)):
        raise ValueError('Missing approved presentation index')
    presentation={}
    presentation_paths={}
    for route,record in index['reports'].items():
        if (not isinstance(record,dict) or set(record) != {'path','sha256','frames'} or
                not scene.valid_hash(record['sha256']) or type(record['frames']) is not int or record['frames'] != COUNTS[route]):
            raise ValueError('Invalid presentation report pin')
        path=Path(record['path'])
        scene.no_redirect(path)
        if not path.resolve().is_relative_to((ROOT/'reports/character').resolve()):
            raise ValueError('Presentation report outside original local evidence directory')
        raw=stable_read(path)
        if scene.digest(raw) != record['sha256']: raise ValueError('Presentation report changed after approval')
        presentation[route]=raw
        presentation_paths[route]=path
    captures=_accepted_evidence(animation_raw,presentation)
    foreground,foreground_png,foreground_manifest_sha=load_foreground(index_raw)
    props_payload,props_manifest_sha,order_sha=load_props(captures)
    art_raw=stable_read(ART/'manifest.json')
    art=scene.decoded(art_raw)
    if art.get('schema') != 'ao_pc_character_reference_art_v1' or art.get('character_id') != 'map001_player' or art.get('seed_sha256') != SEED_SHA:
        raise ValueError('Unknown source reference art')
    resource=graphics.PlayerResource(*(stable_read(ROOT.parent/'work/extract'/name) for name in SOURCES))
    low=stable_read(ROOT/'reports/character/cardinal-a/frame-000000/wram-low.bin')
    high=stable_read(ROOT/'reports/character/cardinal-a/frame-000000/wram-high.bin')
    profile=animation.profile_from_snapshot(high,low)
    if art['animation_profile'] != profile.metadata(): raise ValueError('Reference art uses a different animation profile')
    if {k:art['source_files'][k]['sha256'] for k in SOURCES} != SOURCES: raise ValueError('Reference art source mismatch')
    frames=expected_frames()
    payload={'profile.json':scene.encoded(profile.metadata()),'animation-bank.bin':profile.animation_bank,
             'image-table.bin':profile.image_table,
             'appearances.json':scene.encoded({'schema':APPEARANCE_SCHEMA,'character_id':'map001_player','frames':frames}),
             'nbg-priority-foreground.png':foreground_png,
             'layers.json':scene.encoded({'schema':LAYER_SCHEMA,'foreground':foreground,'props':expected_props(),
                 'sorting':SORTING,'omitted_object_slots':[6,7],'shadow_omitted':True}),**props_payload}
    if len(art['frames']) != 20: raise ValueError('Reference poses are incomplete')
    for expected,original in zip(frames,art['frames']):
        if {key:original.get(key) for key in expected} != expected:
            raise ValueError('Reference pose mapping differs from source profile')
        image_record=resource.image(expected['image_index'])
        if len(image_record['pieces']) != 1: raise ValueError('Unverified multi-piece character')
        piece=image_record['pieces'][0]
        texture=resource.textures[piece['texture_index']]
        if expected['anchor'] != [-v for v in piece['offset']] or expected['dimensions'] != [texture.width,texture.height]:
            raise ValueError('Source anchor or dimensions differ from package')
        raw=stable_read(ART/expected['file'])
        identity=art['files'][expected['file']]
        if identity != {'bytes':len(raw),'sha256':scene.digest(raw)}: raise ValueError('Reference PNG hash changed')
        png=_png(raw)
        colors=[]
        for index in texture.indices:
            color=int.from_bytes(resource.palette[index*2:index*2+2],'big')
            colors.append(tuple(((color>>shift)&31)<<3 for shift in (0,5,10))+(255,) if index else (0,0,0,0))
        decoded=Image.new('RGBA',(texture.width,texture.height)); decoded.putdata(colors)
        if expected['baked_mirror_x']: decoded=decoded.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if png.tobytes() != decoded.tobytes(): raise ValueError('Reference PNG pixels differ from decoded source')
        payload[expected['file']]=raw
    package={'schema':SCHEMA,'character_id':'map001_player','source_local_only':True,'scene_manifest_sha256':expected_scene,
        'camera':[544,1536],'viewport':[320,224], 'files':{n:{'bytes':len(b),'sha256':scene.digest(b)} for n,b in sorted(payload.items())},
        'source':{'seed_sha256':SEED_SHA,'source_files':SOURCES,'reference_art_manifest_sha256':scene.digest(art_raw),
            'animation_validation_sha256':scene.digest(animation_raw),'presentation_reports':{r:scene.digest(b) for r,b in presentation.items()},
            'capture_manifests':captures,'presentation_index_sha256':scene.digest(index_raw),
            'foreground_manifest_sha256':foreground_manifest_sha,'props_manifest_sha256':props_manifest_sha,
            'draw_order_validation_sha256':order_sha,'map_v1n_sha256':graphics.MAP_V1N_SHA256},
        'presentation':{'state':'source_draw_and_visibility_verified','delay_profile':DELAY,
            'scope':SCOPE}}
    manifest=scene.encoded(package); manifest_sha=scene.digest(manifest)
    if stable_read(ANIMATION_REPORT) != animation_raw or stable_read(ART/'manifest.json') != art_raw or stable_read(presentation_index) != index_raw or any(
            stable_read(presentation_paths[r]) != raw for r,raw in presentation.items()):
        raise ValueError('Character acceptance evidence changed before publication')
    if output.exists(): verify(output,scene.decoded(stable_read(pin_path))['manifest_sha256'],scene.DEFAULT_OUT,expected_scene)
    else: output.mkdir(parents=True)
    for name,raw in payload.items(): (output/name).write_bytes(raw)
    (output/'package.json').write_bytes(manifest)
    result=verify(output,manifest_sha,scene.DEFAULT_OUT,expected_scene)
    pin_path.parent.mkdir(parents=True,exist_ok=True)
    pin_path.write_bytes(scene.encoded({'schema':PIN_SCHEMA,'manifest_sha256':manifest_sha,'scene_manifest_sha256':expected_scene}))
    return result


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    make=commands.add_parser('build'); make.add_argument('--out',type=Path,default=DEFAULT_OUT); make.add_argument('--pin',type=Path,default=DEFAULT_PIN)
    make.add_argument('--presentation-index',type=Path,default=PRESENTATION_INDEX)
    check=commands.add_parser('verify'); check.add_argument('bundle',type=Path); check.add_argument('--manifest-sha256',required=True)
    check.add_argument('--scene',type=Path,default=scene.DEFAULT_OUT); check.add_argument('--scene-manifest-sha256',required=True)
    args=parser.parse_args()
    try:
        result=build(args.out,args.pin,args.presentation_index) if args.command=='build' else verify(args.bundle,args.manifest_sha256,args.scene,args.scene_manifest_sha256)
    except (OSError,ValueError,KeyError,TypeError) as exc: parser.exit(1,f'Character package rejected: {exc}\n')
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__=='__main__': raise SystemExit(main())
