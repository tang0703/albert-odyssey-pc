extends "res://enhanced25d_main.gd"
const LandingArt = preload("res://landing25d_loader.gd")
const LandingRender = preload("res://landing25d_renderer.gd")
const LaiaAnimation = preload("res://landing25d_animation.gd")
var landing_art: Dictionary = {}
var landing_page_capture: int = 0

func _ready() -> void:
	var directory: String = LandingArt.default_directory()
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--landing25d-package="): directory=arg.trim_prefix("--landing25d-package=")
		if arg.begins_with("--landing25d-page="): landing_page_capture=arg.trim_prefix("--landing25d-page=").to_int()
	if landing_page_capture>0: landing_capture="after"
	landing_art=LandingArt.load_bundle(directory)
	if not landing_art.ok: startup_error=str(landing_art.error)
	super._ready()
	if startup_error.is_empty(): get_window().title="MAP001 兩場景與 LAIA · 2.5D 功能候選版"
	if landing_page_capture not in range(9): startup_error="Invalid dialogue screenshot page"; paused=true

func workbench_title() -> String: return "MAP001  /  兩場景與 LAIA · 2.5D"
func workbench_subtitle() -> String: return "暖光木造全景 · 原作事件與八頁繁中對話 · 效能未驗收"

func enhanced_room() -> bool:
	return selected_appearance=="enhanced25d" and enhanced_bundle.get("ok",false) and landing_art.get("ok",false)

func draw_map(canvas: Control) -> void:
	if not enhanced_room() or int(shown_event.get("scene",8))==8: super.draw_map(canvas); return
	var error: String = LandingRender.draw(canvas,self,landing_art)
	if not error.is_empty(): startup_error=error; paused=true; push_error(error)

func refresh() -> void:
	super.refresh()
	if transfer_ready and enhanced_room() and int(shown_event.get("scene",8))==7:
		domain_label.text="樓下 2.5D · 98 格核准行走範圍 · 效能未驗收"
		animation_label.text="F2 四外觀切換 · LAIA 52 幀預載\n固定全景；鏡頭與劇情規則保持來源結果"
	_dialogue_layout()

func _dialogue_layout() -> void:
	super._dialogue_layout()
	if dialogue_panel != null and enhanced_room() and int(shown_event.get("scene",8))==7:
		dialogue_panel.position.y=maxf(18,map_canvas.size.y-dialogue_panel.size.y-18)

func _landing_auto_pad() -> int:
	if landing_page_capture>0 and dialogue.active:
		var absolute_page: int = dialogue.page+1 if dialogue_id=="map001_00b141" else dialogue.page+6 if dialogue_id=="map001_00b2e2" else 0
		if absolute_page==landing_page_capture:
			qa_capture_ready=true; paused=true; return 0
	return super._landing_auto_pad()

func qa_identity() -> Dictionary:
	var result: Dictionary = super.qa_identity()
	result.schema="ao_pc_landing25d_ui_qa_v1"
	result.landing25d_preloaded=landing_art.get("preloaded",false)
	result.landing25d_manifest_sha256=landing_art.get("manifest_sha256","")
	result.pixel_fallback_scene7=false
	result.dialogue_capture_page=landing_page_capture
	result.dialogue_text=dialogue_text.text if dialogue_text != null else ""
	if int(shown_event.get("scene",8))==7 and shown_event.get("world_visible",false):
		result.laia_art=LaiaAnimation.select(str(shown_event.arrival_actor).hex_decode(),render_phase)
	return result
