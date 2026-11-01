"""Self-contained review with real Unity PNGs; no external/broken image links."""
from pathlib import Path
import base64,hashlib,json,html,shutil,argparse
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'art/local/hunyuan-head-v1'
parser=argparse.ArgumentParser();parser.add_argument('--out',default='review-02');parser.add_argument('--capture',required=True);args=parser.parse_args()
CAPTURE=Path(args.capture).resolve()
OUT=BASE/args.out;OUT.mkdir(exist_ok=False)
record=json.loads((CAPTURE/'review.json').read_bytes())
assert record['captures']==40 and record['engine']=='Unity URP' and not record['performance_tested']
images={}
def add(key,path):
    raw=path.read_bytes();assert raw[:8]==b'\x89PNG\r\n\x1a\n'
    images[key]='data:image/png;base64,'+base64.b64encode(raw).decode()
for path in CAPTURE.glob('*.png'):add(path.stem,path)
for v in ('front','left','back','right'):add('concept-'+v,BASE/f'inputs/{v}.png')
for v in ('front','left','back','right'):add('raw-'+v,BASE/f'prepared-01/diagnostic-{v}.png')
page='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MAP001 頭部幾何小樣｜Unity 實際審閱</title><style>
*{box-sizing:border-box}body{margin:0;background:#101b1f;color:#e9e4db;font:17px/1.65 system-ui,"Microsoft JhengHei",sans-serif}main{max-width:1550px;margin:auto;padding:32px 24px 80px}h1{font-size:32px;margin:0 0 12px;color:#edc58b}h2{font-size:23px;margin-top:40px}.status{border-left:4px solid #d2a76c;padding:12px 20px;background:#203137}button,a{font:inherit}button{padding:10px 19px;margin:4px;border-radius:8px;border:1px solid #65777a;background:#22363c;color:inherit;cursor:pointer}button[aria-pressed=true]{background:#d2a76c;color:#102024;border-color:#eacfaa}.controls{margin:18px 0}.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.card{margin:0;background:#18292f;border:1px solid #385057;border-radius:14px;overflow:hidden}.card img{display:block;width:100%;aspect-ratio:1;object-fit:contain;background:#1b262b}.card figcaption{padding:12px 18px}.small{color:#b1c1c5;font-size:15px}a{color:#efc690}.note{max-width:1100px}.error{color:#ff978b}details{margin:16px 0;padding:15px;background:#1a2a30;border-radius:10px}.raw{max-width:650px} .raw img{width:100%}@media(max-width:850px){.cards{grid-template-columns:1fr}main{padding:24px 14px}.card img{max-height:620px}}
</style><main><p class="small">MAP001 / LOCAL 3D HEAD STUDY / UNITY URP</p><h1>頭臉與髮型：先看幾何，再看配色</h1>
<div class="status">本頁是<strong>頭部小樣，尚未定稿</strong>。新舊模型均置於等高展示框，以相同鏡頭與燈光由 Unity 實際渲染；裁切含不同程度的頸部／圍巾，不作精確頭身比測量。未替換遊戲人物；未製作動畫，未進行負載或效能測試。</div>
<p class="note">核准概念是插畫，四向透視並非校準掃描。先核對臉頰／下巴、髮流與瀏海。近景使用同一組無投影主光與補光；這是造型檢查照明，不是遊戲房間照明驗收。<strong>本頁選用 refined-02 灰模；基本分色試作未通過，僅保留為問題紀錄。後續 refined-04 羽飾分件造成局部表面失真，未採用。</strong>目前不可核准為最終人物。</p>
<div class="controls" id="directions"></div><div class="controls" id="materials"></div><div class="controls" id="lighting"></div>
<div class="cards"><figure class="card"><img id="concept" alt="核准概念頭部裁切"><figcaption>原概念｜核准圖片裁切</figcaption></figure><figure class="card"><img id="old" alt="v2 Unity 頭部"><figcaption>原 v2｜Unity 實際渲染</figcaption></figure><figure class="card"><img id="new" alt="新頭部小樣 Unity 渲染"><figcaption>新小樣｜Unity 實際渲染</figcaption></figure></div>
<p class="small" id="angleNote"></p><p class="error" id="errors"></p>
<h2>本次實際修整</h2><ul><li>以核准的四方向頭部圖生成初始幾何，改變原本程序髮束堆疊的起點。</li><li>清除游離碎片，修補細孔並收整重建噪點。</li><li>局部收整側後方多餘突起與嘴部；重複羽飾尚未完全解決，原始模型完整保留。</li><li>提供不帶貼圖灰模，另保留基本分色失敗紀錄，不將它視為定稿。</li></ul>
<h2>尚未通過的部分</h2><p class="note">眉眼神情、嘴角、耳朵與髮根銜接、側後髮束及羽飾根部仍需要審閱。模型目前是靜態雕塑參考網格，沒有可供動畫使用的最終拓樸、蒙皮或 UV 材質。服裝與整身精修尚未展開；此頁不代表 C2 已核准。</p>
<details><summary>原始生成幾何（Blender 診斷，非 Unity 成果）</summary><p>四視角原始結果可見側面多餘突起與碎片；這些紀錄保留，不以新圖覆蓋。</p><div class="raw"><img id="raw" alt="原始四視角生成的 Blender 灰模"></div></details>
<p class="small">所有審閱圖片已嵌入本頁，離線可用。模型、生成紀錄與授權文件留在本地。原有 v2、遊戲資料與候選套件保持不變。</p>
</main><script>const images=IMAGES;let direction='front',material='clay',lighting='neutral';
const groups=[['directions',[['front','正面'],['left','面向左側'],['back','背面'],['right','面向右側'],['threequarter','斜側面']]],['materials',[['clay','灰模・檢查體積'],['palette','分色問題紀錄・不採用']]],['lighting',[['neutral','中性光'],['warm','暖光']]]];
function render(){for(const [group,opts] of groups){document.getElementById(group).innerHTML='';for(const [id,label] of opts){const b=document.createElement('button');b.textContent=label;b.setAttribute('aria-pressed',String(id===(group==='directions'?direction:group==='materials'?material:lighting)));b.onclick=()=>{if(group==='directions')direction=id;else if(group==='materials')material=id;else lighting=id;render()};document.getElementById(group).appendChild(b)}}
const ref=direction==='threequarter'?'front':direction;document.getElementById('concept').src=images['concept-'+ref];document.getElementById('raw').src=images['raw-'+ref];document.getElementById('old').src=images['v2-'+material+'-'+lighting+'-'+direction];document.getElementById('new').src=images['pilot-'+material+'-'+lighting+'-'+direction];document.getElementById('angleNote').textContent=direction==='threequarter'?'斜側面沒有同角度概念，左欄保留正面參考。':'模型角度一致；概念圖本身的透視與俯角不完全相同。';}
document.querySelectorAll('img').forEach(i=>i.onerror=()=>document.getElementById('errors').textContent='圖片載入失敗，請保留此錯誤並回報。');render();</script></html>'''
page=page.replace('IMAGES',json.dumps(images,separators=(',',':')))
(OUT/'review.html').write_text(page,encoding='utf-8')
shutil.copytree(CAPTURE,OUT/'unity')
manifest={'scope':'static head pilot only','unity_capture':str(CAPTURE),'art_approved':False,'palette_accepted':False,'selected_geometry':'refined-02','refined_04_rejected':True,
    'embedded_images':len(images),'html_sha256':hashlib.sha256((OUT/'review.html').read_bytes()).hexdigest(),
    'animation_tested':False,'performance_tested':False,
    'images':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (OUT/'unity').glob('*.png')}}
(OUT/'review-lock.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(OUT/'review.html')
