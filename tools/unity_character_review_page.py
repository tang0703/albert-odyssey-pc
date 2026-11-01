"""Publish already-rendered C2 images into an immutable, local review bundle."""
from pathlib import Path
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parents[1];ART=ROOT/'art/unity/player-refined-v1'
if (ART/'review-lock.json').exists():raise RuntimeError('Review already frozen')
capture=Path((ROOT/'reports/unity/last-character-review-capture.txt').read_text(encoding='utf-8-sig').strip()).resolve()
assert capture.is_relative_to((ROOT/'reports/unity').resolve())
report=json.loads((capture/'review.json').read_bytes());assert report['passed'] and report['captures']==22
target=ART/'review';shutil.copytree(capture,target)
page='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MAP001 人物精修｜C2 造型審閱</title>
<style>:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#10191c;color:#e8e3d8;font:17px/1.7 system-ui,"Microsoft JhengHei",sans-serif}main{max-width:1240px;margin:auto;padding:40px 24px}h1{font-size:36px;line-height:1.3}h2{margin-top:42px;color:#ebc18c}p{max-width:1000px;color:#c2c9c8}.tag{color:#ebc18c;font-size:14px;letter-spacing:.12em}.notice{border-left:3px solid #bb9567;padding:14px 20px;background:#1b292d}.pair{display:grid;grid-template-columns:1fr 1fr;gap:22px}figure{margin:0;background:#162327;border:1px solid #304349;border-radius:12px;overflow:hidden}figure img{display:block;width:100%;height:auto}figcaption{padding:10px 18px}button{background:#24383e;color:#e8e3d8;border:1px solid #52696c;border-radius:7px;padding:10px 18px;margin:4px;cursor:pointer;font:inherit}button[aria-pressed=true]{background:#d4ae78;color:#172023;border-color:#d4ae78}.toolbar{margin:18px 0}a{color:#ebc18c}details{padding:16px 0}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:12px;border-bottom:1px solid #314247}small{color:#a6b5b5}@media(max-width:650px){.pair{gap:8px}main{padding:24px 12px}h1{font-size:27px}figcaption{font-size:14px;padding:7px}button{padding:8px 12px}}</style>
<main><span class="tag">MAP001 / UNITY CHARACTER / C2</span><h1>人物精修造型審閱</h1>
<p>重整臉部曲面與眼瞼、髮束走向、連續手臂、衣物輪廓與皮靴。仍保留綠頭帶、羽飾、紅圍巾及原有遊戲內總高度。下方新舊人物均為 Unity 實際渲染。</p>
<div class="notice"><strong>等待造型核准，再進入最終蒙皮與動畫。</strong><br>目前為靜態模型；沒有替換正式遊戲人物，沒有新候選 ZIP，也沒有負載或 FPS 測試。</div>
<h2>同條件新舊對照</h2><div class="toolbar" id="lights"><button data-light="neutral" aria-pressed="true">中性光</button><button data-light="warm" aria-pressed="false">暖光</button></div>
<div class="toolbar" id="views"><button data-view="front" aria-pressed="true">正面</button><button data-view="left" aria-pressed="false">左側</button><button data-view="back" aria-pressed="false">背面</button><button data-view="right" aria-pressed="false">右側</button><button data-view="face" aria-pressed="false">臉部近景</button></div>
<section class="pair"><figure><img id="old" src="review/old-neutral-front.png" alt="舊版 Unity 人物"><figcaption>舊版 U4｜待機首姿勢</figcaption></figure><figure><img id="new" src="review/refined-neutral-front.png" alt="新版 Unity 靜態人物"><figcaption>新版精修｜待審閱靜態模型</figcaption></figure></section>
<p><small>近景使用共同補光與較短陰影範圍以辨認造型，不作效能比較。原有暖光與 45° 鏡頭的實際房間比例見下方。</small></p>
<h2>原概念圖</h2><figure><img src="../../enhanced25d/v1/review/directions-review.png" alt="先前核准的四方向概念圖"><figcaption>造型參考，不能作為新版 Unity 渲染證據。</figcaption></figure>
<h2>固定房間鏡頭與人物比例</h2><section class="pair"><figure><a href="review/old-room.png"><img src="review/old-room.png" alt="舊人物房間比例"></a><figcaption>舊版人物｜點圖看原尺寸</figcaption></figure><figure><a href="review/refined-room.png"><img src="review/refined-room.png" alt="新版人物房間比例"></a><figcaption>新版人物｜點圖看原尺寸</figcaption></figure></section>
<p>房間使用原有模型、材質與暖光；沒有為了人物重畫家具或修改碰撞。此處是隔離的靜態比例預覽，沒有執行互動、裝備或事件。</p>
<h2>本次交付與待辦</h2><table><tr><th>完成供審閱</th><td>四方向與臉部、連續手臂、修整鞋靴、角色專用 2048px UV 色彩／法線／材質貼圖。</td></tr><tr><th>核准後進行</th><td>22 骨最終蒙皮、六個動作、握劍、衣物變形、全流程與三解析度驗證。</td></tr><tr><th>尚未驗收</th><td>人物造型偏好、最終動畫、功能整合及效能。細緻插畫質感與目前 3D 表現仍有差異。</td></tr></table>
<p><a href="player-refined.blend">可編輯網格與程序材質</a> · <a href="player-textured.blend">貼圖版 Blender</a> · <a href="player-static.fbx">靜態 FBX</a> · <a href="review-lock.json">審閱素材清單</a></p>
<details><summary>渲染與診斷說明</summary><p>所有審閱圖片直接由 Unity URP 輸出，未進行影像修圖。近景兩版本均使用相同主光、0.28 補光與陰影設定；房間恢復既有暖光且不加補光。髮束法線與近景陰影問題的先前失敗畫面、無陰影隔離診斷仍保留於本地報告。這些診斷圖不作正式造型畫面。</p></details>
</main><script>let light='neutral',view='front';function update(){document.querySelector('#old').src='review/old-'+light+'-'+view+'.png';document.querySelector('#new').src='review/refined-'+light+'-'+view+'.png';document.querySelectorAll('[data-light]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.light===light));document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.view===view));}document.querySelectorAll('[data-light]').forEach(b=>b.onclick=()=>{light=b.dataset.light;update()});document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;update()});</script></html>'''
(ART/'review.html').write_text(page,encoding='utf-8')
def identity(p):return {'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
record={'schema':'ao_character_refinement_review_v1','status':'pending_user_approval','approved':False,'source_baseline':identity(ROOT/'unity-remake/SourceContracts/source-baseline.json'),'old_art_lock':identity(ROOT/'art/unity/startroom-u4/asset-lock.json'),'concept_reference':identity(ROOT/'art/enhanced25d/v1/review/directions-review.png'),'height':1.125,'room_camera_pitch':45,'rig_complete':False,'animations_complete':False,'performance_tested':False,'capture_source':capture.relative_to(ROOT).as_posix(),'files':{p.relative_to(ART).as_posix():identity(p) for p in ART.rglob('*') if p.is_file() and p.name!='review-lock.json'}}
(ART/'review-lock.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'review':str(ART/'review.html'),'files':len(record['files']),'status':record['status']}))
