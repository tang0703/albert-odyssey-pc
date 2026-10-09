"""Separate, source-bound HD appearance package. Drafts never satisfy this contract."""
from __future__ import annotations
import argparse
import io
import math
import uuid
from pathlib import Path
from PIL import Image
import character_bundle as source
import exploration_bundle as scene
from exploration_capture import stable_read

ROOT=Path(__file__).resolve().parents[1]
SCHEMA='ao_pc_character_hd_bundle_v1'
PIN_SCHEMA='ao_pc_character_hd_bundle_pin_v1'
APPEARANCE_SCHEMA='ao_pc_character_hd_appearances_v1'
DEFAULT_OUT=ROOT/'exploration-demo/generated/character-hd'
DEFAULT_PIN=ROOT/'exploration-demo/character-hd-pin.json'
DIRECTIONS=('down','left','right','up')
DRAFTS={'down':'69f0b62b922970de1ed6858d5bb02a97155ea2bc58d580da8b9b783151ab8c32',
 'left':'0a8b2a8ba87d308e0d7a6eaa7e01a8f7dce7e6294574badc0c6eca4642ace2d5',
 'right':'e50459c5657b069f85ca074c7da20efd3c274284f9c98243b49fb13031a46b3c',
 'up':'0d9808ae52ad55b1c5dfa1a2c78f0433d2ecb3141a43898f7ddc34890fdd3373'}
TIMING={'cycle_updates':40,'primary_updates':10,'subframes_per_primary':3,
 'primary_walk_indices':[0,3,6,9],'phase_formula':'floor((source_timer + render_phase) * 3 / 10)',
 'render_phase_interval':'[0,1)','idle_uses_source_state':True,'writes_movement':False}
PNG_FILES={f'{d}-{s}.png' for d in DIRECTIONS for s in [*[f'walk-{i:02d}' for i in range(12)],'idle']}
ATLAS_FILES={f'{d}-atlas.png' for d in DIRECTIONS}
PAYLOADS=PNG_FILES|ATLAS_FILES|{'appearances.json'}
FILES=PAYLOADS|{'package.json'}

def expected_frames() -> list[dict]:
    result=[]
    for d in DIRECTIONS:
        for cell in range(13):
            walk=cell if cell<12 else -1
            suffix=f'walk-{walk:02d}' if walk>=0 else 'idle'
            sub=walk%3 if walk>=0 else -1
            primary=walk//3 if walk>=0 else None
            result.append({'id':f'map001_player_hd/{d}/{suffix}','direction':d,'action':'walk' if walk>=0 else 'idle',
             'kind':'idle' if walk<0 else ('primary' if sub==0 else 'transition'),'walk_index':walk,
             'primary_source_index':primary,'next_primary_source_index':(primary+1)%4 if sub>0 else None,
             'transition_fraction':{'numerator':sub,'denominator':3} if sub>0 else None,
             'file':f'{d}-{suffix}.png','atlas':f'{d}-atlas.png','cell':cell,
             'rect':[(cell%4)*512,(cell//4)*512,512,512],'dimensions':[512,512]})
    return result

def _point(value):
    return isinstance(value,list) and len(value)==2 and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=512 for v in value)

def validate_appearances(value) -> list[dict]:
    if not isinstance(value,dict) or set(value)!={'schema','character_id','timing','frames'} or value['schema']!=APPEARANCE_SCHEMA or value['character_id']!='map001_player_hd' or scene.encoded(value['timing'])!=scene.encoded(TIMING):
        raise ValueError('Unknown HD appearance/timing contract')
    rows=value['frames']; expected=expected_frames()
    if not isinstance(rows,list) or len(rows)!=52: raise ValueError('HD requires exactly 52 actual frames')
    for row,base in zip(rows,expected):
        if not isinstance(row,dict) or set(row)!=set(base)|{'ground_anchor','actor_anchor','display_scale'}:
            raise ValueError('HD frame metadata incomplete')
        if scene.encoded({k:row[k] for k in base})!=scene.encoded(base): raise ValueError('Unknown HD frame mapping or atlas geometry')
        if row['ground_anchor']!=[256,448] or not _point(row['ground_anchor']) or not _point(row['actor_anchor']):
            raise ValueError('HD ground and source actor anchors must be separate valid points')
        scale=row['display_scale']
        if type(scale) not in (float,int) or not math.isfinite(scale) or not 0.01<=scale<=0.25:
            raise ValueError('HD display scale must be finite, source-pixel units')
    return rows

def exact_files(folder: Path) -> None:
    folder=Path(folder); scene.no_redirect(folder)
    if not folder.is_dir() or {p.name for p in folder.iterdir()}!=FILES: raise ValueError('HD bundle requires exactly its 58 approved files')
    for p in folder.iterdir():
        scene.no_redirect(p)
        if not p.is_file() or p.resolve().parent!=folder.resolve(): raise ValueError('HD payload is not a direct regular file')

def png(raw: bytes, size: tuple[int,int]) -> Image.Image:
    with Image.open(io.BytesIO(raw)) as im:
        if im.format!='PNG' or im.mode!='RGBA' or im.size!=size: raise ValueError('HD PNG format or dimensions differ')
        im.verify()
    with Image.open(io.BytesIO(raw)) as im:
        im.load(); return im.copy()

def validate_payload(package: dict, payload: dict[str,bytes], scene_sha: str, source_sha: str) -> dict:
    keys={'schema','character_id','source_local_only','state','scene_manifest_sha256','source_character_manifest_sha256','source','files'}
    if not isinstance(package,dict) or set(package)!=keys or package['schema']!=SCHEMA or package['character_id']!='map001_player_hd' or package['source_local_only'] is not True or package['state']!='approved_52_frames':
        raise ValueError('Unknown, draft or incomplete HD package')
    if package['scene_manifest_sha256']!=scene_sha or package['source_character_manifest_sha256']!=source_sha:
        raise ValueError('HD package belongs to different scene/source character')
    provenance=package['source']
    if not isinstance(provenance,dict) or set(provenance)!={'art_manifest_sha256','draft_approval_record_sha256','approved_drafts','art_review_status'} or provenance['approved_drafts']!=DRAFTS or provenance['art_review_status']!='approved' or not all(scene.valid_hash(provenance[k]) for k in ('art_manifest_sha256','draft_approval_record_sha256')):
        raise ValueError('HD final-art acceptance or approved draft binding is missing')
    if not isinstance(package['files'],dict) or set(package['files'])!=PAYLOADS or set(payload)!=PAYLOADS: raise ValueError('Unexpected HD files')
    for name,raw in payload.items():
        rec=package['files'][name]
        if not isinstance(rec,dict) or set(rec)!={'bytes','sha256'} or type(rec['bytes']) is not int or rec['bytes']<=0 or not scene.valid_hash(rec['sha256']) or rec['bytes']!=len(raw) or rec['sha256']!=scene.digest(raw):
            raise ValueError('HD payload changed or truncated: '+name)
    rows=validate_appearances(scene.decoded(payload['appearances.json']))
    atlases={d:png(payload[f'{d}-atlas.png'],(2048,2048)) for d in DIRECTIONS}
    pixels={d:set() for d in DIRECTIONS}
    for row in rows:
        frame=png(payload[row['file']],(512,512))
        alpha=frame.getchannel('A')
        if alpha.getextrema()[0]!=0 or alpha.getextrema()[1]<128 or alpha.point(lambda a:255 if a>=128 else 0).getbbox() is None:
            raise ValueError('HD frame needs a nonempty body and transparent background')
        raw_pixels=frame.tobytes(); identity=scene.digest(raw_pixels)
        if identity in pixels[row['direction']]: raise ValueError('Repeated still frame cannot stand in for a walk/transition pose')
        pixels[row['direction']].add(identity)
        x,y,w,h=row['rect']
        if atlases[row['direction']].crop((x,y,x+w,y+h)).tobytes()!=raw_pixels: raise ValueError('HD atlas cell differs from its exact frame pixels')
    for atlas in atlases.values():
        for cell in range(13,16):
            x,y=(cell%4)*512,(cell//4)*512
            if any(atlas.crop((x,y,x+512,y+512)).tobytes()): raise ValueError('Unused atlas cells must be zero RGBA')
    return {'passed':True,'frame_count':52,'atlas_count':4,'files':58,'source_local_only':True}

def verify(bundle: Path, expected_manifest_sha: str, scene_bundle: Path=scene.DEFAULT_OUT,
           expected_scene_sha: str|None=None, source_character_bundle: Path=source.DEFAULT_OUT,
           expected_source_character_sha: str|None=None) -> dict:
    if not all(scene.valid_hash(v) for v in [expected_manifest_sha,expected_scene_sha,expected_source_character_sha]): raise ValueError('Trusted HD, scene and source-character manifest hashes are required')
    source.verify(source_character_bundle,expected_source_character_sha,scene_bundle,expected_scene_sha)
    bundle=Path(bundle); exact_files(bundle)
    raw=stable_read(bundle/'package.json')
    if scene.digest(raw)!=expected_manifest_sha: raise ValueError('HD manifest differs from trusted pin')
    payload={name:stable_read(bundle/name) for name in PAYLOADS}
    result=validate_payload(scene.decoded(raw),payload,expected_scene_sha,expected_source_character_sha)
    exact_files(bundle)
    if raw!=stable_read(bundle/'package.json') or any(b!=stable_read(bundle/n) for n,b in payload.items()): raise ValueError('HD package changed during verification')
    return {'schema':'ao_pc_character_hd_verification_v1',**result,'manifest_sha256':expected_manifest_sha,
      'scene_manifest_sha256':expected_scene_sha,'source_character_manifest_sha256':expected_source_character_sha}

def _art_file(folder: Path, name: str) -> bytes:
    if not isinstance(name,str) or '\\' in name or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('A4 file path escapes art directory')
    path=folder/name
    if not path.resolve().is_relative_to(folder.resolve()): raise ValueError('A4 path escape')
    for entry in (path,*path.parents):
        scene.no_redirect(entry)
        if entry==folder: break
    return stable_read(path)

def _bound_sources(art: dict) -> tuple[str,str,dict[Path,bytes]]:
    """Pin art to its reviewed sources; never rebind anchors to newer packages."""
    snapshots={}
    for path in (scene.DEFAULT_PIN,source.DEFAULT_PIN):
        scene.no_redirect(path)
        snapshots[path]=stable_read(path)
    scene_pin=scene.decoded(snapshots[scene.DEFAULT_PIN])
    source_pin=scene.decoded(snapshots[source.DEFAULT_PIN])
    scene_sha=scene_pin.get('manifest_sha256'); source_sha=source_pin.get('manifest_sha256')
    if (scene_pin.get('schema')!='ao_pc_exploration_bundle_pin_v1' or
        source_pin.get('schema')!='ao_pc_character_bundle_pin_v1' or
        not all(scene.valid_hash(v) for v in (scene_sha,source_sha)) or
        source_pin.get('scene_manifest_sha256')!=scene_sha or
        art.get('scene_manifest_sha256')!=scene_sha or
        art.get('source_character_manifest_sha256')!=source_sha):
        raise ValueError('Reviewed A4 scene/source bindings differ from current trusted pins')
    return scene_sha,source_sha,snapshots

def _unchanged_pins(snapshots: dict[Path,bytes]) -> None:
    for path,raw in snapshots.items():
        scene.no_redirect(path)
        if stable_read(path)!=raw: raise ValueError('Scene/source pin changed during HD build')

def _publish(output: Path, pin_path: Path, payload: dict[str,bytes], manifest: bytes,
             scene_sha: str, source_sha: str, snapshots: dict[Path,bytes]) -> dict:
    """Fresh staged publication or exact idempotence; never replace an old package."""
    identity=scene.digest(manifest)
    files={**payload,'package.json':manifest}
    pin=scene.encoded({'schema':PIN_SCHEMA,'manifest_sha256':identity,
        'scene_manifest_sha256':scene_sha,'source_character_manifest_sha256':source_sha})
    if pin_path.resolve().is_relative_to(output.resolve()): raise ValueError('HD pin must live outside external package')
    _unchanged_pins(snapshots)
    if output.exists():
        exact_files(output)
        scene.no_redirect(pin_path)
        if not pin_path.is_file() or stable_read(pin_path)!=pin or any(stable_read(output/n)!=b for n,b in files.items()):
            raise ValueError('Existing HD output differs; choose a new output and pin, prior package was preserved')
        result=verify(output,identity,scene.DEFAULT_OUT,scene_sha,source.DEFAULT_OUT,source_sha)
        _unchanged_pins(snapshots)
        return result
    if pin_path.exists(): raise ValueError('Existing HD pin without output; refusing to replace it')
    output.parent.mkdir(parents=True,exist_ok=True); scene.no_redirect(output.parent)
    pin_path.parent.mkdir(parents=True,exist_ok=True); scene.no_redirect(pin_path.parent)
    staging=output.parent/(output.name+'.staging-'+uuid.uuid4().hex)
    staging.mkdir(); scene.no_redirect(staging)
    for name,data in files.items(): (staging/name).write_bytes(data)
    result=verify(staging,identity,scene.DEFAULT_OUT,scene_sha,source.DEFAULT_OUT,source_sha)
    _unchanged_pins(snapshots)
    if output.exists() or pin_path.exists(): raise ValueError('HD publication target appeared during build; staging preserved')
    # On Windows these same-volume renames refuse an existing destination.
    staging.rename(output)
    _unchanged_pins(snapshots)
    temporary_pin=pin_path.parent/(pin_path.name+'.staging-'+uuid.uuid4().hex)
    temporary_pin.write_bytes(pin)
    if pin_path.exists(): raise ValueError('HD pin appeared during publication; existing pin preserved')
    temporary_pin.rename(pin_path)
    _unchanged_pins(snapshots)
    return result

def build(art_manifest: Path, expected_art_sha: str, output: Path=DEFAULT_OUT, pin_path: Path=DEFAULT_PIN) -> dict:
    if not scene.valid_hash(expected_art_sha): raise ValueError('Final approved A4 manifest hash must be explicitly provided')
    art_manifest,output,pin_path=map(Path,(art_manifest,output,pin_path))
    scene.no_redirect(art_manifest)
    raw=stable_read(art_manifest)
    if scene.digest(raw)!=expected_art_sha: raise ValueError('A4 manifest changed after approval')
    art=scene.decoded(raw)
    if art.get('schema')!='ao_character_hd_art_v1' or art.get('review_status')!='approved': raise ValueError('Actual 52-frame art has not passed A4 review')
    import character_hd_art as art_contract
    art_check=art_contract.verify(art_manifest.parent,require_review=True)
    if art_check.get('manifest_sha256')!=expected_art_sha or scene.encoded(art.get('phase_contract'))!=scene.encoded(art_contract.PHASE):
        raise ValueError('A4 full art/animation review does not bind this exact source manifest')
    approval=art.get('draft_approval',{})
    if approval.get('status')!='approved' or approval.get('reference_sha256')!=DRAFTS or not scene.valid_hash(approval.get('approval_record_sha256')):
        raise ValueError('A4 is not bound to the approved four-direction design')
    scene_sha,source_sha,pin_snapshots=_bound_sources(art)
    source.verify(source.DEFAULT_OUT,source_sha,scene.DEFAULT_OUT,scene_sha)
    _unchanged_pins(pin_snapshots)
    payload={}; rows=[]
    originals=art.get('frames',[])
    if not isinstance(originals,list) or len(originals)!=52: raise ValueError('A4 has not supplied 52 individual actual frames')
    keyed={r.get('id'):r for r in originals if isinstance(r,dict)}
    if len(keyed)!=52: raise ValueError('Duplicate/missing A4 frame IDs')
    for base in expected_frames():
        row=keyed.get(base['id'],{})
        for field in ('direction','action','kind','walk_index','primary_source_index','next_primary_source_index','transition_fraction','cell','rect'):
            if scene.encoded(row.get(field))!=scene.encoded(base[field]): raise ValueError('A4 pose-to-atlas mapping differs: '+field)
        frame_raw=_art_file(art_manifest.parent,row.get('file'))
        frame=png(frame_raw,(512,512))
        if row.get('bytes')!=len(frame_raw) or row.get('sha256')!=scene.digest(frame_raw) or row.get('rgba_sha256')!=scene.digest(frame.tobytes()): raise ValueError('A4 frame bytes/pixels differ')
        payload[base['file']]=frame_raw
        rows.append({**base,**{k:row.get(k) for k in ('ground_anchor','actor_anchor','display_scale')}})
    atlases=art.get('atlases',[])
    if not isinstance(atlases,list) or len(atlases)!=4: raise ValueError('A4 needs four actual 2048 atlases')
    for d in DIRECTIONS:
        filename=f'atlases/{d}.png'
        matches=[row for row in atlases if row.get('file')==filename]
        if len(matches)!=1: raise ValueError('A4 direction atlas missing or duplicated')
        row=matches[0]; atlas_raw=_art_file(art_manifest.parent,filename); image=png(atlas_raw,(2048,2048))
        if row.get('bytes')!=len(atlas_raw) or row.get('sha256')!=scene.digest(atlas_raw) or row.get('rgba_sha256')!=scene.digest(image.tobytes()): raise ValueError('A4 atlas bytes/pixels differ')
        payload[f'{d}-atlas.png']=atlas_raw
    payload['appearances.json']=scene.encoded({'schema':APPEARANCE_SCHEMA,'character_id':'map001_player_hd','timing':TIMING,'frames':rows})
    package={'schema':SCHEMA,'character_id':'map001_player_hd','source_local_only':True,'state':'approved_52_frames',
      'scene_manifest_sha256':scene_sha,'source_character_manifest_sha256':source_sha,
      'source':{'art_manifest_sha256':expected_art_sha,'draft_approval_record_sha256':approval['approval_record_sha256'],'approved_drafts':DRAFTS,'art_review_status':'approved'},
      'files':{n:{'bytes':len(b),'sha256':scene.digest(b)} for n,b in sorted(payload.items())}}
    validate_payload(package,payload,scene_sha,source_sha)
    if stable_read(art_manifest)!=raw: raise ValueError('A4 approval changed during build')
    return _publish(output,pin_path,payload,scene.encoded(package),scene_sha,source_sha,pin_snapshots)

def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build'); b.add_argument('--art-manifest',type=Path,required=True); b.add_argument('--art-sha256',required=True); b.add_argument('--out',type=Path,default=DEFAULT_OUT); b.add_argument('--pin',type=Path,default=DEFAULT_PIN)
    v=sub.add_parser('verify'); v.add_argument('folder',type=Path); v.add_argument('--manifest-sha256',required=True); v.add_argument('--scene',type=Path,default=scene.DEFAULT_OUT); v.add_argument('--scene-manifest-sha256',required=True); v.add_argument('--source-character',type=Path,default=source.DEFAULT_OUT); v.add_argument('--source-character-manifest-sha256',required=True)
    a=parser.parse_args()
    result=build(a.art_manifest,a.art_sha256,a.out,a.pin) if a.command=='build' else verify(a.folder,a.manifest_sha256,a.scene,a.scene_manifest_sha256,a.source_character,a.source_character_manifest_sha256)
    print(scene.encoded(result).decode())
if __name__=='__main__': main()
