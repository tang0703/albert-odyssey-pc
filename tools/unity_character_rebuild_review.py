"""Freeze the v2 static Unity review and publish a self-contained comparison."""
from pathlib import Path
import base64, hashlib, json, shutil
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'art/unity/player-refined-v2'
OLD=ROOT/'art/unity/player-refined-v1'
if (ART/'review-lock.json').exists():raise RuntimeError('Review frozen')
def identity(p):
    raw=p.read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
old_lock=json.loads((OLD/'review-lock.json').read_bytes())
for name,record in old_lock['files'].items():assert identity(OLD/name)==record,name
capture=Path((ROOT/'reports/unity/last-player-refined-v2-review-capture.txt').read_text(encoding='utf-8-sig').strip()).resolve()
build=Path((ROOT/'reports/unity/last-player-refined-v2-review-build.txt').read_text(encoding='utf-8-sig').strip()).resolve()
assert capture.is_relative_to((ROOT/'reports/unity').resolve()) and build.is_relative_to((ROOT/'build').resolve())
report=json.loads((capture/'review.json').read_bytes())
built=json.loads((build/'review-build.json').read_bytes())
assert report['passed'] and report['captures']==22 and built['art_version']=='player-refined-v2'
assert built['manifest_sha256']==identity(ART/'material-manifest.json')['sha256']
shutil.copytree(capture,ART/'review')
embedded={}
def img(path,alt):
    with Image.open(path) as image:image.verify()
    key=path.relative_to(ROOT).as_posix();embedded[key]=identity(path)
    return '<img alt="'+alt+'" src="data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()+'">'
def figure(path,label):return '<figure>'+img(path,label)+'<figcaption>'+label+'</figcaption></figure>'
concept=ROOT/'art/enhanced25d/v1/review/directions-review.png'
assert identity(concept)==old_lock['concept_reference']
html='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>人物重做 v2｜概念與 Unity 實際渲染</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#10191c;color:#eee5d5;font:17px/1.7 system-ui,"Microsoft JhengHei",sans-serif}main{max-width:1380px;margin:auto;padding:32px 24px}h1{line-height:1.3}h2{margin-top:48px;color:#e9bd7b}.notice{padding:18px;border-left:4px solid #d5a86b;background:#203036}.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}figure{margin:0;background:#18272c;border-radius:10px;overflow:hidden}img{display:block;width:100%;height:auto}figcaption{padding:12px 16px}details{margin-top:20px}summary{cursor:pointer;padding:12px;background:#23363b}p{color:#c7cecc}small{color:#b1bfbc}@media(max-width:650px){main{padding:20px 10px}.pair{gap:7px}figcaption{font-size:13px;padding:8px}}</style>
<main><h1>依原概念圖重做人物 · v2</h1><div class="notice">C2 靜態造型審閱，尚未核准。新版是重新建模的 3D 人物；本輪未製作動畫、最終蒙皮或負載測試，未替換正式遊戲。</div>
<h2>核准的原概念圖</h2><p>這張是造型目標，不是 Unity 畫面。下方所有新版角色均為 Unity URP 直接輸出，沒有用生成插畫替代模型。</p>'''
html+=figure(concept,'原概念：髮束走向、俐落眉眼、收腰上衣、分片衣襬與皮靴')
concept_data='data:image/png;base64,'+base64.b64encode(concept.read_bytes()).decode()
html+='<h2>概念正面與新版 Unity</h2><section class="pair"><figure><svg xmlns="http://www.w3.org/2000/svg" viewBox="45 210 420 730" style="display:block;width:100%;height:auto" role="img" aria-label="原概念正面，僅裁切檢視"><image href="'+concept_data+'" width="1920" height="1080"/></svg><figcaption>原概念正面｜僅裁切檢視，未修圖</figcaption></figure>'
html+=figure(ART/'review/refined-neutral-front.png','新版 v2｜Unity 實際渲染')+'</section>'
html+='<h2>正面：被退回的 v1 與重做 v2</h2><section class="pair">'
html+=figure(OLD/'review/refined-neutral-front.png','前版 v1｜已退回')
html+=figure(ART/'review/refined-neutral-front.png','新版 v2｜Unity 中性光・待審閱')+'</section>'
html+='<p>兩版使用同一近景鏡頭、照明與 1.125 單位高度。新模型縮小臉部、重建髮流與衣服結構；色彩、細節、表情和概念圖仍可能存在差距，請以實際畫面審閱。</p>'
for light,light_label in [('neutral','中性光'),('warm','暖光')]:
    html+='<h2>'+light_label+'四方向</h2><section class="pair">'
    # Historical capture names describe the viewed side; label the visible
    # facing direction explicitly to match the reference's LEFT/RIGHT arrows.
    for view,label in [('front','正面'),('right','向左（側面）'),('back','背面'),('left','向右（側面）')]:
        html+=figure(ART/f'review/refined-{light}-{view}.png','Unity v2 '+light_label+'・'+label)
    html+='</section><details open><summary>'+light_label+'臉部近景</summary><section class="pair">'
    html+=figure(OLD/f'review/refined-{light}-face.png','前版 v1')
    html+=figure(ART/f'review/refined-{light}-face.png','新版 v2')+'</section></details>'
html+='<h2>實際房間比例 · 固定 45° 鏡頭</h2>'
html+=figure(ART/'review/refined-room.png','Unity 靜態房間預覽｜1.125 單位人物・原有房間暖光')
html+='<p>房間、Cirrus、來源包與玩法未修改。這是隔離的靜態人物審閱程式，並非本輪完整玩法驗收。</p><h2>本輪範圍</h2><p>頭臉與眉眼、交疊髮流、頭帶與羽飾、領口、收腰上衣、分片衣襬、袖口、圍巾、褲管與靴型。可編輯的獨立表面保留在 Blender 的 EDITABLE 集合；無骨架、無動畫。最終材質與變形拓樸尚待後續工作。</p>'
if built['material_mode']=='surface_palette_no_bake':
    html+='<p>本次新版審閱使用 URP 分區色彩與粗糙度材質，以隔離 UV 烘焙黑邊並集中核對造型；不是最終貼圖驗收。2048px UV 烘焙試作與先前瑕疵畫面保留，未以修圖掩蓋。前版 v1 為其封存 UV 材質畫面，因此材質處理並不相同。</p>'
html+='<p>所有圖片已內嵌；頁面無外部圖片依賴，也不需要 JavaScript。原概念圖與前版封存檔未修改。</p></main></html>'
(ART/'review.html').write_text(html,encoding='utf-8')
validation=json.loads((ROOT/'reports/unity/player-refined-v2-c1-validation.json').read_bytes())
assert validation['passed']
record={'schema':'ao_character_rebuild_review_v2','status':'pending_user_approval','approved':False,
        'concept_reference':identity(concept),'previous_review_lock':identity(OLD/'review-lock.json'),
        'source_baseline':identity(ROOT/'unity-remake/SourceContracts/source-baseline.json'),
        'capture_source':capture.relative_to(ROOT).as_posix(),'build_source':build.relative_to(ROOT).as_posix(),
        'build_record':built,'review_executable':identity(build/'MAP001-Character-Review.exe'),
        'review_sources':{name:identity(ROOT/name) for name in ['tools/unity_character_rebuild.py','tools/unity_character_bake.py','unity-remake/Assets/Editor/CharacterReviewBuild.cs','unity-remake/Assets/Scripts/CharacterReview.cs']},
        'geometry_validation':validation,'embedded_images':embedded,
        'height':1.125,'room_camera_pitch':45,'rig_complete':False,'animations_complete':False,'performance_tested':False,
        'files':{p.relative_to(ART).as_posix():identity(p) for p in ART.rglob('*') if p.is_file() and p.name!='review-lock.json'}}
(ART/'review-lock.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'review':str(ART/'review.html'),'files':len(record['files']),'embedded_images':len(embedded),'status':record['status']}))
