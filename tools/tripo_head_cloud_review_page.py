"""Embed unretouched Unity captures and concept references in an offline review."""
from pathlib import Path
import argparse,base64,hashlib,json,shutil
from PIL import Image

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/tripo-head-v1'
p=argparse.ArgumentParser();p.add_argument('--capture',required=True);p.add_argument('--out',default='review-cloud-texture-01')
a=p.parse_args();capture=Path(a.capture);out=BASE/a.out;out.mkdir(exist_ok=False)
record=json.loads((capture/'review.json').read_bytes())
assert record['engine']=='Unity URP' and record['cloud_texture_review'] and record['captures']==80
assert not record['animation_tested'] and not record['performance_tested'] and not record['gameplay_changed']
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
images={};hashes={}
for file in capture.glob('*.png'):
    with Image.open(file) as im:assert im.size==(900,900);im.verify()
    images[file.stem]='data:image/png;base64,'+base64.b64encode(file.read_bytes()).decode();hashes[file.stem]=sha(file)
assert len(images)==80
for side in ('front','left','back','right'):
    file=ROOT/f'art/local/hunyuan-head-v1/inputs/{side}.png'
    images['concept-'+side]='data:image/png;base64,'+base64.b64encode(file.read_bytes()).decode();hashes['concept-'+side]=sha(file)
page='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:,"><title>Tripo 頭部上色｜Unity 實際畫面審閱</title><style>
*{box-sizing:border-box}body{margin:0;background:#111b20;color:#e9e4dc;font:17px/1.65 system-ui,"Microsoft JhengHei",sans-serif}main{max-width:1800px;margin:auto;padding:28px 24px 64px}h1{font-size:32px;color:#edc58b;margin:10px 0}.eyebrow,.small{color:#a6b6bd;font-size:14px}.note{padding:15px 20px;background:#203137;border-left:4px solid #d2a76c}button{font:inherit;padding:8px 14px;margin:4px;border:1px solid #586f76;border-radius:7px;background:#24363e;color:inherit;cursor:pointer}button[aria-pressed=true]{background:#d2a76c;color:#152027}.controls{margin:10px 0}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}figure{margin:0;border:1px solid #38515a;border-radius:10px;overflow:hidden;background:#19282e}figure img{display:block;width:100%;aspect-ratio:1;object-fit:contain;background:#101b20;cursor:zoom-in}figcaption{padding:10px 14px}#error{color:#ff9c8e}details{margin:25px 0}dialog{border:1px solid #72858c;background:#122128;color:#eee;max-width:95vw;max-height:95vh;padding:12px}dialog img{display:block;max-width:90vw;max-height:80vh}dialog::backdrop{background:#000b}@media(max-width:850px){.cards{grid-template-columns:1fr}main{padding:16px 10px}h1{font-size:25px}}
</style><main><p class="eyebrow">MAP001 · HEAD-ONLY TEXTURE REVIEW · UNITY URP</p>
<h1>Tripo 頭部上色｜實際 Unity 對照</h1>
<p class="note"><strong>僅供頭部審閱，尚未人物定稿。</strong>保留既有頭部與平滑眼球，使用四方向概念圖進行一次 Tripo HD／PBR 上色。此頁全部模型畫面來自 Unity，沒有後製修形或重畫。</p>
<div class="controls" id="directions"></div><div class="controls" id="lights"></div><div class="controls" id="crops"></div><div class="controls" id="modes"></div>
<div class="cards"><figure><img id="concept" alt="原概念圖片參考" tabindex="0"><figcaption>原概念｜圖片參考</figcaption></figure>
<figure><img id="local" alt="之前本地製作頭部 Unity 畫面" tabindex="0"><figcaption id="local-label"></figcaption></figure>
<figure><img id="cloud" alt="Tripo 上色頭部 Unity 畫面" tabindex="0"><figcaption id="cloud-label"></figcaption></figure></div>
<p id="angle" class="small"></p><p class="small">點擊圖片可放大。新舊採相同展示高度、正交鏡頭與照明。展示範圍含頸部／圍巾，不代表已完成身體比例整合。45° 畫面僅檢查頭部辨識度，尚非房間驗收。</p><p id="error" role="alert"></p>
<details open><summary>本次費用與素材紀錄</summary><p>僅執行一次 texture_model：<strong>20 點（US$0.20）</strong>；完成後餘額 440 點，凍結 0 點。沒有重新生成、追加幾何、綁定或動畫任務。</p><p class="small">任務：39e6ab01-c274-49e6-9043-d4dcd81144c1<br>貼圖版本 v3.0-20250812；頭部主貼圖 4096×4096，兩眼各 128×128。HD 不代表每個材質都是 4K。</p></details>
<details open><summary>幾何保留與審閱限制</summary><p>Tripo 將原模型垂直移動 −0.5 單位。此版移回原位置後，位置最大誤差約 1.49×10⁻⁸，三角面及 UV 對照相同。雲端重算了部分頂點法線，因此不能聲稱法線不變；原始 GLB、本地精修檔與舊審閱頁均保留。</p><p>請核對雙眼視線、棕髮色調、髮根／眼瞼／頭帶／羽飾交界與圍巾。Tripo 配色仍可能有串色、風格化明暗或對參考的不同詮釋；沒有把建置成功當成美術核准。全身、最終拓樸、骨架及遊戲整合尚未完成。</p></details>
<p class="note">本輪沒有動畫、負載、長循環、效能基準或實際 GPU FPS 測試；未替換遊戲玩家。</p>
<p class="small">cloud-ready-01 · 80 張 Unity 畫面＋4 張概念參考 · 圖片自包含，可離線開啟。</p></main>
<dialog id="zoom"><button id="close-zoom">關閉放大</button><img id="zoom-image" alt="放大畫面"></dialog>
<script>const images=IMAGES;let direction='front',light='neutral',close=false,mode='palette';
function group(id,items,value,set){const box=document.getElementById(id);box.innerHTML='';for(const [v,label]of items){const b=document.createElement('button');b.textContent=label;b.setAttribute('aria-pressed',String(v===value));b.onclick=()=>{set(v);render()};box.appendChild(b)}}
function render(){group('directions',[['front','正面'],['left','面向左'],['back','背面'],['right','面向右'],['threequarter','斜側面'],['top45','45° 俯視']],direction,v=>direction=v);group('lights',[['neutral','中性光'],['warm','暖光']],light,v=>light=v);group('crops',[[false,'完整頭部'],[true,'頭臉近景']],close,v=>close=v);group('modes',[['palette','上色對照'],['clay','灰模對照']],mode,v=>mode=v);
const suffix=close&&!['back','top45'].includes(direction)?'-face':'';document.getElementById('concept').src=images['concept-'+(['threequarter','top45'].includes(direction)?'front':direction)];for(const id of ['local','cloud'])document.getElementById(id).src=images[id+'-'+mode+'-'+light+'-'+direction+suffix];document.getElementById('local-label').textContent='本地前版｜'+(mode==='clay'?'灰模':'基礎上色');document.getElementById('cloud-label').textContent='Tripo 新版｜'+(mode==='clay'?'灰模':'PBR 上色');document.getElementById('angle').textContent=['threequarter','top45'].includes(direction)?'沒有同角度概念圖，左欄保留正面參考。':direction==='back'&&close?'背面保留完整頭部。':'概念圖片與 Unity 鏡頭透視不同，請以造型及配色對照。';}
const dialog=document.getElementById('zoom');for(const id of ['concept','local','cloud']){const im=document.getElementById(id);im.onerror=()=>document.getElementById('error').textContent='圖片載入失敗，請保留此錯誤。';im.onclick=()=>{document.getElementById('zoom-image').src=im.src;dialog.showModal()};im.onkeydown=e=>{if(e.key==='Enter')im.click()};}document.getElementById('close-zoom').onclick=()=>dialog.close();render();</script></html>'''
page=page.replace('IMAGES',json.dumps(images,separators=(',',':')))
(out/'review.html').write_text(page,encoding='utf-8');shutil.copytree(capture,out/'unity')
manifest={'schema':'ao_head_cloud_texture_review_v1','capture':str(capture),'unity_images':80,'embedded_images':84,
 'html_sha256':sha(out/'review.html'),'image_hashes':hashes,'task_id':'39e6ab01-c274-49e6-9043-d4dcd81144c1',
 'credits_billed':20,'balance_after':440,'art_approved':False,'animation_tested':False,'performance_tested':False}
(out/'review-lock.json').write_text(json.dumps(manifest,indent=2)+'\n');print(out/'review.html')
