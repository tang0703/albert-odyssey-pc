"""Create a self-contained review of actual Unity renders and lock its evidence."""
from pathlib import Path
import argparse, base64, hashlib, json, shutil
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'art/local/tripo-head-v1'
p=argparse.ArgumentParser()
p.add_argument('--capture',required=True)
p.add_argument('--prepared',default='prepared-01')
p.add_argument('--out',default='review-01')
a=p.parse_args()
capture=Path(a.capture).resolve()
out=BASE/a.out
out.mkdir(exist_ok=False)
record=json.loads((capture/'review.json').read_bytes())
assert record['engine']=='Unity URP' and record['captures']==36
assert record['clay_only'] and record['pilot_label']=='tripo'
assert not record['animation_tested'] and not record['performance_tested']
images={}; hashes={}
def add(key,path):
    raw=path.read_bytes()
    with Image.open(path) as im:
        im.verify()
    images[key]='data:image/png;base64,'+base64.b64encode(raw).decode('ascii')
    hashes[key]=hashlib.sha256(raw).hexdigest()
for f in capture.glob('*.png'):
    with Image.open(f) as im: assert im.size==(900,900)
    add(f.stem,f)
assert len(images)==36
for d in ('front','left','back','right'):
    add('concept-'+d,ROOT/f'art/local/hunyuan-head-v1/inputs/{d}.png')
for n in range(1,7):
    add('wire-'+str(n),ROOT/f'art/local/face-revision-v1/references/user-20261101/reference-{n:02}.png')
for version in ('previous','tripo'):
    for light in ('neutral','warm'):
        for direction in ('front','left','back','right','threequarter'):
            assert f'{version}-clay-{light}-{direction}' in images
            if direction!='back': assert f'{version}-clay-{light}-{direction}-face' in images
page='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tripo 頭部樣本 01｜Unity 實際對照</title><style>
*{box-sizing:border-box}body{margin:0;background:#101b1f;color:#e9e4db;font:17px/1.65 system-ui,"Microsoft JhengHei",sans-serif}main{max-width:1600px;margin:auto;padding:32px 24px 70px}h1{font-size:32px;color:#edc58b}.note{padding:16px 20px;background:#203137;border-left:4px solid #d2a76c}button{font:inherit;padding:9px 16px;margin:4px;border-radius:8px;border:1px solid #65777a;background:#22363c;color:inherit;cursor:pointer}button[aria-pressed=true]{background:#d2a76c;color:#102024}.controls{margin:15px 0}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.card{margin:0;background:#18292f;border:1px solid #385057;border-radius:12px;overflow:hidden}.card img{display:block;width:100%;aspect-ratio:1;object-fit:contain;background:#1b262b}.card figcaption{padding:10px 16px}.small{color:#b1c1c5;font-size:15px}.error{color:#ff978b}details{margin:25px 0}a{color:#edc58b}@media(max-width:850px){.cards{grid-template-columns:1fr}main{padding:20px 12px}}</style>
<main><p class="small">MAP001 / SINGLE TRIPO GENERATION / UNITY URP</p><h1>頭臉與髮型：Tripo 首次樣本</h1>
<p class="note"><strong>靜態造型樣本，尚未核准。</strong>中、右欄均為 Unity 實際渲染，使用相同正交鏡頭、材質與光線。僅調整匯入方向、展示比例與平滑著色，沒有後製修改模型輪廓。無貼圖，因此眼睛虹膜與服裝顏色尚不存在。未替換遊戲人物、未製作動畫、未進行效能測試。</p>
<div class="controls" id="directions"></div><div class="controls" id="lights"></div><div class="controls" id="crops"></div>
<div class="cards"><figure class="card"><img id="concept" alt="原概念頭部"><figcaption>原概念｜圖片參考</figcaption></figure><figure class="card"><img id="previous" alt="前次 Hunyuan 頭部 Unity 畫面"><figcaption>前次 Hunyuan refined-02｜Unity</figcaption></figure><figure class="card"><img id="tripo" alt="Tripo 頭部 Unity 畫面"><figcaption>本次 Tripo 原始形體｜Unity</figcaption></figure></div>
<p class="small" id="angle"></p><p class="error" id="error"></p>
<p>概念圖片不是校準掃描；側面俯角及透視與 Unity 鏡頭不同。模型以含頸部／圍巾的外接高度歸一展示，不作精確頭身比量測。暖光也是同一組檢查照明，並非遊戲房間整合驗收。</p>
<h2>本次範圍</h2><p>只生成一個 H3.1 高精細無貼圖模型（v3.1-20260211）；原始 GLB、任務紀錄、可編輯 Blender 與 FBX 均留在本地。沒有自動重抽、貼圖、綁骨或額外付費轉檔。新造型未核准前不接入正式玩家。</p>
<h2>審閱重點</h2><p>請比較臉頰到下巴的輪廓、鼻口的側面突出量、眼窩與眼瞼、額頭及頭帶銜接、瀏海與側後髮束、羽飾數量與根部。這是生成的靜態網格，不能視為可直接蒙皮的最終拓樸。</p>
<details><summary>您提供的六張線框形體參考</summary><p>本次直接生成使用四張彩色概念頭部圖。這六張圖作形體審閱參考，未混入本次生成；只有圖片，未收到原始模型，也未聲稱恢復圖中的布線。</p><div class="cards" id="wires"></div></details>
<p class="small">全部圖片嵌入本頁，可離線開啟。詳細費用、來源雜湊與檢查結果另存同目錄 report.json。</p></main>
<script>const images=IMAGES;let direction='front',light='neutral',close=false;
function group(id,items,value,set){const box=document.getElementById(id);box.innerHTML='';for(const [v,label] of items){const b=document.createElement('button');b.textContent=label;b.setAttribute('aria-pressed',String(v===value));b.onclick=()=>{set(v);render()};box.appendChild(b)}}
function render(){group('directions',[['front','正面'],['left','面向左'],['back','背面'],['right','面向右'],['threequarter','斜側面']],direction,v=>direction=v);group('lights',[['neutral','中性光'],['warm','暖光']],light,v=>light=v);group('crops',[[false,'完整頭部'],[true,'頭臉近景']],close,v=>close=v);
const suffix=close&&direction!=='back'?'-face':'';document.getElementById('concept').src=images['concept-'+(direction==='threequarter'?'front':direction)];for(const v of ['previous','tripo'])document.getElementById(v).src=images[v+'-clay-'+light+'-'+direction+suffix];document.getElementById('angle').textContent=direction==='back'&&close?'背面保留完整頭部；近景用於臉部。':direction==='threequarter'?'沒有同角度斜側概念，左欄保留正面參考。':'概念維持完整裁圖；Unity 新舊模型使用同一鏡頭。';}
for(let n=1;n<=6;n++){const f=document.createElement('figure');f.className='card';const im=document.createElement('img');im.src=images['wire-'+n];im.alt='使用者形體參考 '+n;f.appendChild(im);document.getElementById('wires').appendChild(f)}document.querySelectorAll('img').forEach(im=>im.onerror=()=>document.getElementById('error').textContent='圖片載入失敗，請保留這項錯誤。');render();</script></html>'''
(out/'review.html').write_text(page.replace('IMAGES',json.dumps(images,separators=(',',':'))),encoding='utf-8')
shutil.copytree(capture,out/'unity')
manifest={'schema':'ao_tripo_head_static_review_v1','capture':str(capture),'prepared':a.prepared,
    'unity_images':36,'embedded_images':len(images),'art_approved':False,
    'animation_tested':False,'performance_tested':False,'gameplay_changed':False,
    'html_sha256':hashlib.sha256((out/'review.html').read_bytes()).hexdigest(),'images':hashes}
(out/'review-lock.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(out/'review.html')
