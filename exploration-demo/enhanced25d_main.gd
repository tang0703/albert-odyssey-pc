extends "res://landing_event_main.gd"
const EnhancedBundle = preload("res://enhanced25d_loader.gd")
const EnhancedRenderer = preload("res://enhanced25d_renderer.gd")
const MODES_25D: Array[String] = ["enhanced25d","hd","original","marker"]
var enhanced_bundle: Dictionary = {}
var selected_appearance: String = "enhanced25d"
var enhanced_capture: String = ""

func _ready() -> void:
	var directory: String = EnhancedBundle.default_directory()
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--enhanced25d-package="): directory = arg.trim_prefix("--enhanced25d-package=")
		if arg.begins_with("--appearance25d="): selected_appearance = arg.trim_prefix("--appearance25d=")
		if arg.begins_with("--enhanced-capture="): enhanced_capture = arg.trim_prefix("--enhanced-capture=")
	enhanced_bundle = EnhancedBundle.load_bundle(directory)
	if not enhanced_bundle.ok: startup_error = str(enhanced_bundle.error)
	if selected_appearance not in MODES_25D: startup_error = "未知 2.5D 外觀選擇。"
	if enhanced_capture not in ["","walk-down","walk-left","walk-right","walk-up"]: startup_error = "未知短程畫面路線。"
	super._ready()
	if not startup_error.is_empty(): return
	get_window().title = "MAP001 2.5D 起始房間 · 功能候選版"
	change_appearance(selected_appearance)
	if not equipment_capture.is_empty() or not qa_capture_state.is_empty(): qa_pc_mode = true
	if not enhanced_capture.is_empty(): qa_pc_mode = false; paused = false

func workbench_title() -> String: return "MAP001  /  2.5D 起始房間"
func workbench_subtitle() -> String: return "暖光木造室內 · 起始房間外觀替換 · 效能未驗收"

func enhanced_room() -> bool:
	return selected_appearance == "enhanced25d" and int(shown_event.get("scene",8)) == 8 and enhanced_bundle.get("ok",false)

func build_ui() -> void:
	super.build_ui()
	for connection: Dictionary in appearance_select.item_selected.get_connections(): appearance_select.item_selected.disconnect(connection.callable)
	appearance_select.clear()
	for label: String in ["2.5D 強化","既有高清","原作像素","診斷標記"]: appearance_select.add_item(label)
	appearance_select.item_selected.connect(func(index: int) -> void: change_appearance(MODES_25D[index]))
	var holder: Control = map_canvas.get_parent()
	for connection: Dictionary in holder.resized.get_connections(): holder.resized.disconnect(connection.callable)
	holder.resized.connect(layout_appearance)
	layout_appearance()

func layout_appearance() -> void:
	if map_canvas == null: return
	var holder: Control = map_canvas.get_parent()
	var size: Vector2 = Vector2(16,9) if enhanced_room() else Vector2(320,224)
	var target := size*minf(holder.size.x/size.x,holder.size.y/size.y)
	if map_canvas.size != target: map_canvas.size = target
	map_canvas.position = (holder.size-target)/2
	map_canvas.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR if enhanced_room() else CanvasItem.TEXTURE_FILTER_NEAREST
	map_canvas.queue_redraw()

func change_appearance(mode: String) -> void:
	if mode not in MODES_25D or not startup_error.is_empty(): return
	selected_appearance = mode
	appearance_mode = "hd" if mode == "enhanced25d" else mode
	if appearance_select != null: appearance_select.select(MODES_25D.find(mode))
	layout_appearance(); refresh()

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		var key: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		if key == KEY_F2:
			change_appearance(MODES_25D[(MODES_25D.find(selected_appearance)+1)%4]); get_viewport().set_input_as_handled(); return
	super._input(event)

func sync_source_layers() -> void:
	super.sync_source_layers()
	if map_canvas == null: return
	layout_appearance()
	if enhanced_room():
		for layer: Node2D in source_layers.values(): layer.visible = false

func advance_update() -> void:
	if not enhanced_capture.is_empty() and not qa_capture_ready and not replay_mode:
		held_keys.clear()
		var code: int = KEY_DOWN if update_count<12 else {"walk-down":KEY_DOWN,"walk-left":KEY_LEFT,"walk-right":KEY_RIGHT,"walk-up":KEY_UP}[enhanced_capture]
		held_keys[code] = true
	super.advance_update()
	if not enhanced_capture.is_empty() and update_count>=18 and not qa_capture_ready:
		held_keys.clear(); qa_capture_ready = true; paused = true; refresh()

func observe_qa() -> void:
	if not enhanced_capture.is_empty() and not qa_capture_ready: return
	super.observe_qa()

func clear_held_keys() -> void:
	var was_paused: bool = paused
	var audio_paused: bool = audio_player.stream_paused if audio_player != null else false
	super.clear_held_keys()
	if (not enhanced_capture.is_empty() or not equipment_capture.is_empty() or not qa_capture_state.is_empty()) and not qa_capture_ready and not qa_output.is_empty() and startup_error.is_empty():
		paused = was_paused
		if audio_player != null: audio_player.stream_paused = audio_paused
		refresh()

func draw_map(canvas: Control) -> void:
	if not enhanced_room() or shown_event.is_empty(): super.draw_map(canvas); return
	var error: String = EnhancedRenderer.draw(canvas,self,enhanced_bundle)
	if not error.is_empty(): startup_error = error; paused = true; push_error(error)

func refresh() -> void:
	super.refresh()
	if appearance_select != null: appearance_select.select(MODES_25D.find(selected_appearance))
	if transfer_ready and enhanced_room():
		domain_label.text = "起始房間 2.5D · 固定全房間構圖 · 效能未驗收"
		animation_label.text = "F2 四外觀切換 · 52 幀預載\n新增接地陰影；特殊動作沿用來源像素"
	elif transfer_ready and selected_appearance == "enhanced25d": animation_label.text += "\n樓下依配置使用既有高清外觀"

func qa_identity() -> Dictionary:
	var result: Dictionary = super.qa_identity()
	result.schema = "ao_pc_enhanced25d_ui_qa_v1"
	result.selected_appearance = selected_appearance
	result.effective_appearance = "enhanced25d" if enhanced_room() else appearance_mode
	result.enhanced25d_preloaded = enhanced_bundle.get("preloaded",false)
	result.enhanced25d_manifest_sha256 = enhanced_bundle.get("manifest_sha256","")
	result.performance_tested = false
	result.enhanced_capture = enhanced_capture
	return result
