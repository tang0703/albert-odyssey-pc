"""Local-only Unity candidate packaging with closed file lists and byte hashes."""
from pathlib import Path
import argparse,hashlib,json,shutil,zipfile,uuid,subprocess
from unity_u4_assets import verify,identity,ROOT,ART
NAME='MAP001-Unity-StartRoom-Candidate-Windows-x64'
ROOTS={'D3D12','MonoBleedingEdge','MAP001-Unity-StartRoom_Data','MAP001-Unity-StartRoom.exe','UnityCrashHandler64.exe','UnityPlayer.dll','u4-build.json'}
DEBUG='MAP001 Unity Start Room_BurstDebugInformation_DoNotShip'
def inventory(folder):
    result={}
    for p in sorted(folder.rglob('*')):
        if p.is_symlink():raise ValueError('Linked package content')
        if p.is_file():result[p.relative_to(folder).as_posix()]=identity(p)
    return result
def check(folder):
    report=json.loads((folder/'PACKAGE.json').read_bytes());actual=inventory(folder);actual.pop('PACKAGE.json')
    if actual!=report['files']:raise ValueError('Package extra/missing/changed files')
    return report
def package(build):
    build=build.resolve()
    if build.parent!=(ROOT/'build').resolve():raise ValueError('Build must be a direct workspace build child')
    report=json.loads((build/'u4-build.json').read_bytes());art=verify()
    if not report['passed'] or report['source_dirty']:raise ValueError('A clean, successful stamped build is required')
    if report['art_lock_sha256']!=identity(ART/'asset-lock.json')['sha256']:raise ValueError('Build art differs')
    names={p.name for p in build.iterdir()}
    if names-ROOTS-{DEBUG} or not ROOTS<=names:raise ValueError('Unapproved build root contents')
    stage=ROOT/'build'/('unity-candidate-'+uuid.uuid4().hex);stage.mkdir()
    for name in ROOTS:
        src=build/name
        if src.is_dir():shutil.copytree(src,stage/name)
        else:shutil.copy2(src,stage/name)
    sources=stage/'Editable-3D';sources.mkdir()
    for name in art['files']:
        dst=sources/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ART/name,dst)
    shutil.copy2(ART/'asset-lock.json',sources/'asset-lock.json')
    previews=ART/'previews'
    preview_lock=json.loads((ART/'preview-lock.json').read_bytes())
    if {p.name:identity(p)['sha256'] for p in previews.iterdir() if p.is_file()}!=preview_lock:raise ValueError('Changed preview content')
    shutil.copytree(previews,stage/'Animation-Previews')
    shutil.copy2(ART/'preview-lock.json',sources/'preview-lock.json')
    shutil.copy2(ART/'accepted.json',sources/'accepted.json')
    license_dir=stage/'Licenses';license_dir.mkdir()
    for source,name in [(ROOT/'art/unity/fonts/OFL.txt','Noto-OFL.txt'),(ROOT/'art/unity/fonts/source.json','Noto-source.json'),(ROOT/'unity-remake/Assets/TextMesh Pro/Fonts/LiberationSans - OFL.txt','LiberationSans-OFL.txt')]:
        if source.is_file():shutil.copy2(source,license_dir/name)
    for source,name in [(ROOT/'docs/UNITY_PLAY_GUIDE.md','操作說明.md'),(ROOT/'docs/UNITY_U5_ACCEPTANCE.md','功能驗收.md')]:shutil.copy2(source,stage/name)
    payload={'schema':'ao_unity_candidate_v1','source_commit':report['source_commit'],'build_report_sha256':identity(build/'u4-build.json')['sha256'],'local_only':True,'performance_tested':False,'files':inventory(stage)}
    (stage/'PACKAGE.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');check(stage)
    archive=ROOT/'build'/(NAME+'.zip')
    if archive.exists():raise ValueError('Candidate exists; preserve it and choose an explicit version')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in stage.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(stage).as_posix())
    extracted=ROOT/'build'/('unity-candidate-extracted-'+uuid.uuid4().hex);extracted.mkdir()
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
        for n in z.namelist():
            if not (extracted/n).resolve().is_relative_to(extracted.resolve()):raise ValueError('Unsafe archive path')
        z.extractall(extracted)
    check(extracted)
    result={'passed':True,'zip':str(archive),'zip_sha256':identity(archive)['sha256'],'files':len(payload['files'])+1,'source_commit':report['source_commit'],'extracted':str(extracted),'standalone_launch_tested':False,'performance_tested':False}
    (ROOT/'reports/unity/u5-package.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    (archive.with_suffix('.zip.sha256')).write_text(result['zip_sha256']+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps(result))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path);p.add_argument('--verify',type=Path);a=p.parse_args()
    if a.verify:print(json.dumps({'passed':True,'files':len(check(a.verify)['files'])}))
    elif a.build:package(a.build)
    else:p.error('Choose --build or --verify')
