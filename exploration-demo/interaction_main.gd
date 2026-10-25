extends "res://room_main.gd"
signal event_finished(run_number: int)
const EventCore = preload("res://interaction_core.gd")
const EventBundle = preload("res://interaction_loader.gd")
const EventVisual = preload("res://event_visual.gd")
const Dialogue = preload("res://interaction_dialogue.gd")
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
var dialogue_id: String = ""
var interaction_pending: bool = false
var confirm_held: bool = false
var interaction_button: Button
var qa_navigation: int = 0
var qa_capture_state: String = ""

func _ready() -> void:
	super._ready()
	if not startup_error.is_empty(): return
	var directory: String = EventBundle.default_directory()
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--interaction-package="): directory = arg.trim_prefix("--interaction-package=")
		if arg.begins_with("--interaction-page="): qa_capture_page = int(arg.trim_prefix("--interaction-page="))
		if arg.begins_with("--interaction-state="): qa_capture_state = arg.trim_prefix("--interaction-state=")
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
	for id: String in ["pickup","spark"]:
		var added := SourceLayer.new()
		added.name = id; map_canvas.add_child(added); source_layers[id] = added
	audio_player = AudioStreamPlayer.new()
	audio_player.stream = event_bundle.audio
	audio_player.volume_db = -8.0
	add_child(audio_player)
	audio_loaded = true
	route_select.clear()
	bundle.traces = []
	var labels: Array[String] = ["直接互動後接近樓梯","先提醒再互動","左側範圍外","右側範圍外","近側範圍外","朝北確認","長按確認","快速連按","左側範圍內","右側範圍內","近側範圍內","朝東確認","朝西確認"]
	for i: int in EventBundle.ROUTES.size():
		route_select.add_item(labels[i])
		var reference: Dictionary = event_bundle.references[i]
		var trace: Dictionary = {"id":EventBundle.ROUTES[i],"label":labels[i],"initial_state":EventCore.project(str(reference.initial_state.player).hex_decode()),"updates":[]}
		for row: Dictionary in reference.updates:
			trace.updates.append({"game_pad_word":row.input.pad,"expected":EventCore.project(str(row.expected.player).hex_decode())})
		bundle.traces.append(trace)
	get_window().title = "MAP001 房內 Cirrus 主動互動"
	qa_pc_mode = qa_soak_seconds > 0 or qa_capture_page >= 0 or not qa_capture_state.is_empty()
	if qa_pc_mode: replay_mode = false; mode_select.select(0)
	show_overlay = false
	reset_state()
	refresh()

func workbench_title() -> String:
	return "MAP001  /  與 Cirrus 啟程"

func workbench_subtitle() -> String:
	return "房內主動互動 · 原作劇情狀態 · 高清繁中對話"

func build_ui() -> void:
	super.build_ui()
	interaction_button = make_button("互動  Enter",request_confirmation)
	interaction_button.focus_mode = Control.FOCUS_NONE
	play_button.get_parent().add_child(interaction_button)
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
	# Wrapped text's minimum height settles after the first layout pass. Shrink
	# again on that notification, including while the simulation is paused.
	dialogue_panel.minimum_size_changed.connect(_dialogue_layout)

func _dialogue_layout() -> void:
	if dialogue_panel == null: return
	dialogue_panel.position = Vector2(20,18)
	dialogue_panel.size = Vector2(maxf(200,map_canvas.size.x-40),0)

func request_confirmation() -> void:
	if paused or not startup_error.is_empty() or replay_mode or event_core == null: return
	if dialogue.active: dialogue.click()
	elif event_core.disabled == 0 and (event_core.root == null or not event_core.root.active): interaction_pending = true

func _input(event: InputEvent) -> void:
	if event is InputEventKey:
		var key: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		if key in [KEY_ENTER,KEY_KP_ENTER]:
			if event.pressed and not event.echo and not confirm_held: request_confirmation()
			confirm_held = event.pressed
			if not event.pressed: dialogue.key(false)
			get_viewport().set_input_as_handled()
			return
	super._input(event)

func clear_held_keys() -> void:
	super.clear_held_keys()
	dialogue.clear_input()
	interaction_pending = false; confirm_held = false
	if is_inside_tree() and event_core != null:
		paused = true
		if audio_player != null: audio_player.stream_paused = true
		refresh()

func toggle_pause() -> void:
	super.toggle_pause()
	dialogue.pending = false
	interaction_pending = false
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
	dialogue_id = ""; interaction_pending = false; confirm_held = false; qa_navigation = 0
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
	note = "走到 Cirrus 桌前並朝向它，按 Enter 互動；拾取後再接近右側樓梯。"
	refresh()

func _show_sample(sample: Dictionary) -> void:
	var next_raw: Dictionary = EventCore.project(str(sample.player).hex_decode())
	var visual: Dictionary = next_raw.duplicate(true) if int(next_raw.image_index) in [35,36,37,38] else EventVisual.project(next_raw)
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
		dialogue.pending = false; interaction_pending = false; diagnostics = {"reason":"multiple_directions"}; refresh(); return
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
	if qa_auto_update <= 53: return 0x8000
	if qa_auto_update <= 63: return 0x2000
	if qa_capture_state == "before" and qa_auto_update == 68: qa_capture_ready = true; paused = true; return 0
	if qa_auto_update == 69: interaction_pending = true
	if dialogue.active:
		qa_page_age += 1
		var wanted: bool = (qa_capture_state == "pickup" and dialogue_id == "map001_00b061") or (qa_capture_state == "stairs" and dialogue_id == "map001_00b0b5")
		if wanted and dialogue.page == maxi(qa_capture_page,0):
			qa_capture_ready = true; paused = true
		elif qa_page_age >= 60: dialogue.click(); qa_page_age = 0
	if completed_events == 1 and event_core.disabled == 0:
		if qa_capture_state == "after": qa_capture_ready = true; paused = true; return 0
		qa_navigation += 1
		if qa_navigation <= 9: return 0x1000
		if qa_navigation <= 61: return 0x8000
	return 0

func advance_update() -> void:
	if event_core == null or not startup_error.is_empty(): return
	var pad: int = 0
	var pressed: int = 0
	var signals: Dictionary
	var source_expected: Dictionary = {}
	if replay_mode:
		var reference: Dictionary = event_bundle.references[route_index]
		if trace_cursor >= reference.updates.size(): return
		var row: Dictionary = reference.updates[trace_cursor]
		pad = int(row.input.pad)
		pressed = int(row.input.pressed)
		signals = {"resource_loaded":row.input.resource_loaded,"resource_playing":row.input.resource_playing,"text_active":row.input.text_active}
		source_expected = row.expected
		dialogue.key(bool(pad&0x0200))
	else:
		var directions: Array[String] = active_directions()
		if directions.size() > 1: dialogue.pending = false; interaction_pending = false; diagnostics = {"reason":"multiple_directions"}; refresh(); return
		pad = _auto_pad() if qa_pc_mode else int(Movement.PAD_WORDS["none" if directions.is_empty() else directions[0]])
		if paused and qa_capture_ready: return
		pressed = 0x0200 if interaction_pending else 0
		interaction_pending = false
		var was_active: bool = dialogue.active
		dialogue.step()
		if was_active and not dialogue.active: dialogue_closing = true
		# Whole-page PC reading can finish before source Cirrus animation. The
		# text device acknowledges closure only once that required presentation
		# has completed; never reuse an occupied source child slot.
		if dialogue_closing and shown_event.get("child") != null and not shown_event.child.active:
			dialogue_closing = false
		signals = {"resource_loaded":1 if audio_loaded else 0,"resource_playing":1 if audio_started else 0,"text_active":dialogue.active or dialogue_closing}
	var was_locked: bool = int(shown_event.get("disabled",0)) == 255
	var result: Dictionary = event_core.step(pad,signals,pressed)
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
			"load_original_resource":
				audio_player.stop()
				audio_player.stream = event_bundle.pickup_audio if request.id == "IVENT176.AIF" else event_bundle.audio
				audio_loaded = event_bundle.preloaded; audio_started = false
			"play_original_resource":
				audio_player.play()
				audio_started = audio_player.playing
				if not audio_started: startup_error = "原作短音訊未能開始播放。"; paused = true
			"dialogue":
				dialogue_id = str(request.id)
				if not event_bundle.data.contract.dialogues.has(dialogue_id): startup_error = "未核准的對話。"; paused = true; return
				dialogue.open(event_bundle.data.contract.dialogues[dialogue_id].pages.size()); qa_page_age = 0
				interaction_pending = false
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
	if was_locked and int(shown_event.disabled) == 0:
		completed_events += 1
		event_finished.emit(completed_events)
		if qa_soak_seconds > 0 and completed_events >= 2:
			qa_routes_completed += 1
			reset_state()
	if replay_mode and trace_cursor >= event_bundle.references[route_index].updates.size():
		paused = true; source_replay_completed = true
		route_completed.emit(EventBundle.ROUTES[route_index])
	note = "原作事件演出中；確認對話後等待動作完成。" if event_core.disabled else ("已拿起 Cirrus；再次接近樓梯可核對尚未裝備的提醒。" if event_core.story == "03" else "朝向桌上的 Cirrus，按 Enter 互動。")
	update_completed.emit(result)
	refresh()

func presentation_order(actor: Dictionary, camera: Vector2) -> Dictionary:
	var result: Dictionary = super.presentation_order(actor,camera)
	if not result.get("ok",false) or event_bundle.is_empty() or shown_event.is_empty(): return result
	var ordered: Array[Dictionary] = []
	for index: int in result.entries.size()-2:
		var entry: Dictionary = result.entries[index]
		if entry.kind == "player" and int(actor.image_index) in [35,36,37,38]:
			entry = event_bundle.sprites["pickup_%d" % int(actor.image_index)].duplicate()
			entry.merge({"id":"pickup","kind":"prop","world_xy_raw":[actor.x_word,actor.y_word],"sprite_priority":3,"command_priority":10},true)
		ordered.append(entry)
	if shown_event.effect != null and not shown_event.effect.ended:
		var key: String = "expression_%d" % int(shown_event.effect.image)
		if not event_bundle.sprites.has(key): return {"ok":false,"error":"必要表情影格缺失。"}
		var entry: Dictionary = event_bundle.sprites[key].duplicate()
		entry.merge({"id":"expression","kind":"prop","world_xy_raw":shown_event.effect_xy,"sprite_priority":3,"command_priority":100},true)
		ordered.append(entry)
	if shown_event.spark != null:
		var raw: PackedByteArray = str(shown_event.spark).hex_decode()
		var image_index: int = EventCore.word(raw,0x34)
		if EventCore.word(raw,6)&0x8000 and image_index != 127:
			var key: String = "spark_%d" % image_index
			if not event_bundle.sprites.has(key): return {"ok":false,"error":"必要光效影格缺失。"}
			var entry: Dictionary = event_bundle.sprites[key].duplicate()
			entry.merge({"id":"spark","kind":"prop","world_xy_raw":[EventCore.word(raw,0),EventCore.word(raw,2)],"sprite_priority":3,"command_priority":100},true)
			ordered.append(entry)
	for index: int in 2:
		if int(displayed_decorations[index].status)&0x8000: ordered.append(result.entries[result.entries.size()-2+index])
	result.entries = ordered
	return result

func sync_source_layers() -> void:
	if event_core == null or shown_event.is_empty(): super.sync_source_layers(); return
	if source_layers.is_empty() or displayed_actor.is_empty() or not startup_error.is_empty(): return
	for layer: Node2D in source_layers.values(): layer.visible = false
	var selected: Dictionary = {}
	if int(displayed_actor.image_index) not in [35,36,37,38]:
		selected = CharacterBundle.lookup(character_bundle,displayed_actor)
		if appearance_mode == "hd": selected = HdBundle.lookup(hd_bundle,HdAnimation.select(displayed_actor,render_phase))
		if not selected.get("ok",false): startup_error = str(selected.error); paused = true; return
	var camera: Vector2 = source_camera()
	var ordered: Dictionary = presentation_order(displayed_actor,camera)
	if not ordered.ok: startup_error = str(ordered.error); paused = true; return
	priority_material.set_shader_parameter("camera_offset",camera-Vector2(512,1536))
	priority_material.set_shader_parameter("canvas_size",map_canvas.size)
	var zoom: float = map_canvas.size.x/320.0
	for index: int in ordered.entries.size():
		var entry: Dictionary = ordered.entries[index]
		var player: bool = entry.kind == "player"
		if player and appearance_mode == "marker": continue
		var layer: Node2D = source_layers["player" if player else str(entry.id)]
		var frame: Dictionary = selected.frame if player else entry
		var texture: Texture2D = selected.texture if player else entry.texture
		var world: Vector2 = world_position(displayed_actor) if player else Vector2(float(entry.world_xy_raw[0]),float(entry.world_xy_raw[1]))/16.0
		var art_scale: float = float(frame.display_scale) if player and appearance_mode == "hd" else 1.0
		var top_left: Vector2 = (world-camera-Vector2(float(frame.anchor[0]),float(frame.anchor[1]))*art_scale)*zoom
		layer.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR if player and appearance_mode == "hd" else CanvasItem.TEXTURE_FILTER_NEAREST
		layer.show_sprite(texture,Rect2(top_left,Vector2(float(frame.dimensions[0]),float(frame.dimensions[1]))*zoom*art_scale),priority_material if int(entry.sprite_priority) == 2 else null,index)

func draw_player(canvas: Control, origin: Vector2, zoom: float) -> void:
	if not displayed_actor.is_empty() and int(displayed_actor.image_index) in [35,36,37,38]: return
	super.draw_player(canvas,origin,zoom)

func refresh() -> void:
	super.refresh()
	if event_core == null or dialogue_panel == null: return
	domain_label.text = "房內互動 · 613 格來源範圍 · 跨場景維持測試邊界"
	comparison_label.text = "更新 %d · 事件 %d 次 · 對照差異 %d" % [update_count,event_core.runs,mismatch_count]
	dialogue_panel.visible = dialogue.active
	if dialogue.active:
		var page: Dictionary = event_bundle.data.contract.dialogues[dialogue_id].pages[dialogue.page]
		dialogue_text.text = str(page.zh_tw)
		dialogue_page.text = "%d / %d" % [dialogue.page+1,dialogue.page_count]
		continue_button.disabled = paused or replay_mode
	interaction_button.disabled = paused or replay_mode or dialogue.active or event_core.disabled != 0
	_dialogue_layout()

func observe_qa() -> void:
	if (qa_capture_page >= 0 or not qa_capture_state.is_empty()) and not qa_capture_ready: return
	var before: int = qa_spikes.size()
	super.observe_qa()
	if qa_spikes.size() > before and event_core != null:
		qa_spikes.back().world_xy_raw = [int(state.x_word),int(state.y_word)]
		qa_spikes.back().dialogue_page = dialogue.page
		qa_spikes.back().control_locked = event_core.disabled == 255

func qa_identity() -> Dictionary:
	var result: Dictionary = super.qa_identity()
	result.schema = "ao_pc_interaction_ui_qa_v1"
	result.interaction_manifest_sha256 = event_bundle.get("manifest_sha256","")
	result.interaction_images_preloaded = event_bundle.get("preloaded",false)
	result.pc_device_policy = true
	result.dialogue_page = dialogue.page
	result.confirmations = dialogue.accepted
	result.dialogue_id = dialogue_id
	result.story = event_core.story if event_core != null else ""
	result.story_item_count = event_core.item_count if event_core != null else 0
	result.completed_events = completed_events
	return result
