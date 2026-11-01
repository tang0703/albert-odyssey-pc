"""Self-contained actual Unity static body review. No image alteration."""
from pathlib import Path
import argparse,base64,hashlib,json,shutil
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/tripo-head-v1'
p=argparse.ArgumentParser();p.add_argument('--version',required=True);p.add_argument('--capture',required=True);p.add_argument('--out',required=True);p.add_argument('--tripo-full',action='store_true');a=p.parse_args()
HEAD_BASE=BASE
if a.tripo_full:BASE=ROOT/'art/local/tripo-body-v1'
out=BASE/a.out;out.mkdir(exist_ok=False);capture=Path(a.capture)
record=json.loads((capture/'review.json').read_bytes());assert record['engine']=='Unity URP' and record['captures']==23 and not record['animation_tested'] and not record['performance_tested']
images={};hashes={};sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths={p.stem:p for p in capture.glob('*.png')};assert len(paths)==23
paths['concept']=ROOT/'art/enhanced25d/v1/references/approved-character.png'
paths['approved-head']=HEAD_BASE/'review-cloud-texture-01/unity/cloud-palette-neutral-threequarter.png'
for name,file in paths.items():
    with Image.open(file) as im:im.verify()
    images[name]='data:image/png;base64,'+base64.b64encode(file.read_bytes()).decode();hashes[name]=sha(file)
page='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>核准頭部＋身體比例與服裝｜Unity 靜態審閱</title>
<style>*{box-sizing:border-box}body{margin:0;background:#111b20;color:#e9e4dc;font:17px/1.65 system-ui,"Microsoft JhengHei",sans-serif}main{max-width:1600px;margin:auto;padding:28px 24px 64px}h1{font-size:32px;color:#edc58b;margin:10px 0}.small{font-size:14px;color:#a6b6bd}.note{padding:15px 20px;background:#203137;border-left:4px solid #d2a76c}button{font:inherit;padding:8px 14px;margin:4px;border:1px solid #586f76;border-radius:7px;background:#24363e;color:inherit;cursor:pointer}button[aria-pressed=true]{background:#d2a76c;color:#152027}.controls{margin:10px 0}.cards{display:grid;grid-template-columns:1fr 1fr;gap:18px}figure{margin:0;border:1px solid #38515a;border-radius:10px;overflow:hidden;background:#19282e}figure img{display:block;width:100%;height:720px;object-fit:contain;background:#101b20;cursor:zoom-in}figcaption{padding:10px 14px}.extras{display:grid;grid-template-columns:1fr 2fr;gap:18px;margin:24px 0}.extras img{height:auto;max-height:460px}#error{color:#ff9c8e}dialog{border:1px solid #72858c;background:#122128;color:#eee;max-width:95vw;max-height:95vh;padding:12px}dialog img{display:block;max-width:90vw;max-height:80vh}dialog::backdrop{background:#000b}@media(max-width:800px){main{padding:16px 10px}.cards,.extras{grid-template-columns:1fr}figure img{height:520px}h1{font-size:25px}}</style>
<main><p class="small">MAP001 · APPROVED HEAD / BODY FITTING · UNITY URP</p><h1>身體比例與服裝銜接預覽</h1>
<p class="note"><strong>頭部已核准，身體與服裝等待審閱。</strong>沿用 Tripo 上色頭部及現有圍巾；本地製作／調整身體輪廓。圖像為 Unity 獨立程式實際渲染，沒有後製修形。</p>
<div id="directions" class="controls"></div><div id="lights" class="controls"></div><div id="modes" class="controls"></div>
<div class="cards"><figure><img id="concept" alt="原核准全身概念圖" tabindex="0"><figcaption>原概念｜造型與配色參考</figcaption></figure><figure><img id="current" alt="新版身體 Unity 實際畫面" tabindex="0"><figcaption id="caption"></figcaption></figure></div>
<p id="view-note" class="small"></p><p id="error" role="alert"></p>
<p class="small">點圖可放大。概念為插畫透視；Unity 使用固定正交鏡頭。中性／暖光是獨立展示光，不是材質內烘焙光照。</p>
<div class="extras"><figure><img id="head" alt="先前已核准頭部 Unity 畫面" tabindex="0"><figcaption>已核准頭部｜原審閱畫面，保留作對照</figcaption></figure><figure><img id="room" alt="45度房間內靜態尺寸預覽" tabindex="0"><figcaption>45° 固定鏡頭｜靜態房間尺寸預覽，尚未接入玩法</figcaption></figure></div>
<h2>本輪調整</h2><p>總高度維持 1.125 Unity 單位、腳底零位。頭部僅等比縮放與定位，網格、UV、法線及貼圖保持核准資料。整合副本將頭像下方多餘綠色／淺色胸肩布料面遮除，原檔未改，頭臉與紅圍巾保留；這項顯示調整供您與服裝銜接一起審閱。身體從先前獨立可編輯部件調整肩寬、領口、寬褲與靴型，保留翻折袖口、皮帶及分片衣襬。</p>
<h2>請優先審閱</h2><p>頭身比例與肩寬、圍巾下緣／領口銜接、手臂及手掌大小、褲管蓬度、靴子厚度與整體配色。新增圍巾下襯是身體側獨立部件，用來銜接原頭像的截面，並非修改核准圍巾。這是身體造型預覽；身體布料／皮革使用基礎材質，細節密度尚未等同頭部。衣服分片及關節仍未作最終變形拓樸或蒙皮驗收。</p>
<p class="note">API 任務 0、費用 0。本輪沒有動畫、負載、長循環、效能基準或實際 GPU FPS 測試。沒有修改原房間、Cirrus、來源規則或遊戲玩家。</p><p class="small">VERSION · 23 張 Unity 圖＋全身概念與核准頭部參考 · 自包含離線審閱頁</p></main>
<dialog id="zoom"><button id="close-zoom">關閉放大</button><img id="zoom-image" alt="放大畫面"></dialog>
<script>const images=IMAGES;let direction='threequarter',light='neutral',mode='color';const labels={front:'正面',left:'面向左',back:'背面',right:'面向右',threequarter:'斜側面',top45:'45° 俯視',neckline:'領口與圍巾',waist:'腰帶與衣襬',boots:'皮靴'};
function group(id,items,value,set){const el=document.getElementById(id);el.innerHTML='';for(const [v,label]of items){const b=document.createElement('button');b.textContent=label;b.setAttribute('aria-pressed',String(v===value));b.onclick=()=>{set(v);render()};el.appendChild(b)}}
function render(){group('directions',Object.entries(labels),direction,v=>direction=v);group('lights',[['neutral','中性光'],['warm','暖光']],light,v=>light=v);group('modes',[['color','材質上色'],['clay','四向灰模']],mode,v=>mode=v);const clay=mode==='clay';const dir=clay&&!['front','left','back','right'].includes(direction)?'front':direction;document.getElementById('current').src=images[clay?'clay-'+dir:light+'-'+dir];document.getElementById('caption').textContent='Unity 實際渲染｜'+labels[dir]+'｜'+(clay?'灰模・中性光':light==='warm'?'暖光':'中性光');document.getElementById('view-note').textContent=clay?'灰模提供四方向與固定中性光；其他角度選擇顯示正面。':'領口、腰帶與皮靴可獨立放大；尚未進行動畫或玩法整合。';}
document.getElementById('concept').src=images.concept;document.getElementById('head').src=images['approved-head'];document.getElementById('room').src=images['room-scale-45'];
const dialog=document.getElementById('zoom');for(const id of ['concept','current','head','room']){const im=document.getElementById(id);im.onerror=()=>document.getElementById('error').textContent='圖片載入失敗，請保留紀錄。';im.onclick=()=>{document.getElementById('zoom-image').src=im.src;dialog.showModal()};im.onkeydown=e=>{if(e.key==='Enter')im.click()};}document.getElementById('close-zoom').onclick=()=>dialog.close();render();</script></html>'''
if a.tripo_full:
    page=page.replace('核准頭部＋身體比例與服裝｜Unity 靜態審閱','Tripo 完整人物｜Unity 靜態審閱').replace('APPROVED HEAD / BODY FITTING','COMPLETE TRIPO CHARACTER').replace('身體比例與服裝銜接預覽','Tripo 完整人物預覽')
    start=page.index('<p class="note">');end=page.index('</p>',start)+4
    page=page[:start]+'<p class="note"><strong>整體由 Tripo 生成，等待人物造型審閱。</strong>依最新指示採用同一次生成的頭、臉、身體與服裝，不拼接舊頭部。所有新版人物畫面均為 Unity 實際渲染，未後製修形。</p>'+page[end:]
    start=page.index('<h2>本輪調整</h2>');end=page.index('<p class="small">VERSION',start)
    page=page[:start]+'''<h2>本輪處理</h2><p>完整 Tripo 模型保留全部 79,434 個三角面、47,498 個頂點與 4K PBR 貼圖；僅統一朝向、腳底零位及總高度 1.125 Unity 單位。沒有裁頭、遮除面、拼接或局部造型變更。原先核准頭部另存，左下參考圖不是本模型的一部分。</p>
<h2>請審閱完整人物</h2><p>這是新生成的完整造型，因此頭臉、髮型、羽飾、配色也需重新審閱，不能沿用舊頭部核准。請比較概念圖與實際人物的頭身比例、表情、手掌、袖口、褲管與靴型。材質可能含生成式明暗，不宣稱是已清理完成的無光照底色。拓樸、指縫、衣物與關節尚未作變形／蒙皮驗收。</p>
<p class="note">單次 Tripo 任務實際扣除 40 點，本次合計 40 點，生成後查詢餘額 400 點。改採完整人物沒有再次生成或額外扣點。本輪沒有動畫、負載、長循環、效能基準或實際 GPU FPS 測試；尚未接入正式遊戲。</p>'''+page[end:]
    page=page.replace('已核准頭部｜原審閱畫面，保留作對照','先前核准頭部｜僅供參考，本次不使用').replace('新版身體 Unity 實際畫面','Tripo 完整人物 Unity 實際畫面')
(out/'review.html').write_text(page.replace('VERSION',a.version).replace('IMAGES',json.dumps(images,separators=(',',':'))),encoding='utf-8')
shutil.copytree(capture,out/'unity')
lock={'schema':'ao_body_fit_review_v1','art':a.version,'capture':str(capture),'html_sha256':sha(out/'review.html'),'image_hashes':hashes,'body_approved':False,'head_approved':True,'animation_tested':False,'performance_tested':False}
if a.tripo_full:lock.update(scope='complete Tripo character',head_approved=False,head_replaced=False,task_id='0dde299a-f45b-4076-9182-bbd84bf7c1d4',credits=40,balance_after=400)
(out/'review-lock.json').write_text(json.dumps(lock,indent=2)+'\n');print(out/'review.html')
