"""Local-only, pinned multiview head geometry study; no gameplay/animation tests."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT.parent / 'tools/pc-remake'
SOURCE = TOOLS / 'hunyuan3d-2-source'
COMMIT = 'f8db63096c8282cb27354314d896feba5ba6ff8a'
MODEL = TOOLS / 'hunyuan-models/tencent/Hunyuan3D-2mv'
INPUT = ROOT / 'art/local/hunyuan-head-v1/inputs'

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while b := f.read(8 * 1024 * 1024): h.update(b)
    return h.hexdigest()

parser = argparse.ArgumentParser()
parser.add_argument('--seed', type=int, default=12345)
parser.add_argument('--resolution', type=int, default=380)
parser.add_argument('--steps', type=int, default=30)
parser.add_argument('--output', required=True)
parser.add_argument('--stream-weights', action='store_true')
parser.add_argument('--views', nargs='+', choices=['front','left','back','right'], default=['front','left','back','right'])
args = parser.parse_args()
out = Path(args.output).resolve()
out.relative_to(ROOT / 'art/local')
if out.exists(): raise RuntimeError('Preserve earlier generation attempts')
out.mkdir(parents=True)
assert subprocess.check_output(['git','-c',f'safe.directory={SOURCE.as_posix()}','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip() == COMMIT
lock = json.loads((MODEL / 'download-lock.json').read_bytes())
assert lock['revision'] == '3a761b539b29fe4ff64714813aa9560fd66f5de0'
for name, record in lock['files'].items():
    assert digest(MODEL/name) == record['sha256'], name
inputs = json.loads((INPUT / 'input-lock.json').read_bytes())
for name, record in inputs['references'].items():
    assert digest(INPUT/f'{name}.png') == record['prepared_sha256'], name
os.environ.update(HY3DGEN_MODELS=str(TOOLS/'hunyuan-models'),
    HF_HOME=str(TOOLS/'hunyuan-cache/huggingface'), HF_HUB_OFFLINE='1',
    TRANSFORMERS_OFFLINE='1', HY3DGEN_DEBUG='0')
sys.path.insert(0,str(SOURCE))
import torch
from PIL import Image
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
if not torch.cuda.is_available(): raise RuntimeError('CUDA required for this bounded asset generation')
print('Loading pinned local weights', flush=True)
if args.stream_weights:
    sys.path.insert(0,str(ROOT/'tools'))
    from hunyuan_stream_loader import load_pipeline
    pipeline = load_pipeline(MODEL)
else:
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        'tencent/Hunyuan3D-2mv', subfolder='hunyuan3d-dit-v2-mv',
        variant='fp16', use_safetensors=True, device='cuda')
views = {v: Image.open(INPUT/f'{v}.png').convert('RGBA') for v in args.views}
print('Generating one static head mesh from '+str(list(views)), flush=True)
mesh = pipeline(image=views, num_inference_steps=args.steps,
    octree_resolution=args.resolution, num_chunks=20000, mc_algo='mc',
    generator=torch.manual_seed(args.seed), output_type='trimesh')[0]
mesh.export(out/'raw-head.glb')
mesh.export(out/'raw-head.obj')
record = {'schema':'ao_local_head_geometry_pilot_v1', 'source_commit':COMMIT,
    'model_revision':lock['revision'], 'model_lock_sha256':digest(MODEL/'download-lock.json'),
    'input_lock_sha256':digest(INPUT/'input-lock.json'), 'seed':args.seed,
    'steps':args.steps,'octree_resolution':args.resolution,'views':list(views),
    'stream_weights':args.stream_weights,
    'vertices':len(mesh.vertices),'triangles':len(mesh.faces), 'bounds':mesh.bounds.tolist(),
    'torch':torch.__version__,'device':torch.cuda.get_device_name(),
    'animation_tested':False,'performance_tested':False,'reference_upload':False,
    'status':'raw generated geometry, not art approved',
    'files':{p.name:digest(p) for p in out.iterdir() if p.is_file()}}
(out/'generation.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record,indent=2),flush=True)
