"""Self-contained review of real Unity head color captures (no image retouching)."""
from pathlib import Path
import argparse,base64,hashlib,json,shutil
from PIL import Image

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/tripo-head-v1'
p=argparse.ArgumentParser();p.add_argument('--capture',required=True);p.add_argument('--art',required=True);p.add_argument('--out',required=True)
a=p.parse_args();capture=Path(a.capture);art=BASE/a.art;out=BASE/a.out;out.mkdir(exist_ok=False)
record=json.loads((capture/'review.json').read_bytes());assert record['engine']=='Unity URP' and record['eye_color_review'] and record['captures']==60
assert not record['animation_tested'] and not record['performance_tested'] and not record['gameplay_changed']
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
images={};hashes={}
for file in capture.glob('*.png'):
    with Image.open(file) as im:assert im.size==(900,900);im.verify()
    images[file.stem]='data:image/png;base64,'+base64.b64encode(file.read_bytes()).decode();hashes[file.stem]=sha(file)
assert len(images)==60
for side in ('front','left','back','right'):
    file=ROOT/f'art/local/hunyuan-head-v1/inputs/{side}.png'
    images['concept-'+side]='data:image/png;base64,'+base64.b64encode(file.read_bytes()).decode();hashes['concept-'+side]=sha(file)
for version in ('previous-clay','eye-color-clay','eye-color-palette'):
    for light in ('neutral','warm'):
        for direction in ('front','left','back','right','threequarter','top45'):
            assert f'{version}-{light}-{direction}' in images
            if direction not in ('back','top45'):assert f'{version}-{light}-{direction}-face' in images
geometry=json.loads((art/'geometry-report.json').read_bytes())
page='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>頭部眼部重建與基礎上色｜Unity 審閱</title><style>
*{box-sizing:border-box}body{margin:0;background:#111b20;color:#e9e4dc;font:17px/1.65 system-ui,"Microsoft JhengHei",sans-serif}main{max-width:1800px;margin:auto;padding:28px 24px 64px}h1{font-size:32px;color:#edc58b;margin:10px 0}.eyebrow{color:#a6b6bd;font-size:14px;letter-spacing:.08em}.note{padding:15px 20px;background:#203137;border-left:4px solid #d2a76c}button{font:inherit;padding:8px 14px;margin:4px;border:1px solid #586f76;border-radius:7px;background:#24363e;color:inherit;cursor:pointer}button[aria-pressed=true]{background:#d2a76c;color:#152027}.controls{margin:10px 0}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.cards.mode-color{grid-template-columns:repeat(2,minmax(0,1fr))}.cards.mode-clay{grid-template-columns:repeat(3,minmax(0,1fr))}figure{margin:0;border:1px solid #38515a;border-radius:10px;overflow:hidden;background:#19282e}figure img{display:block;width:100%;aspect-ratio:1;object-fit:contain;background:#101b20;cursor:zoom-in}figcaption{padding:10px 14px}.small{font-size:14px;color:#afc1c7}#error{color:#ff9c8e}details{margin:25px 0}dialog{border:1px solid #72858c;background:#122128;color:#eee;max-width:95vw;max-height:95vh;padding:12px}dialog img{display:block;max-width:90vw;max-height:80vh}dialog::backdrop{background:#000b}[hidden]{display:none!important}@media(max-width:1100px){.cards,.cards.mode-clay{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){main{padding:16px 10px}.cards,.cards.mode-color,.cards.mode-clay{grid-template-columns:1fr}h1{font-size:25px}}
</style><main><p class="eyebrow">MAP001 · LOCAL STATIC HEAD STUDY · UNITY URP</p>
<h1>眼部重建與頭部基礎上色</h1><p class="note"><strong>審閱版，尚未人物定稿。</strong>沿用已確認的頭臉與髮型方向，重建眼球可見表面並加入棕髮、棕色虹膜、綠頭帶、淺色羽飾及紅圍巾。灰模與上色圖均為 Unity 實際渲染，沒有後製修形。新增 API 費用 0 點。</p>
<div class="controls" id="directions"></div><div class="controls" id="lights"></div><div class="controls" id="crops"></div><div class="controls" id="modes"></div>
<div class="cards" id="cards">
<figure id="concept-card"><img id="concept" alt="原概念圖" tabindex="0"><figcaption>原概念｜圖片參考</figcaption></figure>
<figure id="previous-card"><img id="previous" alt="refined-08 灰模 Unity 畫面" tabindex="0"><figcaption>refined-08｜舊灰模</figcaption></figure>
<figure id="clay-card"><img id="clay" alt="新版眼部灰模 Unity 畫面" tabindex="0"><figcaption>新版｜眼部灰模</figcaption></figure>
<figure id="color-card"><img id="color" alt="新版基礎上色 Unity 畫面" tabindex="0"><figcaption>新版｜基礎上色</figcaption></figure></div>
<p id="angle" class="small"></p><p class="small">點擊任一圖片可放大。新舊模型採相同正交鏡頭、展示高度及照明；外接盒含頸部／圍巾，不代表已完成身體比例整合。</p><p id="error" role="alert"></p>
<details open><summary>本次修改與仍待審閱項目</summary><p>將帶刻線的舊眼球面排除顯示，改用獨立平滑曲面與眼睛 UV；保留來源眼瞼、眉形、髮型及其他外輪廓。左右眼依各自開口定位，不強制鏡像。新增頭部色彩貼圖使用來源 UV 烘焙純色彩，沒有烘入光照、AO 或投影。</p><p>請核對眼睛大小與視線、頭髮／皮膚／頭帶／羽飾交界及配色。這仍是高密度靜態頭部：髮根與羽飾造型精修、全身比例、最終拓樸與材質、骨架和動畫均未驗收。</p><p class="small">保留原網格資料與眼部遮除標記；保護區域座標及 Blender 角點法線逐值完全相同，來源原檔不變。舊眼球面仍在可編輯檔中，顯示由具名透明裁切材質關閉。先前刪面重建造成法線量化的失敗嘗試及日誌保留。</p></details>
<p class="note"><strong>尚未通過的細節：</strong>髮根、部分瀏海末端、羽飾外緣與圍巾交界仍可見局部串色；眼白外緣保留區域仍有細小來源紋理。這些列為已知缺口，不以模型／建置檢查通過代替美術驗收。</p>
<p>45° 俯視只用來檢查頭部辨識度，不是正式房間整合。此頁未替換遊戲玩家，沒有動畫、負載、長循環或 GPU FPS 測試。</p><p class="small">ARTVERSION · 60 張 Unity 畫面 · 4 張概念參考 · 全部圖片嵌入本頁，可離線開啟。</p></main>
<dialog id="zoom"><button id="close-zoom">關閉放大</button><img id="zoom-image" alt="放大畫面"></dialog>
<script>const images=IMAGES;let direction='front',light='neutral',close=false,mode='compare';
function group(id,items,value,set){const box=document.getElementById(id);box.innerHTML='';for(const [v,label]of items){const b=document.createElement('button');b.textContent=label;b.setAttribute('aria-pressed',String(v===value));b.onclick=()=>{set(v);render()};box.appendChild(b)}}
function render(){group('directions',[['front','正面'],['left','面向左'],['back','背面'],['right','面向右'],['threequarter','斜側面'],['top45','45° 俯視']],direction,v=>direction=v);group('lights',[['neutral','中性光'],['warm','暖光']],light,v=>light=v);group('crops',[[false,'完整頭部'],[true,'頭臉近景']],close,v=>close=v);group('modes',[['compare','完整比較'],['clay','檢查灰模'],['color','查看上色']],mode,v=>mode=v);
const suffix=close&&!['back','top45'].includes(direction)?'-face':'';document.getElementById('concept').src=images['concept-'+(['threequarter','top45'].includes(direction)?'front':direction)];document.getElementById('previous').src=images['previous-clay-'+light+'-'+direction+suffix];document.getElementById('clay').src=images['eye-color-clay-'+light+'-'+direction+suffix];document.getElementById('color').src=images['eye-color-palette-'+light+'-'+direction+suffix];document.getElementById('previous-card').hidden=mode==='color';document.getElementById('clay-card').hidden=mode==='color';document.getElementById('color-card').hidden=mode==='clay';document.getElementById('cards').className='cards mode-'+mode;document.getElementById('angle').textContent=['threequarter','top45'].includes(direction)?'沒有同角度概念圖，左欄保留正面參考。':direction==='back'&&close?'背面保留完整頭部。':'概念圖與 Unity 的鏡頭透視不同，請以造型與配色對照。';}
const dialog=document.getElementById('zoom');for(const id of ['concept','previous','clay','color']){const im=document.getElementById(id);im.onerror=()=>document.getElementById('error').textContent='圖片載入失敗，請保留此錯誤。';im.onclick=()=>{document.getElementById('zoom-image').src=im.src;dialog.showModal()};im.onkeydown=e=>{if(e.key==='Enter')im.click()};}document.getElementById('close-zoom').onclick=()=>dialog.close();render();</script></html>'''
page=page.replace('NORMALANGLE',f"{geometry['retained_normal_max_angle_degrees']:.5f}").replace('ARTVERSION',a.art).replace('IMAGES',json.dumps(images,separators=(',',':')))
(out/'review.html').write_text(page,encoding='utf-8');shutil.copytree(capture,out/'unity')
manifest={'schema':'ao_head_eye_color_review_v1','art':a.art,'capture':str(capture),'unity_images':60,'embedded_images':64,'html_sha256':sha(out/'review.html'),'image_hashes':hashes,'art_approved':False,'animation_tested':False,'performance_tested':False}
(out/'review-lock.json').write_text(json.dumps(manifest,indent=2)+'\n');print(out/'review.html')
