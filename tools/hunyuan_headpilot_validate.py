"""Validate pilot provenance/display artifacts, never artistic or performance acceptance."""
from pathlib import Path
import base64, hashlib, io, json, re, subprocess, sys
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/hunyuan-head-v1'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
old=ROOT/'art/unity/player-refined-v2';oldlock=json.loads((old/'review-lock.json').read_bytes())
for name,info in oldlock['files'].items():assert sha(old/name)==info['sha256'],name
inputs=json.loads((BASE/'inputs/input-lock.json').read_bytes())
for name,info in inputs['references'].items():
    assert sha(BASE/f'inputs/{name}.png')==info['prepared_sha256']
    assert sha(ROOT/info['source'])==info['source_sha256']
art=BASE/'refined-02';assets=json.loads((art/'unity-inputs.json').read_bytes())
for name,expected in assets['files'].items():assert sha(art/name)==expected
build=ROOT/'build/unity-headpilot-7425703b3e1d430a80f0c47e55f20caa'
buildinfo=json.loads((build/'review-build.json').read_bytes());assert buildinfo['passed'] and buildinfo['inputs_sha256']==sha(art/'unity-inputs.json')
review=BASE/'review-02';lock=json.loads((review/'review-lock.json').read_bytes());assert not lock['art_approved'] and not lock['palette_accepted']
assert sha(review/'review.html')==lock['html_sha256']
for name,expected in lock['images'].items():
    path=review/'unity'/name;assert sha(path)==expected
    with Image.open(path) as image:assert image.size==(900,900);image.verify()
page=(review/'review.html').read_text(encoding='utf-8')
embedded=json.loads(re.search(r'const images=(\{.*?\});let direction=',page,re.S).group(1))
assert len(embedded)==48
for value in embedded.values():
    assert value.startswith('data:image/png;base64,')
    with Image.open(io.BytesIO(base64.b64decode(value.split(',',1)[1]))) as image:image.verify()
for version in ('v2','pilot'):
    for material in ('clay','palette'):
        for light in ('neutral','warm'):
            for direction in ('front','left','back','right','threequarter'):
                assert f'{version}-{material}-{light}-{direction}' in embedded
evidence=BASE/'evidence';evidence.mkdir(exist_ok=True)
tests=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_unity_source_baseline.py','-v'],cwd=ROOT,capture_output=True,text=True)
(evidence/'source-guard-tests.txt').write_text(tests.stdout+tests.stderr,encoding='utf-8')
assert tests.returncode==0,tests.stderr
logs={p.name:sha(p) for pattern in ('hunyuan-head-*.log','headpilot-*.log','hunyuan-*-install.log','hunyuan-shape-dependencies.log') for p in (ROOT/'reports/unity').glob(pattern)}
result={'schema':'ao_headpilot_artifact_validation_v1','artifact_integrity':'passed',
    'old_v2_files_verified':len(oldlock['files']),'approved_reference_images_verified':len(inputs['references']),
    'unity_png_verified':len(lock['images']),'embedded_png_verified':len(embedded),
    'review_html_sha256':sha(review/'review.html'),'selected_geometry':'refined-02',
    'selected_unity_build':str(build.relative_to(ROOT)),
    'editable_blend_sha256':sha(art/'head-refined.blend'),
    'head_fbx_sha256':sha(art/'head-palette.fbx'),
    'source_guard_tests':{'exit_code':tests.returncode,'tests_run':int(re.search(r'Ran (\d+) tests',tests.stderr).group(1)),'full_gameplay_regressions_rerun':False},
    'artistic_acceptance':'not passed; user direction review pending',
    'palette_acceptance':'failed; diagnostic only','refined_04':'rejected due local surface distortion',
    'gameplay_replaced':False,'animation_tested':False,'performance_tested':False,
    'browser_render_verified':False,'reference_upload':False,'retained_log_hashes':logs}
(evidence/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
(ROOT/'docs/character-headpilot-status.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='retained_log_hashes'},indent=2))
