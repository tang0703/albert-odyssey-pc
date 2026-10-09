extends SceneTree
## Standalone preview uses the same frame files and timing as the battle runtime.
func _initialize() -> void:
	call_deferred("build")

func build() -> void:
	var config_path: String = "res://battle-demo/data/appearances.json"
	if "--candidate" in OS.get_cmdline_user_args():
		config_path = "res://reports/battle-appearances-candidate.json"
	var appearances: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(config_path))
	var rows: Array[Dictionary] = []
	for slot: String in ["guardian", "scout"]:
		var appearance: Dictionary = appearances[slot]
		if appearance.get("renderer") != "sprite":
			push_error("Preview needs installed sprite definitions: " + slot)
			quit(1)
			return
		for animation_name: String in ["idle", "attack", "hurt", "down"]:
			var spec: Dictionary = appearance["states"][animation_name]
			var images: Array[String] = []
			for path: String in spec["frames"]:
				var local_path: String = "res://battle-demo/" + path.trim_prefix("res://")
				images.append("data:image/png;base64," + Marshalls.raw_to_base64(FileAccess.get_file_as_bytes(local_path)))
			rows.append({"name": appearance["display_name"], "state": animation_name, "frames": images, "durations": spec["durations"], "loop": spec["loop"], "hit_frame": spec.get("hit_frame", -1), "facing": appearance["default_facing"]})
	var html: String = """<!doctype html>
<html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>三曜試煉 · 角色動畫預覽</title>
<style>
:root{color-scheme:dark;font:16px/1.5 system-ui,sans-serif;background:#101b27;color:#e3ebed}*{box-sizing:border-box}body{max-width:1400px;margin:auto;padding:32px}h1{font-size:30px;margin:0 0 6px}p{color:#b3c4cc}.controls{position:sticky;top:0;display:flex;gap:12px;flex-wrap:wrap;padding:15px 0;background:#101b27eF;z-index:3}button,select{font:inherit;background:#263b4b;color:#ecf5f6;padding:10px 18px;border:1px solid #537082;border-radius:8px;cursor:pointer}button:focus-visible,select:focus-visible{outline:3px solid #f7d68a}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px}article{background:#1b2c3b;border:1px solid #3b5261;border-radius:12px;overflow:hidden}.title{padding:12px 15px;display:flex;justify-content:space-between;font-weight:650}.stage{position:relative;aspect-ratio:1;background-color:#163243;background-image:linear-gradient(45deg,#ffffff05 25%,transparent 25%),linear-gradient(-45deg,#ffffff05 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#ffffff05 75%),linear-gradient(-45deg,transparent 75%,#ffffff05 75%);background-size:24px 24px;background-position:0 0,0 12px,12px -12px,-12px 0}.stage:after{content:'';position:absolute;left:0;right:0;top:87.5%;border-top:1px dashed #e3c78a90}.stage img{width:100%;height:100%;object-fit:contain}.status{padding:10px 15px;font:13px/1.5 ui-monospace,monospace;color:#aebfc7;min-height:62px}.stage.light{background-color:#ddd9ce}.stage.solid{background-image:none}.hit{color:#f6d788}footer{font-size:13px;color:#a9bac3;padding:20px 0}@media(max-width:950px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:480px){body{padding:16px}.grid{grid-template-columns:1fr}}
</style>
<h1>三曜試煉 · 角色動畫預覽</h1><p>派克與 WEREDOG · 32 幀 · 每幀 512 × 512 RGBA。虛線為固定腳底基準；顯示原始朝向。</p>
<div class="controls"><button id="pause">暫停</button><button id="restart">重新播放</button><label>速度 <select id="speed"><option value="1">1×</option><option value="2">2×</option></select></label><label>背景 <select id="background"><option value="dark">深色格紋</option><option value="light">淺色格紋</option><option value="solid">深色純色</option></select></label><button id="flip">左右翻轉</button></div>
<main class="grid" id="grid"></main><footer>待機循環；攻擊、受傷與倒下播放一次並停在末格。重新播放可重啟所有動作。預覽與遊戲使用同一份影格時長，速度只影響演出。</footer>
<script>
const rows=__ROWS__;
const labels={idle:'待機',attack:'攻擊',hurt:'受傷',down:'倒下'};
let paused=false,speed=1,last=performance.now(),elapsed=0,flip=false;
const grid=document.getElementById('grid');
const views=rows.map(row=>{const card=document.createElement('article');card.innerHTML='<div class="title"><span></span><span></span></div><div class="stage"><img alt=""></div><div class="status"></div>';card.querySelectorAll('.title span')[0].textContent=row.name;card.querySelectorAll('.title span')[1].textContent=labels[row.state];const img=card.querySelector('img');img.alt=row.name+' '+labels[row.state];img.src=row.frames[0];grid.append(card);return {row,img,status:card.querySelector('.status'),stage:card.querySelector('.stage'),images:row.frames.map(src=>{const i=new Image();i.src=src;return i})}});
function draw(){views.forEach(v=>{const total=v.row.durations.reduce((a,b)=>a+b,0);let t=v.row.loop?elapsed%total:Math.min(elapsed,total);let frame=0;while(frame<v.row.frames.length-1&&t>=v.row.durations[frame]){t-=v.row.durations[frame];frame++}if(v.img.dataset.frame!==String(frame)){v.img.src=v.row.frames[frame];v.img.dataset.frame=String(frame)}const hit=frame===v.row.hit_frame;v.status.textContent=`${frame+1} / ${v.row.frames.length} 幀 · ${Math.round(v.row.durations[frame]*1000)} ms · ${v.row.loop?'循環':elapsed>=total?'停在末格':'播放中'}${hit?' · 命中':''}`;v.status.classList.toggle('hit',hit)})}
function tick(now){if(!paused)elapsed+=Math.min((now-last)/1000,.1)*speed;last=now;draw();requestAnimationFrame(tick)}
document.getElementById('pause').onclick=e=>{paused=!paused;e.target.textContent=paused?'繼續':'暫停'};
document.getElementById('restart').onclick=()=>{elapsed=0;draw()};
document.getElementById('speed').onchange=e=>speed=Number(e.target.value);
document.getElementById('background').onchange=e=>views.forEach(v=>v.stage.className='stage '+(e.target.value==='dark'?'':e.target.value));
document.getElementById('flip').onclick=()=>{flip=!flip;views.forEach(v=>v.img.style.transform=flip?'scaleX(-1)':'')};
Promise.all(views.flatMap(v=>v.images).map(i=>i.decode().catch(()=>{}))).then(()=>{last=performance.now();requestAnimationFrame(tick)});
</script></html>
"""
	html = html.replace("__ROWS__", JSON.stringify(rows))
	var file := FileAccess.open("res://reports/character-animation-preview.html", FileAccess.WRITE)
	if file == null:
		quit(1)
		return
	file.store_string(html)
	file.close()
	print("BATTLE PREVIEW: reports/character-animation-preview.html, 8 animations, 32 embedded frames")
	quit()
