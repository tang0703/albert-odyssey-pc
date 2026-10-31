extends "res://equipment_main.gd"
const TransferCore = preload("res://transition_core.gd")
const TransferBundle = preload("res://transition_loader.gd")
const FadeShader = preload("res://transition_fade.gdshader")
var transfer_bundle: Dictionary = {}
var transfer_ready: bool = false
var load_responses: Array[Dictionary] = []
var physical_held: Dictionary = {}
var release_barrier: Dictionary = {}
var post_cursor: int = 0
var transfer_capture: String = ""
var landing_age: int = 0
var fade_rect: ColorRect
var fade_material: ShaderMaterial
var transfer_footer: Control

func build_ui() -> void:
	super.build_ui()
	# Reserve space for wrapped transition messages without pushing the footer
	# beyond the viewport. These spacings apply only to the new entry.
	status_label.get_parent().add_theme_constant_override("separation",6)
	var grid: GridContainer = field_values.values()[0].get_parent()
	grid.add_theme_constant_override("v_separation",0)
	transfer_footer = stage.get_parent().get_parent().get_parent().get_child(-1)

func _ready() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--transition-state="): transfer_capture = arg.trim_prefix("--transition-state=")
	super._ready()
	if not startup_error.is_empty(): return
	var directory: String = TransferBundle.default_directory()
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--transition-package="): directory = arg.trim_prefix("--transition-package=")
	transfer_bundle = TransferBundle.load_bundle(directory,event_bundle.data,bundle.profile,bundle.flags,character_bundle,room_bundle.data)
	if not transfer_bundle.ok: startup_error = str(transfer_bundle.error); paused = true; refresh(); return
	event_core = TransferCore.new()
	var configured: Dictionary = event_core.configure_transition(transfer_bundle.data,event_bundle.data,bundle.profile,bundle.flags,character_bundle,room_bundle.data)
	if not configured.ok: startup_error = str(configured.error); paused = true; refresh(); return
	for frame: Dictionary in transfer_bundle.frames.values():
		if source_layers.has(frame.id): continue
		var layer := SourceLayer.new(); layer.name = frame.id
		map_canvas.add_child(layer); source_layers[frame.id] = layer
	fade_material = ShaderMaterial.new(); fade_material.shader = FadeShader
	fade_rect = ColorRect.new(); fade_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE; fade_rect.z_index = 900
	fade_rect.material = fade_material; map_canvas.add_child(fade_rect)
	fade_rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	transfer_ready = true
	if transfer_capture not in ["","before","fade","landing","boundary"]: startup_error = "未知轉場截圖狀態。"; paused = true; refresh(); return
	route_select.clear(); bundle.traces = []
	var labels: Array[String] = ["裝備後下樓","卸下後下樓","再次裝備後下樓","落點通道與接牆"]
	for i: int in TransferBundle.ROUTES.size():
		route_select.add_item(labels[i])
		var updates: Array = []
		for row: Dictionary in transfer_bundle.references[i].prefix.updates: updates.append({"expected":TransferCore.project(str(row.expected.player).hex_decode())})
		for row: Dictionary in transfer_bundle.references[i].post_commit: updates.append({"expected":TransferCore.project(str(row.expected.player).hex_decode())})
		bundle.traces.append({"id":TransferBundle.ROUTES[i],"label":labels[i],"initial_state":TransferCore.project(event_core.player),"updates":updates})
	get_window().title = "MAP001 首次單向轉場 · 功能候選版"
	replay_mode = false; mode_select.select(0); route_index = 0
	qa_pc_mode = not transfer_capture.is_empty()
	reset_state(); refresh()

func workbench_title() -> String: return "MAP001  /  首次下樓"
func workbench_subtitle() -> String: return "取得與裝備 · 單向轉場 · 落點通道"

func reset_state() -> void:
	load_responses.clear(); release_barrier = physical_held.duplicate(); post_cursor = 0; landing_age = 0
	super.reset_state()
	if transfer_ready:
		priority_material.set_shader_parameter("source_foreground",room_bundle.textures["foreground.png"])
		fade_material.set_shader_parameter("source_offset",0.0)
		sync_source_layers(); refresh()

func can_open_equipment() -> bool:
	if transfer_ready and event_core.stage not in ["original_room","landing"]: return false
	return super.can_open_equipment()

func request_confirmation() -> void:
	if transfer_ready and event_core.stage != "original_room": return
	super.request_confirmation()

func input_barrier() -> void:
	for key: int in physical_held: release_barrier[key] = true
	held_keys.clear(); interaction_pending = false; confirm_held = false; equipment_key_held = false; dialogue.clear_input()

func _input(event: InputEvent) -> void:
	if event is InputEventKey:
		var key: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		var gameplay: bool = KEY_DIRECTIONS.has(key) or key in [KEY_ENTER,KEY_KP_ENTER,KEY_E]
		if gameplay:
			if event.pressed: physical_held[key] = true
			else: physical_held.erase(key); release_barrier.erase(key)
			if transfer_ready and event_core.stage not in ["original_room","landing"]:
				if event.pressed: release_barrier[key] = true
				held_keys.erase(key); get_viewport().set_input_as_handled(); return
			if release_barrier.has(key): get_viewport().set_input_as_handled(); return
	super._input(event)

func clear_held_keys() -> void:
	input_barrier()
	super.clear_held_keys()

func _visual_sample() -> Dictionary:
	var sample: Dictionary = event_core.snapshot()
	sample.merge(event_core.transition_snapshot(),true)
	sample.world_visible = true
	return sample

func _install_scene() -> void:
	input_barrier(); event_queue.clear(); dialogue.reset(); dialogue_closing = false; dialogue_id = ""
	equipment_panel.visible = false
	var initial: Dictionary = _visual_sample(); initial.world_visible = false
	for i: int in 2: event_queue.append(initial.duplicate(true))
	_show_sample(initial)
	trail.clear()

func _show_sample(sample: Dictionary) -> void:
	if int(sample.get("scene",8)) == 8:
		super._show_sample(sample); return
	var actor: Dictionary = TransferCore.project(str(sample.player).hex_decode())
	var previous: Dictionary = TransferCore.project(str(shown_event.player).hex_decode()) if not shown_event.is_empty() else actor
	display_advancing = actor.animation_timer != previous.animation_timer or actor.image_index != previous.image_index or actor.animation_cursor != previous.animation_cursor
	displayed_actor = EventVisual.project(actor)
	if displayed_actor.is_empty(): startup_error = "落點玩家圖像未核准。"; paused = true; return
	shown_event = sample; camera_states = sample.cameras.duplicate(true)
	bundle.data.camera = [int(sample.cameras[0].x)/16,int(sample.cameras[0].y)/16]

func _requests() -> void:
	for request: Dictionary in event_core.requests:
		match str(request.type):
			"load_original_resource":
				audio_player.stop(); audio_player.stream = event_bundle.pickup_audio if request.id == "IVENT176.AIF" else event_bundle.audio
				audio_loaded = event_bundle.preloaded; audio_started = false
			"play_original_resource":
				audio_player.play(); audio_started = audio_player.playing
				if not audio_started: startup_error = "原作短音訊未能開始播放。"; paused = true
			"dialogue":
				dialogue_id = str(request.id)
				if not event_bundle.data.contract.dialogues.has(dialogue_id): startup_error = "未核准的對話。"; paused = true; return
				dialogue.open(event_bundle.data.contract.dialogues[dialogue_id].pages.size()); qa_page_age = 0; interaction_pending = false
			"source_text_layout","retain_source_music": pass
			"transition_begin": input_barrier(); equipment_panel.visible = false
			"load_scene":
				if not transfer_bundle.preloaded: startup_error = "轉場素材尚未預載。"; paused = true; return
				load_responses.append({"generation":int(request.generation),"id":str(request.id)})
			"scene_initialized": _install_scene()
			"control_restored": input_barrier()
			"test_boundary": diagnostics = {"reason":"test_boundary"}
			_: startup_error = "未知轉場輸出："+str(request.type); paused = true

func accept_load(response: Dictionary) -> bool:
	var result: Dictionary = event_core.scene_resources_ready(int(response.generation),str(response.id))
	if not result.ok: startup_error = str(result.error); paused = true; return false
	if result.accepted: _requests()
	return result.accepted

func _present(result: Dictionary) -> void:
	var was_locked: bool = int(shown_event.get("disabled",0)) == 255
	state = TransferCore.project(event_core.player); animation_state = AnimationModel.project_state(state)
	event_queue.append(_visual_sample()); _show_sample(event_queue.pop_front())
	presentation_updates += 1; update_count += 1
	diagnostics = event_core.diagnostics
	trail.append(world_position(state))
	if trail.size() > 2048: trail.remove_at(0)
	if was_locked and int(shown_event.disabled) == 0 and event_core.scene_id == 8:
		completed_events += 1; event_finished.emit(completed_events)
	if event_core.stage == "landing": landing_age += 1
	if not transfer_capture.is_empty():
		var ready: bool = (transfer_capture == "before" and event_core.stage == "fade_out" and event_core.rgb[0] == 0) or (transfer_capture == "fade" and event_core.scene_id == 7 and event_core.rgb[0] == -127) or (transfer_capture == "landing" and landing_age >= 8)
		if ready: qa_capture_ready = true; paused = true
	update_completed.emit(result); sync_source_layers(); refresh()

func advance_update() -> void:
	if not transfer_ready or not startup_error.is_empty() or equipment_panel.visible: return
	if replay_mode: _source_update(); return
	if event_core.stage == "loading":
		if not load_responses.is_empty(): accept_load(load_responses.pop_front())
		sync_source_layers(); refresh(); return
	if event_core.stage == "boundary": diagnostics = {"reason":"test_boundary"}; refresh(); return
	var directions: Array[String] = active_directions()
	if directions.size() > 1: dialogue.pending = false; interaction_pending = false; diagnostics = {"reason":"multiple_directions"}; refresh(); return
	var pad: int = int(Movement.PAD_WORDS["none" if directions.is_empty() else directions[0]])
	if qa_pc_mode:
		if event_core.stage == "original_room": pad = _auto_pad()
		elif event_core.stage == "landing" and transfer_capture == "boundary": pad = 0x4000
		else: pad = 0
	if equipment_panel.visible:
		if qa_pc_mode and qa_capture_ready: paused = false; refresh()
		return
	if paused and qa_capture_ready: return
	var pressed: int = 0x0200 if interaction_pending and event_core.stage == "original_room" else 0
	interaction_pending = false
	var was_active: bool = dialogue.active
	dialogue.step()
	if was_active and not dialogue.active: dialogue_closing = true
	if dialogue_closing and shown_event.get("child") != null and not shown_event.child.active: dialogue_closing = false
	var signals: Dictionary = {"resource_loaded":1 if audio_loaded else 0,"resource_playing":1 if audio_started else 0,"text_active":dialogue.active or dialogue_closing}
	var result: Dictionary = event_core.step(pad,signals,pressed)
	if not result.ok: startup_error = str(result.error); paused = true; refresh(); return
	_requests()
	if not result.applied:
		diagnostics = {"reason":"test_boundary"}
		if transfer_capture == "boundary": qa_capture_ready = true; paused = true
		refresh(); return
	trace_cursor = update_count+1; _present(result)

func _source_update() -> void:
	var reference: Dictionary = transfer_bundle.references[route_index]
	var result: Dictionary
	if event_core.stage == "original_room":
		if trace_cursor < reference.prefix.updates.size():
			var row: Dictionary = reference.prefix.updates[trace_cursor]
			for action: String in row.equipment:
				if not event_core.equipment(action).ok: startup_error = "來源裝備操作遭拒。"; paused = true; refresh(); return
			var input: Dictionary = row.input
			dialogue.key(bool(int(input.pad)&0x0200))
			result = event_core.step(int(input.pad),{"resource_loaded":input.resource_loaded,"resource_playing":input.resource_playing,"text_active":input.text_active},int(input.pressed))
			if result.ok and result.state != row.expected: startup_error = "原房來源對照不一致。"
		else:
			result = event_core.step(int(reference.prefix.terminal.pad),{"resource_loaded":0,"resource_playing":0,"text_active":false})
			post_cursor = 1
		trace_cursor += 1
	else:
		if post_cursor >= reference.post_commit.size():
			paused = true; source_replay_completed = true; route_completed.emit(TransferBundle.ROUTES[route_index]); refresh(); return
		var row: Dictionary = reference.post_commit[post_cursor]
		if row.initialize:
			result = event_core.step(0,{})
			if not result.ok or event_core.stage != "loading": startup_error = "來源載入階段不符。"; paused = true; refresh(); return
			_requests()
			if load_responses.size() != 1 or not accept_load(load_responses.pop_front()): startup_error = "來源載入回應遭拒。"; paused = true; refresh(); return
		result = event_core.step(int(row.input.pad),{})
		if result.ok and event_core.transition_snapshot() != row.expected: startup_error = "落點來源對照不一致。"
		post_cursor += 1; trace_cursor += 1
	if not result.ok: startup_error = str(result.error)
	if not startup_error.is_empty(): mismatch_count += 1; qa_mismatches += 1; paused = true; refresh(); return
	dialogue.step(); _requests(); _present(result)

func presentation_order(actor: Dictionary, camera: Vector2) -> Dictionary:
	if int(shown_event.get("scene",8)) == 8: return super.presentation_order(actor,camera)
	if not shown_event.get("world_visible",false): return {"ok":true,"entries":[]}
	var entries: Array[Dictionary] = []
	for slot: int in shown_event.objects.size():
		var raw: PackedByteArray = str(shown_event.objects[slot]).hex_decode()
		var key: String = "object:%d:%d" % [slot,TransferCore.word(raw,0x22)]
		if not transfer_bundle.frames.has(key): return {"ok":false,"error":"缺少落點物件影格。"}
		entries.append(transfer_bundle.frames[key].duplicate())
	entries.append({"kind":"player","sprite_priority":2,"command_priority":10,"y_sorted":true,"world_xy_raw":[actor.x_word,actor.y_word]})
	entries.append(transfer_bundle.frames["actor:1:3"].duplicate())
	var buckets: Dictionary = {}; var ordered: Array[Dictionary] = []
	for entry: Dictionary in entries:
		if not entry.y_sorted: ordered.append(entry); continue
		var bucket: int = Movement.divide16(int(entry.world_xy_raw[1])-int(camera.y)*16)+256
		if bucket < 40 or bucket > 700: return {"ok":false,"error":"落點排序範圍未驗證。"}
		while buckets.has(bucket) and bucket < 767: bucket += 1
		if buckets.has(bucket): return {"ok":false,"error":"落點排序容量不足。"}
		buckets[bucket] = entry
	var keys: Array = buckets.keys(); keys.sort()
	for key: int in keys: ordered.append(buckets[key])
	return {"ok":true,"entries":ordered}

func sync_source_layers() -> void:
	if transfer_ready:
		priority_material.set_shader_parameter("source_foreground",transfer_bundle.textures["foreground.png"] if int(shown_event.get("scene",8)) == 7 else room_bundle.textures["foreground.png"])
	super.sync_source_layers()
	if transfer_ready:
		priority_material.set_shader_parameter("camera_offset",source_camera()-Vector2(512,1792 if int(shown_event.get("scene",8)) == 7 else 1536))
		fade_material.set_shader_parameter("source_offset",float(event_core.rgb[0])/255.0)
		fade_rect.visible = event_core.rgb[0] < 0

func draw_background(canvas: Control, whole: Rect2) -> void:
	if int(shown_event.get("scene",8)) == 8: super.draw_background(canvas,whole); return
	canvas.draw_texture_rect_region(transfer_bundle.textures["background.png"],whole,Rect2(source_camera()-Vector2(512,1792),Vector2(320,224)))

func draw_map(canvas: Control) -> void:
	if int(shown_event.get("scene",8)) == 8: super.draw_map(canvas); return
	draw_background(canvas,Rect2(Vector2.ZERO,canvas.size))
	var zoom: float = canvas.size.x/320.0
	if appearance_mode == "marker" and shown_event.get("world_visible",false): draw_player(canvas,(world_position(displayed_actor)-source_camera())*zoom,zoom)
	if not show_overlay: return
	for index: Variant in transfer_bundle.data.landing_query_indices:
		var point := Vector2((int(index)%256)*8,(int(index)/256)*8)-source_camera()
		canvas.draw_rect(Rect2(point*zoom,Vector2(8,8)*zoom),Color(0.2,0.8,0.9,0.3),false,maxf(1,zoom*0.15))
	for contact: Dictionary in transfer_bundle.data.contacts:
		var b: Array = contact.bounds_raw
		canvas.draw_rect(Rect2((Vector2(b[0],b[1])/16.0-source_camera())*zoom,Vector2(b[2]-b[0],b[3]-b[1])/16.0*zoom),Color(1,0.5,0.2,0.8),false,maxf(1,zoom*0.3))

func refresh() -> void:
	super.refresh()
	if not transfer_ready: return
	domain_label.text = "單向下樓 · 落點 95 格來源查表範圍 · 效能未驗收"
	if event_core.scene_id == 7:
		interaction_button.disabled = true
		note = "落點右側通道；回程、後續劇情及未驗證區域為測試邊界。R 回到原房起點。"
	if event_core.stage in ["fade_out","loading","arrival_first_update","fade_in"]: status_label.text = "原作轉場流程 · "+str(event_core.stage)+" · 等待恢復控制"
	elif event_core.stage == "boundary": status_label.text = "測試邊界：後續場景／事件尚未開放；按 R 回到原房起點。"
	elif diagnostics.get("reason") == "test_boundary": status_label.text = "測試邊界：此位置尚未驗證；可退回或按 R 重設。"
	elif event_core.scene_id == 7: status_label.text = note

func observe_qa() -> void:
	if not transfer_capture.is_empty() and not qa_capture_ready: return
	super.observe_qa()

func qa_identity() -> Dictionary:
	var result: Dictionary = super.qa_identity()
	result.schema = "ao_pc_transition_ui_qa_v1"; result.performance_tested = false
	result.transition_state = transfer_capture; result.transition_manifest_sha256 = transfer_bundle.get("manifest_sha256","")
	result.content_bounds_valid = get_viewport_rect().encloses(transfer_footer.get_global_rect())
	result.footer_bottom = transfer_footer.get_global_rect().end.y
	result.viewport_bottom = get_viewport_rect().end.y
	if transfer_ready:
		result.scene_id = event_core.scene_id; result.stage = event_core.stage; result.rgb = event_core.rgb.duplicate()
		result.old_scene_hidden = true
		if int(shown_event.get("scene",8)) == 7:
			for id: String in source_layers:
				if id != "player" and not id.begins_with("landing_") and source_layers[id].visible: result.old_scene_hidden = false
	return result
