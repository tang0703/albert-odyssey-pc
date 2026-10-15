extends "res://room_main.gd"
signal event_finished(run_number: int)
const EventCore = preload("res://event_core.gd")
const EventBundle = preload("res://event_loader.gd")
const EventVisual = preload("res://event_visual.gd")
const Dialogue = preload("res://event_dialogue.gd")
var event_bundle: Dictionary = {}
var event_core: RefCounted
var dialogue := Dialogue.new()
var audio_player: AudioStreamPlayer
var audio_loaded: bool = false
var audio_started: bool = false
var event_queue: Array[Dictionary] = []
var shown_event: Dictionary = {}
var display_advancing: bool = false
var dialogue_panel: PanelContainer
var dialogue_text: Label
var dialogue_page: Label
var continue_button: Button
var completed_events: int = 0
var source_pad_previous: int = 0
var qa_pc_mode: bool = false
var qa_page_age: int = 0
var qa_auto_update: int = 0
var qa_capture_page: int = -1
var qa_capture_ready: bool = false
var source_replay_completed: bool = false
var dialogue_closing: bool = false

func _ready() -> void:
	super._ready()
	if not startup_error.is_empty(): return
	var directory: String = EventBundle.default_directory()
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--event-package="): directory = arg.trim_prefix("--event-package=")
		if arg.begins_with("--event-page="): qa_capture_page = int(arg.trim_prefix("--event-page="))
	event_bundle = EventBundle.load_bundle(directory,bundle.profile,bundle.flags,character_bundle,room_bundle.data)
	if not event_bundle.get("ok",false): startup_error = str(event_bundle.error); paused = true; refresh(); return
	event_core = EventCore.new()
	var configured: Dictionary = event_core.configure(event_bundle.data,bundle.profile,bundle.flags,character_bundle,room_bundle.data)
	if not configured.ok: startup_error = str(configured.error); paused = true; refresh(); return
	var cirrus: Dictionary = room_bundle.frames["6:46"].duplicate(true)
	for key: String in ["file","anchor","dimensions","texture"]: cirrus[key] = event_bundle.sprites.cirrus_71[key]
	cirrus.image_index = 71
	room_bundle.frames["6:71"] = cirrus
	var layer := SourceLayer.new()
	layer.name = "expression"
	map_canvas.add_child(layer)
	source_layers.expression = layer
	audio_player = AudioStreamPlayer.new()
	audio_player.stream = event_bundle.audio
	audio_player.volume_db = -8.0
	add_child(audio_player)
	audio_loaded = true
	route_select.clear()
	bundle.traces = []
	var labels: Array[String] = ["中央接近","上側接近","下側接近","離開再次進入","等待確認","長按確認"]
	for i: int in EventBundle.ROUTES.size():
		route_select.add_item(labels[i])
		var reference: Dictionary = event_bundle.references[i]
		var trace: Dictionary = {"id":EventBundle.ROUTES[i],"label":labels[i],"initial_state":EventCore.project(str(reference.initial_state.player).hex_decode()),"updates":[]}
		for row: Dictionary in reference.updates:
			trace.updates.append({"game_pad_word":row.input.pad,"expected":EventCore.project(str(row.expected.player).hex_decode())})
		bundle.traces.append(trace)
	get_window().title = "MAP001 樓梯前 Cirrus 事件"
	qa_pc_mode = qa_soak_seconds > 0 or qa_capture_page >= 0
	if qa_pc_mode: replay_mode = false; mode_select.select(0)
	show_overlay = false
	reset_state()
	refresh()

func workbench_title() -> String:
	return "MAP001  /  樓梯前的呼喚"

func workbench_subtitle() -> String:
	return "Cirrus 原作事件 · 高清繁中對話"

func build_ui() -> void:
	super.build_ui()
	dialogue_panel = PanelContainer.new()
	dialogue_panel.add_theme_stylebox_override("panel",panel_style("172d40"))
	dialogue_panel.z_index = 2000
	dialogue_panel.visible = false
	map_canvas.add_child(dialogue_panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation",10)
	dialogue_panel.add_child(column)
	var heading := HBoxContainer.new()
	column.add_child(heading)
	var speaker := make_label("CIRRUS",26,"f5dba2")
	speaker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_child(speaker)
	dialogue_page = make_label("",22,"a9c4d1")
	heading.add_child(dialogue_page)
	dialogue_text = make_label("",30,"f0f5f7")
	dialogue_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	dialogue_text.custom_minimum_size.y = 76
	column.add_child(dialogue_text)
	continue_button = make_button("繼續  Enter",request_confirmation)
	continue_button.focus_mode = Control.FOCUS_NONE
	continue_button.size_flags_horizontal = Control.SIZE_SHRINK_END
	column.add_child(continue_button)
	map_canvas.resized.connect(_dialogue_layout)

func _dialogue_layout() -> void:
	if dialogue_panel == null: return
	dialogue_panel.position = Vector2(20,18)
	dialogue_panel.size = Vector2(maxf(200,map_canvas.size.x-40),0)

func request_confirmation() -> void:
	if not paused and startup_error.is_empty(): dialogue.click()

func _input(event: InputEvent) -> void:
	if event is InputEventKey:
		var key: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		if key in [KEY_ENTER,KEY_KP_ENTER]:
			if not paused and startup_error.is_empty(): dialogue.key(event.pressed,event.echo)
			elif not event.pressed: dialogue.key(false)
			get_viewport().set_input_as_handled()
			return
	super._input(event)

func clear_held_keys() -> void:
	super.clear_held_keys()
	dialogue.clear_input()
	if is_inside_tree() and event_core != null:
		paused = true
		if audio_player != null: audio_player.stream_paused = true
		refresh()

func toggle_pause() -> void:
	super.toggle_pause()
	dialogue.pending = false
	if audio_player != null: audio_player.stream_paused = paused

func single_step() -> void:
	if not paused or not startup_error.is_empty(): return
	accumulator = 0
	advance_update()
	render_phase = 0
	sync_source_layers()

func reset_state() -> void:
	if event_core == null:
		super.reset_state()
		return
	event_core.reset(); dialogue.reset()
	dialogue_closing = false
	if audio_player != null: audio_player.stop(); audio_player.stream_paused = paused
	audio_loaded = true; audio_started = false; source_pad_previous = 0
	completed_events = 0; source_replay_completed = false; qa_page_age = 0; qa_auto_update = 0; qa_capture_ready = false
	held_keys.clear(); accumulator = 0; render_phase = 0; update_count = 0; trace_cursor = 0; mismatch_count = 0; presentation_updates = 0
	current_differences.clear(); expected = {}; diagnostics = {}
	state = EventCore.project(event_core.player)
	animation_state = AnimationModel.project_state(state)
	event_queue.clear()
	shown_event = event_core.snapshot()
	for i: int in 3: event_queue.append(shown_event.duplicate(true))
	_show_sample(shown_event)
	trail = PackedVector2Array([world_position(state)])
	note = "往房間右側樓梯前移動即可觸發；兩頁對話後會依原作退回並恢復控制。"
	refresh()

func _show_sample(sample: Dictionary) -> void:
	var next_raw: Dictionary = EventCore.project(str(sample.player).hex_decode())
	var visual: Dictionary = EventVisual.project(next_raw)
	if visual.is_empty(): startup_error = "未確認的事件玩家圖像。"; paused = true; return
	var previous: Dictionary = EventCore.project(str(shown_event.player).hex_decode()) if not shown_event.is_empty() else next_raw
	display_advancing = next_raw.animation_timer != previous.animation_timer or next_raw.image_index != previous.image_index or next_raw.animation_cursor != previous.animation_cursor
	displayed_actor = visual
	shown_event = sample
	camera_states = sample.cameras.duplicate(true)
	displayed_decorations = [RoomDecorations.state_from_hex(sample.decor),RoomDecorations.state_from_hex(sample.ambient)]
	bundle.data.camera = [int(sample.cameras[0].x)/16,int(sample.cameras[0].y)/16]

func advance_time(delta: float) -> void:
	if event_core == null: return
	if paused or not startup_error.is_empty(): return
	if not replay_mode and active_directions().size() > 1:
		dialogue.pending = false; diagnostics = {"reason":"multiple_directions"}; refresh(); return
	accumulator += delta
	while accumulator+0.000000001 >= tick_seconds and not paused and startup_error.is_empty():
		accumulator -= tick_seconds
		advance_update()
	render_phase = clampf(accumulator/tick_seconds,0.0,0.999999999) if display_advancing else 0.0
	sync_source_layers()

func _auto_pad() -> int:
	qa_auto_update += 1
	if qa_auto_update <= 4: return 0
	if qa_auto_update <= 34: return 0x2000
	if qa_auto_update <= 101: return 0x8000
	if dialogue.active:
		qa_page_age += 1
		if qa_capture_page == dialogue.page:
			qa_capture_ready = true; paused = true
		elif qa_page_age >= 60: dialogue.click(); qa_page_age = 0
	return 0

func advance_update() -> void:
	if event_core == null or not startup_error.is_empty(): return
	var pad: int = 0
	var signals: Dictionary
	var source_expected: Dictionary = {}
	if replay_mode:
		var reference: Dictionary = event_bundle.references[route_index]
		if trace_cursor >= reference.updates.size(): return
		var row: Dictionary = reference.updates[trace_cursor]
		pad = int(row.input.pad)
		signals = {"resource_loaded":row.input.resource_loaded,"resource_playing":row.input.resource_playing,"text_active":row.input.text_active}
		source_expected = row.expected
		dialogue.key(bool(pad&0x0200))
	else:
		var directions: Array[String] = active_directions()
		if directions.size() > 1: dialogue.pending = false; diagnostics = {"reason":"multiple_directions"}; refresh(); return
		pad = _auto_pad() if qa_pc_mode else int(Movement.PAD_WORDS["none" if directions.is_empty() else directions[0]])
		var was_active: bool = dialogue.active
		dialogue.step()
		if was_active and not dialogue.active: dialogue_closing = true
		# Whole-page PC reading can finish before source Cirrus animation. The
		# text device acknowledges closure only once that required presentation
		# has completed; never reuse an occupied source child slot.
		if dialogue_closing and shown_event.get("child") != null and not shown_event.child.active:
			dialogue_closing = false
		signals = {"resource_loaded":1 if audio_loaded else 0,"resource_playing":1 if audio_started else 0,"text_active":dialogue.active or dialogue_closing}
	var was_locked: bool = event_core.disabled == 255
	var result: Dictionary = event_core.step(pad,signals)
	if not result.ok:
		startup_error = str(result.error); paused = true; refresh(); return
	if not result.applied: diagnostics = {"reason":"test_boundary"}; refresh(); return
	if replay_mode:
		dialogue.step()
		for key: String in result.state:
			if result.state[key] != source_expected[key]:
				startup_error = "事件來源對照不一致："+key; mismatch_count += 1; qa_mismatches += 1; paused = true; refresh(); return
		trace_cursor += 1
	for request: Dictionary in event_core.requests:
		match str(request.type):
			"load_original_resource": audio_loaded = event_bundle.preloaded; audio_started = false
			"play_original_resource":
				audio_player.play()
				audio_started = audio_player.playing
				if not audio_started: startup_error = "原作短音訊未能開始播放。"; paused = true
			"dialogue": dialogue.open(); qa_page_age = 0
			"source_text_layout": pass
			_: startup_error = "未知事件輸出。"; paused = true
	state = EventCore.project(event_core.player)
	animation_state = AnimationModel.project_state(state)
	expected = EventCore.project(str(source_expected.player).hex_decode()) if not source_expected.is_empty() else {}
	event_queue.append(result.state)
	_show_sample(event_queue.pop_front())
	presentation_updates += 1; update_count += 1
	if not replay_mode: trace_cursor = update_count
	diagnostics = event_core.diagnostics
	trail.append(world_position(state))
	if trail.size() > 2048: trail.remove_at(0)
	if was_locked and event_core.disabled == 0:
		completed_events += 1
		event_finished.emit(completed_events)
		if qa_soak_seconds > 0:
			qa_routes_completed += 1
			reset_state()
	if replay_mode and trace_cursor >= event_bundle.references[route_index].updates.size():
		paused = true; source_replay_completed = true
		route_completed.emit(EventBundle.ROUTES[route_index])
	note = "原作事件演出中；完成兩頁對話與退回動作後恢復控制。" if event_core.disabled else "可以移動；再次進入樓梯前會依來源重新觸發。"
	update_completed.emit(result)
	refresh()

func presentation_order(actor: Dictionary, camera: Vector2) -> Dictionary:
	var result: Dictionary = super.presentation_order(actor,camera)
	if not result.get("ok",false) or event_bundle.is_empty() or shown_event.is_empty() or shown_event.effect == null or shown_event.effect.ended: return result
	var key: String = "expression_%d" % int(shown_event.effect.image)
	if not event_bundle.sprites.has(key): return {"ok":false,"error":"必要表情影格缺失。"}
	var entry: Dictionary = event_bundle.sprites[key].duplicate()
	entry.id = "expression"; entry.kind = "prop"; entry.world_xy_raw = shown_event.effect_xy
	entry.sprite_priority = 3; entry.command_priority = 100
	result.entries.insert(result.entries.size()-2,entry)
	return result

func sync_source_layers() -> void:
	if source_layers.has("expression"): source_layers.expression.visible = false
	super.sync_source_layers()

func refresh() -> void:
	super.refresh()
	if event_core == null or dialogue_panel == null: return
	domain_label.text = "原作樓梯事件 · 613 格來源範圍 · 出口維持測試邊界"
	comparison_label.text = "更新 %d · 事件 %d 次 · 對照差異 %d" % [update_count,event_core.runs,mismatch_count]
	dialogue_panel.visible = dialogue.active
	if dialogue.active:
		var page: Dictionary = event_bundle.data.contract.dialogue.pages[dialogue.page]
		dialogue_text.text = str(page.zh_tw)
		dialogue_page.text = "%d / 2" % (dialogue.page+1)
		continue_button.disabled = paused or replay_mode
	_dialogue_layout()

func observe_qa() -> void:
	if qa_capture_page >= 0 and not qa_capture_ready: return
	var before: int = qa_spikes.size()
	super.observe_qa()
	if qa_spikes.size() > before and event_core != null:
		qa_spikes.back().world_xy_raw = [int(state.x_word),int(state.y_word)]
		qa_spikes.back().dialogue_page = dialogue.page
		qa_spikes.back().control_locked = event_core.disabled == 255

func qa_identity() -> Dictionary:
	var result: Dictionary = super.qa_identity()
	result.schema = "ao_pc_event_ui_qa_v1"
	result.event_manifest_sha256 = event_bundle.get("manifest_sha256","")
	result.event_images_preloaded = event_bundle.get("preloaded",false)
	result.pc_device_policy = true
	result.dialogue_page = dialogue.page
	result.confirmations = dialogue.accepted
	return result
