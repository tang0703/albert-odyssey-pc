extends Control
## Diagnostic presentation only. All integer movement belongs to movement_core.

signal update_completed(result: Dictionary)
signal route_completed(route_id: String)

const Bundle = preload("res://package_loader.gd")
const Movement = preload("res://movement_core.gd")
const FIELD_NAMES: Dictionary = {
	"x_word": "X 原始座標", "y_word": "Y 原始座標", "status_word": "狀態", "flags_word": "角色旗標",
	"selector_word": "選擇器", "mode_word": "模式", "dx_word": "X 位移", "dy_word": "Y 位移",
	"slide_x_word": "X 待修正", "slide_y_word": "Y 待修正", "speed_index": "速度索引",
	"heading": "朝向", "shape_index": "形狀索引", "animation_index": "動畫索引",
	"free_direction": "自由方向", "center_flag": "中心格旗標", "contact_bits": "接觸方向",
}
const KEY_DIRECTIONS: Dictionary = {KEY_UP:"up", KEY_W:"up", KEY_DOWN:"down", KEY_S:"down", KEY_LEFT:"left", KEY_A:"left", KEY_RIGHT:"right", KEY_D:"right"}

class MapCanvas extends Control:
	var display: Control
	func _draw() -> void:
		if is_instance_valid(display):
			display.draw_map(self)

var core: RefCounted
var bundle: Dictionary = {}
var state: Dictionary = {}
var expected: Dictionary = {}
var diagnostics: Dictionary = {}
var startup_error: String = ""
var bundle_override: Dictionary = {}
var ui_test_mode: bool = false
var paused: bool = false
var replay_mode: bool = false
var show_overlay: bool = true
var held_keys: Dictionary = {}
var route_index: int = 0
var trace_cursor: int = 0
var update_count: int = 0
var mismatch_count: int = 0
var current_differences: Array[String] = []
var trail: PackedVector2Array = PackedVector2Array()
var tick_seconds: float = 0.016732
var accumulator: float = 0.0
var note: String = "自由行走；僅接受已採樣的查表範圍。"
var stage: PanelContainer
var map_canvas: MapCanvas
var status_label: Label
var position_label: Label
var diagnostics_label: Label
var comparison_label: Label
var boundary_label: Label
var domain_label: Label
var mode_select: OptionButton
var route_select: OptionButton
var play_button: Button
var step_button: Button
var reset_button: Button
var overlay_button: Button
var field_values: Dictionary = {}
var verified_indices: Dictionary = {}

# QA timing and presentation are separate. No image access during measured soak.
var qa_output: String = ""
var qa_report: String = ""
var qa_target: Vector2i = Vector2i.ZERO
var qa_soak_seconds: float = 0.0
var qa_warmup_seconds: float = 15.0
var qa_started_usec: int = 0
var qa_first_frame_usec: int = 0
var qa_verified_surface_usec: int = 0
var qa_last_pixel_read_usec: int = 0
var qa_measure_started_usec: int = 0
var qa_previous_usec: int = 0
var qa_next_sample: float = 0.0
var qa_surface_verified: bool = false
var qa_stable_since_usec: int = 0
var qa_surface_checks: int = 0
var qa_ready_written: bool = false
var qa_last_surface_size: Vector2i = Vector2i.ZERO
var qa_verified_pixel_size: Vector2i = Vector2i.ZERO
var qa_pixel_reads_before_measurement: int = 0
var qa_pixel_reads_after_measurement: int = 0
var qa_window_corrections: Array[Dictionary] = []
var qa_surface_changes: Array[Dictionary] = []
const QA_SURFACE_STABILITY_SECONDS: float = 0.25
var qa_finishing: bool = false
var qa_frames_ms: Array[float] = []
var qa_samples: Array[Dictionary] = []
var qa_spikes: Array[Dictionary] = []
var qa_routes_completed: int = 0
var qa_mismatches: int = 0

func _ready() -> void:
	qa_started_usec = Time.get_ticks_usec()
	var folder: String = Bundle.default_directory()
	if not ui_test_mode:
		Engine.max_fps = 60
		for arg: String in OS.get_cmdline_user_args():
			if arg.begins_with("--scene-package="): folder = arg.trim_prefix("--scene-package=")
			if arg.begins_with("--qa-output="): qa_output = arg.trim_prefix("--qa-output=")
			if arg.begins_with("--qa-report="): qa_report = arg.trim_prefix("--qa-report=")
			if arg.begins_with("--qa-soak-seconds="): qa_soak_seconds = float(arg.trim_prefix("--qa-soak-seconds="))
			if arg.begins_with("--qa-warmup-seconds="): qa_warmup_seconds = float(arg.trim_prefix("--qa-warmup-seconds="))
			if arg.begins_with("--qa-size="):
				var parts: PackedStringArray = arg.trim_prefix("--qa-size=").to_lower().split("x")
				if parts.size() == 2: qa_target = Vector2i(int(parts[0]), int(parts[1]))
	if qa_target.x > 0 and qa_target.y > 0:
		lock_qa_window_size()
	bundle = bundle_override if not bundle_override.is_empty() else Bundle.load_bundle(folder)
	if not bundle.get("ok", false):
		startup_error = str(bundle.get("error", "資料包載入失敗"))
	else:
		core = Movement.new()
		var configured: Dictionary = core.configure(bundle.profile, bundle.flags)
		if not configured.ok: startup_error = str(configured.error)
		else:
			state = core.initial_state()
			tick_seconds = float(bundle.profile.logical_tick_seconds.numerator) / float(bundle.profile.logical_tick_seconds.denominator)
			for index: Variant in bundle.profile.verified_query_indices: verified_indices[int(index)] = true
	var ui_theme := Theme.new()
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["Microsoft JhengHei", "Microsoft YaHei", "Noto Sans CJK TC"])
	ui_theme.default_font = font
	ui_theme.default_font_size = 24
	theme = ui_theme
	build_ui()
	if not startup_error.is_empty():
		paused = true
		note = "資料拒絕載入：" + startup_error
		for control: Control in [mode_select, route_select, play_button, step_button, reset_button, overlay_button]: control.set("disabled", true)
	else: reset_state()
	refresh()
	get_window().focus_exited.connect(clear_held_keys)
	if not qa_output.is_empty() or not qa_report.is_empty():
		if not startup_error.is_empty():
			finish_qa(startup_error)
			return
		replay_mode = true
		mode_select.select(1)
		reset_state()
		paused = false
		RenderingServer.frame_post_draw.connect(qa_check_rendered_surface)

func panel_style(color: String) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = Color(color)
	style.border_color = Color("304954")
	style.set_border_width_all(1)
	style.set_corner_radius_all(10)
	style.content_margin_left = 20
	style.content_margin_right = 20
	style.content_margin_top = 14
	style.content_margin_bottom = 14
	return style

func make_label(text: String, font_size: int = 24, color: String = "dce7e9") -> Label:
	var item := Label.new()
	item.text = text
	item.add_theme_font_size_override("font_size", font_size)
	item.add_theme_color_override("font_color", Color(color))
	return item

func make_button(text: String, callback: Callable) -> Button:
	var item := Button.new()
	item.text = text
	item.custom_minimum_size = Vector2(0, 52)
	for pair: Array in [["normal", "203c49"], ["hover", "2b5362"], ["pressed", "397182"]]:
		var style: StyleBoxFlat = panel_style(pair[1])
		style.content_margin_top = 8
		style.content_margin_bottom = 8
		item.add_theme_stylebox_override(pair[0], style)
	item.pressed.connect(callback)
	item.focus_mode = Control.FOCUS_CLICK
	return item

func build_ui() -> void:
	var background := ColorRect.new()
	background.color = Color("0b151d")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(background)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for edge: String in ["left", "right"]: margin.add_theme_constant_override("margin_" + edge, 32)
	for edge: String in ["top", "bottom"]: margin.add_theme_constant_override("margin_" + edge, 22)
	add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 14)
	margin.add_child(column)
	var heading := HBoxContainer.new()
	column.add_child(heading)
	var title := make_label("MAP001  /  行走驗證台", 38, "eef4ed")
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_child(title)
	heading.add_child(make_label("固定鏡頭 · 原始整數座標 · 本地來源", 23, "86a6b4"))
	domain_label = make_label("指定區域驗證，不代表完整地圖或 Stage B 通過", 23, "9eb9c3")
	column.add_child(domain_label)
	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 22)
	column.add_child(body)
	var left := VBoxContainer.new()
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(left)
	var info := HBoxContainer.new()
	left.add_child(info)
	position_label = make_label("", 24)
	position_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_child(position_label)
	boundary_label = make_label("", 24, "ffd099")
	info.add_child(boundary_label)
	stage = PanelContainer.new()
	stage.size_flags_vertical = Control.SIZE_EXPAND_FILL
	stage.add_theme_stylebox_override("panel", panel_style("111f27"))
	left.add_child(stage)
	var map_holder := Control.new()
	map_holder.size_flags_vertical = Control.SIZE_EXPAND_FILL
	stage.add_child(map_holder)
	map_canvas = MapCanvas.new()
	map_canvas.display = self
	map_canvas.clip_contents = true
	map_canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE
	map_canvas.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	map_holder.add_child(map_canvas)
	map_holder.resized.connect(func() -> void:
		var factor: float = minf(map_holder.size.x / 320.0, map_holder.size.y / 224.0)
		map_canvas.size = Vector2(320, 224) * factor
		map_canvas.position = (map_holder.size - map_canvas.size) * 0.5
		map_canvas.queue_redraw())
	left.add_child(make_label("青格：已驗證　紅格：0x80 診斷　金線：原作軌跡　未標色：未驗證", 21, "9ab7c2"))
	var sidebar := PanelContainer.new()
	sidebar.custom_minimum_size.x = 612
	sidebar.add_theme_stylebox_override("panel", panel_style("142630"))
	body.add_child(sidebar)
	var side := VBoxContainer.new()
	side.add_theme_constant_override("separation", 10)
	sidebar.add_child(side)
	var selectors := HBoxContainer.new()
	side.add_child(selectors)
	mode_select = OptionButton.new()
	mode_select.add_item("自由行走")
	mode_select.add_item("原作軌跡對照")
	mode_select.custom_minimum_size = Vector2(210, 48)
	mode_select.item_selected.connect(change_mode)
	selectors.add_child(mode_select)
	route_select = OptionButton.new()
	route_select.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for trace: Dictionary in bundle.get("traces", []): route_select.add_item(str(trace.label))
	route_select.item_selected.connect(select_route)
	selectors.add_child(route_select)
	var actions := HBoxContainer.new()
	side.add_child(actions)
	play_button = make_button("暫停", toggle_pause)
	step_button = make_button("單步 .", single_step)
	reset_button = make_button("重設 R", reset_state)
	overlay_button = make_button("疊圖 F1", toggle_overlay)
	for item: Button in [play_button, step_button, reset_button, overlay_button]:
		item.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		actions.add_child(item)
	status_label = make_label("", 24, "b2e7d4")
	side.add_child(status_label)
	comparison_label = make_label("", 22, "9eb9c3")
	side.add_child(comparison_label)
	var header := make_label("狀態欄位                         核心  /  原作", 21, "83a6b3")
	side.add_child(header)
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("v_separation", 2)
	grid.add_theme_constant_override("h_separation", 20)
	side.add_child(grid)
	for key: String in FIELD_NAMES:
		var field_label := make_label(str(FIELD_NAMES[key]) + "  " + key, 18, "9fb7c1")
		field_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		grid.add_child(field_label)
		var value := make_label("—", 19, "dce7e9")
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		grid.add_child(value)
		field_values[key] = value
	diagnostics_label = make_label("", 20, "b5c6ca")
	diagnostics_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	diagnostics_label.size_flags_vertical = Control.SIZE_EXPAND_FILL
	side.add_child(diagnostics_label)
	var footer := make_label("方向鍵 / WASD 移動　Space 暫停　. 單步　R 重設　F1 疊圖　｜　多方向同按不移動；範圍外為「測試邊界」", 23, "89a6b3")
	footer.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(footer)

func clear_held_keys() -> void:
	held_keys.clear()

func _input(event: InputEvent) -> void:
	if not event is InputEventKey or not startup_error.is_empty(): return
	var key_event: InputEventKey = event
	var key: int = key_event.physical_keycode if key_event.physical_keycode != 0 else key_event.keycode
	if KEY_DIRECTIONS.has(key):
		if key_event.pressed: held_keys[key] = true
		else: held_keys.erase(key)
		get_viewport().set_input_as_handled()
		return
	if not key_event.pressed or key_event.echo: return
	match key:
		KEY_SPACE: toggle_pause()
		KEY_PERIOD: single_step()
		KEY_R: reset_state()
		KEY_F1: toggle_overlay()
		KEY_1, KEY_2, KEY_3, KEY_4:
			var selected: int = key - KEY_1
			route_select.select(selected)
			select_route(selected)
		_: return
	get_viewport().set_input_as_handled()

func active_directions() -> Array[String]:
	var result: Array[String] = []
	for key: int in held_keys:
		var direction: String = KEY_DIRECTIONS[key]
		if not result.has(direction): result.append(direction)
	return result

func _process(delta: float) -> void:
	if not ui_test_mode: advance_time(delta)
	if not qa_output.is_empty() or not qa_report.is_empty(): observe_qa()

func advance_time(delta: float) -> void:
	if paused or not startup_error.is_empty(): return
	accumulator += delta
	while accumulator + 0.000000001 >= tick_seconds and not paused:
		accumulator -= tick_seconds
		advance_update()

func advance_update() -> void:
	if state.is_empty() or not startup_error.is_empty(): return
	var result: Dictionary
	var next_expected: Dictionary = {}
	if replay_mode:
		var trace: Dictionary = bundle.traces[route_index]
		if trace_cursor >= trace.updates.size(): return
		var record: Dictionary = trace.updates[trace_cursor]
		result = core.step_game_input(state, int(record.game_pad_word))
		next_expected = record.expected.duplicate(true)
	else:
		var directions: Array[String] = active_directions()
		if directions.size() > 1:
			diagnostics = {"applied": false, "reason": "multiple_directions"}
			note = "多方向同按：整次更新保留，待修正位移也不消耗。"
			refresh()
			return
		result = core.step(state, "none" if directions.is_empty() else directions[0])
	if not result.ok:
		startup_error = str(result.error)
		paused = true
		note = "核心拒絕更新：" + startup_error
		refresh()
		return
	var presentation_error: String = prepare_update_presentation(result)
	if not presentation_error.is_empty():
		startup_error = presentation_error
		paused = true
		note = "演出拒絕更新：" + startup_error
		refresh()
		return
	state = result.state
	expected = next_expected
	if replay_mode: trace_cursor += 1
	diagnostics = result.diagnostics
	update_count += 1
	current_differences.clear()
	for key: String in expected:
		if int(state[key]) != int(expected[key]): current_differences.append(key)
	if not current_differences.is_empty():
		mismatch_count += 1
		qa_mismatches += 1
	note = "測試邊界：未驗證格，整次更新保留。" if diagnostics.get("reason") == "test_boundary" else "核心已更新；0x80 格僅為此場景診斷，並非通用牆壁規則。"
	trail.append(world_position(state))
	if trail.size() > 2048: trail.remove_at(0)
	update_completed.emit(result)
	if replay_mode and trace_cursor >= bundle.traces[route_index].updates.size():
		paused = true
		note = "軌跡完成。17 欄逐更新對照：%d 次差異。" % mismatch_count
		route_completed.emit(str(bundle.traces[route_index].id))
		if qa_soak_seconds > 0:
			qa_routes_completed += 1
			route_index = (route_index + 1) % bundle.traces.size()
			route_select.select(route_index)
			reset_state()
			paused = false
	refresh()

func prepare_update_presentation(_result: Dictionary) -> String:
	# Optional visual models validate before the movement state is committed.
	# The original marker entry has no additional presentation state.
	return ""

func change_mode(index: int) -> void:
	replay_mode = index == 1
	paused = replay_mode
	reset_state()

func select_route(index: int) -> void:
	route_index = index
	replay_mode = true
	mode_select.select(1)
	paused = true
	reset_state()

func reset_state() -> void:
	if core == null or not startup_error.is_empty(): return
	state = bundle.traces[route_index].initial_state.duplicate(true) if replay_mode else core.initial_state()
	expected = state.duplicate(true) if replay_mode else {}
	diagnostics.clear()
	current_differences.clear()
	trace_cursor = 0
	update_count = 0
	mismatch_count = 0
	accumulator = 0
	trail = PackedVector2Array([world_position(state)])
	note = "原作軌跡待播放；僅輸入序列驅動核心，原作狀態只供對照。" if replay_mode else "自由行走；僅接受已採樣的查表範圍。"
	refresh()

func toggle_pause() -> void:
	if not startup_error.is_empty(): return
	if replay_mode and trace_cursor >= bundle.traces[route_index].updates.size(): reset_state()
	paused = not paused
	accumulator = 0
	refresh()

func single_step() -> void:
	if not startup_error.is_empty(): return
	paused = true
	accumulator = 0
	advance_update()

func toggle_overlay() -> void:
	show_overlay = not show_overlay
	refresh()

func refresh() -> void:
	if status_label == null: return
	play_button.text = "播放" if paused else "暫停"
	status_label.text = ("原作對照" if replay_mode else "自由行走") + (" · 已暫停" if paused else " · 執行中")
	comparison_label.text = "更新 %d　差異 %d 次 / 17 欄" % [update_count, mismatch_count]
	if replay_mode and not bundle.get("traces", []).is_empty(): comparison_label.text += "　%d / %d" % [trace_cursor, bundle.traces[route_index].updates.size()]
	boundary_label.text = "測試邊界" if diagnostics.get("reason") == "test_boundary" else ("多方向：不移動" if diagnostics.get("reason") == "multiple_directions" else "")
	domain_label.text = "MAP001 指定區域 · %d 個已驗證查表格 · 320 × 224 固定視窗 · 非完整地圖驗收" % verified_indices.size()
	diagnostics_label.text = note
	if not state.is_empty():
		var xy: Vector2 = world_position(state)
		position_label.text = "世界座標  %.2f, %.2f　｜　朝向 %d" % [xy.x, xy.y, int(state.heading)]
		if diagnostics.has("lookups"): diagnostics_label.text += "\n本次查表 %d 筆 · 接觸 0x%02X · 中心 0x%02X" % [diagnostics.lookups.size(), int(state.contact_bits), int(state.center_flag)]
	for key: String in field_values:
		var value: Label = field_values[key]
		value.text = "%04X / %04X" % [int(state[key]), int(expected[key])] if state.has(key) and expected.has(key) else ("%04X / —" % int(state[key]) if state.has(key) else "—")
		value.add_theme_color_override("font_color", Color("ffac9a" if current_differences.has(key) else "dce7e9"))
	map_canvas.queue_redraw()

func world_position(value: Dictionary) -> Vector2:
	return Vector2(Movement.signed16(int(value.x_word)), Movement.signed16(int(value.y_word))) / 16.0

func draw_map(canvas: Control) -> void:
	canvas.draw_rect(Rect2(Vector2.ZERO, canvas.size), Color("0c141a"))
	if state.is_empty(): return
	var zoom: float = canvas.size.x / 320.0
	var camera := Vector2(float(bundle.data.camera[0]), float(bundle.data.camera[1]))
	var whole := Rect2(Vector2.ZERO, canvas.size)
	for index: int in [1, 0]: canvas.draw_texture_rect(bundle.textures[index], whole, false)
	if show_overlay:
		for index: int in verified_indices:
			@warning_ignore("integer_division")
			var cell := Vector2(index % 256, index / 256) * 8.0 - camera
			var cell_rect := Rect2(cell * zoom, Vector2.ONE * 8.0 * zoom)
			var blocked: bool = bool(int(bundle.flags[index]) & 0x80)
			canvas.draw_rect(cell_rect, Color(1.0, 0.35, 0.25, 0.27) if blocked else Color(0.25, 0.87, 0.8, 0.18))
			canvas.draw_rect(cell_rect, Color(0.3, 0.8, 0.76, 0.45), false, maxf(1, zoom * 0.2))
		var original := PackedVector2Array()
		original.append((world_position(bundle.traces[route_index].initial_state) - camera) * zoom)
		for record: Dictionary in bundle.traces[route_index].updates: original.append((world_position(record.expected) - camera) * zoom)
		if original.size() >= 2: canvas.draw_polyline(original, Color(1.0, 0.81, 0.39, 0.6), maxf(1.5, zoom * 0.6), true)
		if trail.size() >= 2:
			var transformed := PackedVector2Array()
			for point: Vector2 in trail: transformed.append((point - camera) * zoom)
			canvas.draw_polyline(transformed, Color("58e0dc"), maxf(1.5, zoom * 0.4), true)
	var origin: Vector2 = (world_position(state) - camera) * zoom
	var shape: Array = bundle.profile.shape_raw
	if show_overlay:
		var rect := Rect2(origin + Vector2(float(shape[0]), float(shape[1])) * zoom / 16.0, Vector2(float(shape[3]), float(shape[4])) * zoom / 16.0)
		canvas.draw_rect(rect, Color(0.26, 0.93, 0.88, 0.15))
		canvas.draw_rect(rect, Color("61eadb"), false, maxf(1.5, zoom * 0.5))
		for lookup: Dictionary in diagnostics.get("lookups", []):
			var index: int = int(lookup.index)
			@warning_ignore("integer_division")
			var cell := Vector2(index % 256, index / 256) * 8.0 - camera
			canvas.draw_rect(Rect2(cell * zoom, Vector2.ONE * 8.0 * zoom), Color("ffe4ac"), false, maxf(1.5, zoom * 0.4))
	draw_player(canvas, origin, zoom)
	if replay_mode and not expected.is_empty():
		var observed: Vector2 = (world_position(expected) - camera) * zoom
		canvas.draw_arc(observed, zoom * 4.5, 0, TAU, 24, Color("ffd18a"), maxf(1.5, zoom * 0.4), true)

func draw_player(canvas: Control, origin: Vector2, zoom: float) -> void:
	canvas.draw_circle(origin, 3.0 * zoom, Color("07161b"))
	canvas.draw_circle(origin, 2.0 * zoom, Color("dcfff2"))
	var direction := Vector2.from_angle(float(state.heading) * PI / 4.0)
	canvas.draw_line(origin + direction * zoom * 3, origin + direction * zoom * 10, Color("fcffff"), maxf(2, zoom * 0.7), true)
	canvas.draw_circle(origin + direction * zoom * 10, zoom, Color("fcffff"))

func lock_qa_window_size() -> void:
	# Window-only QA policy. A late Windows DPI/monitor event must not silently
	# change the rendered workload. Do not alter desktop or global DPI settings.
	if qa_target.x <= 0 or qa_target.y <= 0: return
	var window: Window = get_window()
	window.mode = Window.MODE_WINDOWED
	window.borderless = true
	window.unresizable = true
	window.content_scale_mode = Window.CONTENT_SCALE_MODE_CANVAS_ITEMS
	window.content_scale_aspect = Window.CONTENT_SCALE_ASPECT_KEEP
	window.content_scale_size = Vector2i(1920, 1080)
	window.content_scale_factor = 1.0
	window.min_size = qa_target
	window.max_size = qa_target
	window.position = Vector2i.ZERO
	window.size = qa_target

func qa_actual_surface_size() -> Vector2i:
	# On Godot 4.7.2 Windows canvas_items, ViewportTexture.get_width()/get_size()
	# can report the stretch factor twice while get_image() has correct pixels.
	# Monitor the physical client size instead, and verify GPU pixels at both ends.
	return DisplayServer.window_get_size(get_window().get_window_id())

func qa_surface_size_issue(actual: Vector2i) -> String:
	if actual.x <= 0 or actual.y <= 0: return "Rendered QA surface is empty"
	if qa_target != Vector2i.ZERO and actual != qa_target:
		return "Rendered QA size drifted: actual %s, requested %s" % [actual, qa_target]
	if qa_target != Vector2i.ZERO and get_window().size != qa_target:
		return "QA window size drifted: actual %s, requested %s" % [get_window().size, qa_target]
	if qa_target != Vector2i.ZERO and (get_window().content_scale_mode != Window.CONTENT_SCALE_MODE_CANVAS_ITEMS or get_window().content_scale_aspect != Window.CONTENT_SCALE_ASPECT_KEEP or get_window().content_scale_size != Vector2i(1920,1080) or not is_equal_approx(get_window().content_scale_factor, 1.0)):
		return "QA canvas scaling configuration changed"
	return ""

func qa_read_pixels() -> Image:
	# finish_qa closes timing before its last read. No measured frame includes
	# GPU readback, PNG compression, report sorting or report/file I/O.
	if qa_measure_started_usec > 0 and not qa_finishing:
		push_error("GPU readback rejected during measured soak")
		return null
	if qa_measure_started_usec > 0: qa_pixel_reads_after_measurement += 1
	else: qa_pixel_reads_before_measurement += 1
	qa_last_pixel_read_usec = Time.get_ticks_usec()
	return get_viewport().get_texture().get_image()

func qa_check_rendered_surface() -> void:
	if qa_finishing: return
	var now: int = Time.get_ticks_usec()
	if qa_first_frame_usec == 0: qa_first_frame_usec = now
	var actual: Vector2i = qa_actual_surface_size()
	qa_surface_checks += 1
	if actual != qa_last_surface_size:
		qa_surface_changes.append({"seconds_from_start":float(now - qa_started_usec) / 1000000.0, "size":[actual.x,actual.y], "measuring":qa_measure_started_usec > 0})
		qa_last_surface_size = actual
	var issue: String = qa_surface_size_issue(actual)
	if not issue.is_empty():
		qa_surface_verified = false
		qa_stable_since_usec = 0
		if qa_measure_started_usec > 0:
			finish_qa(issue)
			return
		qa_window_corrections.append({"seconds_from_start":float(now - qa_started_usec) / 1000000.0, "surface":[actual.x,actual.y], "window":[get_window().size.x,get_window().size.y]})
		lock_qa_window_size()
		return
	if qa_surface_verified: return
	if qa_stable_since_usec == 0:
		qa_stable_since_usec = now
		return
	if float(now - qa_stable_since_usec) / 1000000.0 < QA_SURFACE_STABILITY_SECONDS: return
	# The one startup pixel read occurs only before measurement. Later checks
	# use dimensions, including every rendered frame throughout a soak.
	if qa_measure_started_usec > 0:
		finish_qa("QA surface lost verification after measurement began")
		return
	var image: Image = qa_read_pixels()
	if image == null or image.is_empty():
		finish_qa("Actual rendered surface has no pixels")
		return
	issue = qa_surface_size_issue(image.get_size())
	if not issue.is_empty():
		finish_qa(issue)
		return
	qa_surface_verified = true
	qa_verified_pixel_size = image.get_size()
	if qa_ready_written: return
	qa_verified_surface_usec = now
	var marker_path: String = qa_report
	if marker_path.is_empty(): marker_path = qa_output if qa_soak_seconds > 0 else qa_output + ".json"
	var marker := FileAccess.open(marker_path + ".ready.json", FileAccess.WRITE)
	if marker == null:
		finish_qa("Cannot write first-frame ready marker")
		return
	marker.store_string(JSON.stringify({"schema":"ao_pc_exploration_first_frame_v1", "ticks_usec":qa_verified_surface_usec, "first_draw_ticks_usec":qa_first_frame_usec, "actual_viewport":[image.get_width(), image.get_height()], "surface_verified":true, "stability_seconds":QA_SURFACE_STABILITY_SECONDS}))
	marker.close()
	qa_ready_written = true

func observe_qa() -> void:
	if qa_finishing: return
	var now: int = Time.get_ticks_usec()
	var startup_elapsed: float = float(now - qa_started_usec) / 1000000.0
	if not qa_surface_verified:
		if startup_elapsed > 20: finish_qa("No verified rendered surface; headless is unsuitable for visual QA")
		return
	var size_issue: String = qa_surface_size_issue(qa_actual_surface_size())
	if not size_issue.is_empty():
		qa_surface_verified = false
		if qa_measure_started_usec > 0: finish_qa(size_issue)
		return
	if qa_soak_seconds <= 0:
		if startup_elapsed >= 2:
			qa_finishing = true
			await RenderingServer.frame_post_draw
			var image: Image = qa_read_pixels()
			var issue: String = "Screenshot surface is empty" if image == null or image.is_empty() else qa_surface_size_issue(image.get_size())
			if not issue.is_empty():
				qa_finishing = false
				qa_surface_verified = false
				finish_qa(issue)
				return
			qa_verified_pixel_size = image.get_size()
			var code: Error = image.save_png(qa_output)
			qa_finishing = false
			finish_qa("" if code == OK else "PNG save failed: %s" % error_string(code))
		return
	if startup_elapsed < qa_warmup_seconds: return
	if qa_measure_started_usec == 0:
		qa_measure_started_usec = now
		qa_previous_usec = now
		return
	var elapsed: float = float(now - qa_measure_started_usec) / 1000000.0
	var ms: float = float(now - qa_previous_usec) / 1000.0
	qa_previous_usec = now
	qa_frames_ms.append(ms)
	if ms > 50: qa_spikes.append({"seconds": elapsed, "frame_ms": ms, "route": str(bundle.traces[route_index].id), "update": trace_cursor})
	if elapsed >= qa_next_sample:
		var window_size: Vector2i = qa_actual_surface_size()
		qa_samples.append({"seconds": elapsed, "engine_static_memory_bytes": Performance.get_monitor(Performance.MEMORY_STATIC), "engine_video_memory_bytes": Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED), "node_count": Performance.get_monitor(Performance.OBJECT_NODE_COUNT), "frame_ms": ms, "fps_monitor": Performance.get_monitor(Performance.TIME_FPS), "routes_completed": qa_routes_completed, "window_pixels":[window_size.x,window_size.y]})
		qa_next_sample = floor(elapsed) + 1.0
	if elapsed >= qa_soak_seconds: finish_qa()

func finish_qa(error: String = "") -> void:
	if qa_finishing: return
	qa_finishing = true
	var actual: Vector2i = qa_verified_pixel_size
	if DisplayServer.get_name() != "headless" and qa_surface_checks > 0:
		var final_pixels: Image = qa_read_pixels()
		if final_pixels != null and not final_pixels.is_empty(): actual = final_pixels.get_size()
		else:
			qa_surface_verified = false
			if error.is_empty(): error = "Final GPU pixel verification failed"
	var size_issue: String = qa_surface_size_issue(actual)
	if not size_issue.is_empty():
		qa_surface_verified = false
		if error.is_empty(): error = size_issue
	var report_path: String = qa_report
	if report_path.is_empty(): report_path = qa_output if qa_soak_seconds > 0 else qa_output + ".json"
	var sorted_frames: Array[float] = qa_frames_ms.duplicate()
	sorted_frames.sort()
	var duration: float = float(qa_previous_usec - qa_measure_started_usec) / 1000000.0 if qa_measure_started_usec > 0 else 0.0
	var p95: float = sorted_frames[clampi(int(ceil(sorted_frames.size() * 0.95)) - 1, 0, sorted_frames.size() - 1)] if not sorted_frames.is_empty() else 0.0
	var avg: float = float(qa_frames_ms.size()) / duration if duration > 0 else 0.0
	var memory_start: Array[float] = []
	var memory_end: Array[float] = []
	var node_start: Array[float] = []
	var node_end: Array[float] = []
	var segment: int = maxi(1, int(ceil(qa_samples.size() * 0.2)))
	for index: int in qa_samples.size():
		if index < segment:
			memory_start.append(float(qa_samples[index].engine_static_memory_bytes))
			node_start.append(float(qa_samples[index].node_count))
		if index >= qa_samples.size() - segment:
			memory_end.append(float(qa_samples[index].engine_static_memory_bytes))
			node_end.append(float(qa_samples[index].node_count))
	var initial_memory: float = median(memory_start)
	var final_memory: float = median(memory_end)
	var growth: float = final_memory / initial_memory - 1.0 if initial_memory > 0 else 0.0
	var report: Dictionary = {"schema":"ao_pc_exploration_ui_qa_v1", "mode":"soak" if qa_soak_seconds > 0 else "screenshot", "error":error,
		"passed":error.is_empty() and qa_surface_verified and qa_mismatches == 0, "surface_verified":qa_surface_verified,
		"actual_viewport": [actual.x, actual.y], "requested_viewport":[qa_target.x,qa_target.y],
		"surface_size_checks":qa_surface_checks, "surface_size_changes":qa_surface_changes, "warmup_window_corrections":qa_window_corrections,
		"surface_size_check_method":"Physical client/window dimensions and canvas scale configuration every frame; actual GPU pixels before and after timing",
		"pixel_reads_before_measurement":qa_pixel_reads_before_measurement, "pixel_reads_after_measurement":qa_pixel_reads_after_measurement, "pixel_reads_during_measurement":0,
		"startup_surface_stability_seconds":QA_SURFACE_STABILITY_SECONDS,
		"startup_to_first_render_ms":float(qa_first_frame_usec - qa_started_usec) / 1000.0 if qa_first_frame_usec > 0 else null,
		"startup_to_verified_surface_ms":float(qa_verified_surface_usec - qa_started_usec) / 1000.0 if qa_verified_surface_usec > 0 else null,
		"measurement_started_ticks_usec":qa_measure_started_usec, "measurement_finished_ticks_usec":qa_previous_usec, "final_pixel_verification_ticks_usec":qa_last_pixel_read_usec,
		"startup_note":"First render is the first frame_post_draw callback; verified-surface ready additionally requires 250ms stable dimensions. Neither is an OS cold-cache claim", "reference_id":bundle.get("data", {}).get("reference_id", ""),
		"measured_seconds":duration, "warmup_seconds":qa_warmup_seconds, "samples":qa_samples, "frame_spikes_over_50ms":qa_spikes,
		"memory_first_segment_median_bytes":initial_memory, "memory_last_segment_median_bytes":final_memory, "memory_median_growth_ratio":growth,
		"nodes_first_segment_median":median(node_start), "nodes_last_segment_median":median(node_end),
		"memory_target_met":growth <= 0.1 if qa_soak_seconds > 0 else null, "nodes_stable":median(node_end) <= median(node_start) if qa_soak_seconds > 0 else null,
		"frame_intervals_ms":qa_frames_ms, "average_fps":avg, "p95_frame_ms":p95, "max_frame_ms":sorted_frames.back() if not sorted_frames.is_empty() else 0,
		"performance_target_met":avg >= 59 and p95 <= 20 if qa_soak_seconds > 0 else null,
		"routes_completed":qa_routes_completed, "mismatched_updates":qa_mismatches,
		"memory_scope":"Godot allocator memory only; process/GPU memory must be collected externally", "screenshots_during_measurement":0}
	report.merge(qa_identity(), true)
	var file := FileAccess.open(report_path, FileAccess.WRITE)
	if file == null:
		push_error("Cannot write QA report: " + report_path)
		get_tree().quit(2)
		return
	file.store_string(JSON.stringify(report, "\t"))
	file.close()
	print("EXPLORATION_QA " + JSON.stringify({"report":report_path, "passed":report.passed, "average_fps":avg, "p95_frame_ms":p95}))
	get_tree().quit(0 if report.passed else 2)

func qa_identity() -> Dictionary:
	return {}

func median(values: Array[float]) -> float:
	if values.is_empty(): return 0.0
	values.sort()
	var middle: int = int(values.size() / 2.0)
	return values[middle] if values.size() % 2 else (values[middle - 1] + values[middle]) / 2.0
