extends "res://equipment_main.gd"
const TransferCore = preload("res://transition_core.gd")
const TransferBundle = preload("res://transition_loader.gd")
const FadeShader = preload("res://transition_fade.gdshader")
const LandingCore = preload("res://landing_event_core.gd")
const LandingBundle = preload("res://landing_event_loader.gd")
const LandingDialogue = preload("res://landing_event_dialogue.gd")
var landing_bundle: Dictionary = {}
var landing_display_delay: int = 0
var landing_capture: String = ""
var landing_end_age: int = 0
var transfer_bundle: Dictionary = {}
var transfer_ready: bool = false
var load_responses: Array[Dictionary] = []
var physical_held: Dictionary = {}
var release_barrier: Dictionary = {}
var post_cursor: int = 0
var landing_age: int = 0
var fade_rect: ColorRect
var fade_material: ShaderMaterial
var transfer_footer: Control
var capture_focus_events: int = 0

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
		if arg.begins_with("--landing-event-state="): landing_capture = arg.trim_prefix("--landing-event-state=")
	super._ready()
	if not startup_error.is_empty(): return
	var directory: String = TransferBundle.default_directory()
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--transition-package="): directory = arg.trim_prefix("--transition-package=")
	transfer_bundle = TransferBundle.load_bundle(directory,event_bundle.data,bundle.profile,bundle.flags,character_bundle,room_bundle.data)
	if not transfer_bundle.ok: startup_error = str(transfer_bundle.error); paused = true; refresh(); return
	var landing_directory: String = LandingBundle.default_directory()
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--landing-event-package="): landing_directory = arg.trim_prefix("--landing-event-package=")
	landing_bundle = LandingBundle.load_bundle(landing_directory,transfer_bundle.data,event_bundle.data,bundle.profile,bundle.flags,character_bundle,room_bundle.data)
	if not landing_bundle.ok: startup_error = str(landing_bundle.error); paused = true; refresh(); return
	event_core = LandingCore.new()
	var configured: Dictionary = event_core.configure_landing_event(landing_bundle.data,transfer_bundle.data,event_bundle.data,bundle.profile,bundle.flags,character_bundle,room_bundle.data)
	if not configured.ok: startup_error = str(configured.error); paused = true; refresh(); return
	# Display-only text dictionary. The verified old core was configured above
	# against its original immutable contract, not this presentation union.
	event_bundle = event_bundle.duplicate(true)
	for id: String in landing_bundle.dialogues: event_bundle.data.contract.dialogues[id] = landing_bundle.dialogues[id].duplicate(true)
	dialogue = LandingDialogue.new()
	landing_display_delay = int(landing_bundle.visuals.presentation.logical_update_delay)
	for frame: Dictionary in transfer_bundle.frames.values()+landing_bundle.frames.values():
		if source_layers.has(frame.id): continue
		var layer := SourceLayer.new(); layer.name = frame.id
		map_canvas.add_child(layer); source_layers[frame.id] = layer
	fade_material = ShaderMaterial.new(); fade_material.shader = FadeShader
	fade_rect = ColorRect.new(); fade_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE; fade_rect.z_index = 900
	fade_rect.material = fade_material; map_canvas.add_child(fade_rect)
	fade_rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	transfer_ready = true
	if landing_capture not in ["","before","approach","dialogue-first","dialogue-last","after","boundary"]: startup_error = "未知轉場截圖狀態。"; paused = true; refresh(); return
	route_select.clear(); bundle.traces = []
	var labels: Array[String] = ["裝備後接近左側","卸下後接近左側","再次裝備後接近左側","觸發邊緣與確認按鍵"]
	for i: int in LandingBundle.ROUTES.size():
		route_select.add_item(labels[i])
		var updates: Array = []
		for row: Dictionary in landing_bundle.references[i].prefix.updates: updates.append({"expected":TransferCore.project(str(row.expected.player).hex_decode())})
		for row: Dictionary in landing_bundle.references[i].post_commit: updates.append({"expected":TransferCore.project(str(row.expected.player).hex_decode())})
		bundle.traces.append({"id":LandingBundle.ROUTES[i],"label":labels[i],"initial_state":TransferCore.project(event_core.player),"updates":updates})
	get_window().title = "MAP001 落點左側事件 · 功能候選版"
	replay_mode = false; mode_select.select(0); route_index = 0
	qa_pc_mode = not landing_capture.is_empty()
	reset_state(); refresh()

func workbench_title() -> String: return "MAP001  /  落點左側事件"
func workbench_subtitle() -> String: return "取得與裝備 · LAIA 事件 · 最小後續探索"

func reset_state() -> void:
	load_responses.clear(); release_barrier = physical_held.duplicate(); post_cursor = 0; landing_age = 0; landing_end_age = 0
	super.reset_state()
	if transfer_ready:
		priority_material.set_shader_parameter("source_foreground",room_bundle.textures["foreground.png"])
		fade_material.set_shader_parameter("source_offset",0.0)
		sync_source_layers(); refresh()

func can_open_equipment() -> bool:
	if transfer_ready and event_core.stage not in ["original_room","landing"]: return false
	return super.can_open_equipment()

func request_confirmation() -> void:
	if transfer_ready and event_core.stage != "original_room":
		if event_core.stage == "landing" and dialogue.active and not paused and not replay_mode and startup_error.is_empty(): dialogue.click()
		return
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
	var was_paused: bool = paused
	var was_audio_paused: bool = audio_player.stream_paused if audio_player != null else false
	input_barrier()
	super.clear_held_keys()
	# Explicit CLI screenshot automation must not depend on desktop focus. Keep
	# explicit pauses and all normal interactive focus-loss behavior unchanged.
	if not landing_capture.is_empty() and qa_pc_mode and not qa_capture_ready and startup_error.is_empty():
		paused = was_paused
		if audio_player != null: audio_player.stream_paused = was_audio_paused
		capture_focus_events += 1
		refresh()

func _visual_sample() -> Dictionary:
	var sample: Dictionary = event_core.snapshot()
	sample.merge(event_core.transition_snapshot(),true)
	sample.world_visible = true
	return sample

func _install_scene() -> void:
	input_barrier(); event_queue.clear(); dialogue.reset(); dialogue_closing = false; dialogue_id = ""
	equipment_panel.visible = false
	var initial: Dictionary = _visual_sample(); initial.world_visible = false
	for i: int in landing_display_delay: event_queue.append(initial.duplicate(true))
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
			"landing_event_completed": completed_events += 1; event_finished.emit(completed_events)
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
	if event_core.event_completed: landing_end_age += 1
	if not landing_capture.is_empty():
		var npc_visible: bool = false
		if int(shown_event.get("scene",8)) == 7:
			var npc: PackedByteArray = str(shown_event.arrival_actor).hex_decode()
			npc_visible = TransferCore.word(npc,0)/16.0 >= source_camera().x+48.0
		var ready: bool = (landing_capture == "approach" and event_core.event_runs == 1 and event_core.fixed_camera and npc_visible and not dialogue.active) or (landing_capture == "after" and landing_end_age >= 8)
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
		elif event_core.stage == "landing": pad = _landing_auto_pad()
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
	if dialogue_closing and (event_core.scene_id == 7 or (shown_event.get("child") != null and not shown_event.child.active)): dialogue_closing = false
	var signals: Dictionary = {"resource_loaded":1 if audio_loaded else 0,"resource_playing":1 if audio_started else 0,"text_active":dialogue.active or dialogue_closing}
	var result: Dictionary = event_core.step(pad,signals,pressed)
	if not result.ok: startup_error = str(result.error); paused = true; refresh(); return
	_requests()
	if not result.applied:
		diagnostics = {"reason":"test_boundary"}
		if landing_capture == "boundary": qa_capture_ready = true; paused = true
		refresh(); return
	trace_cursor = update_count+1; _present(result)

func _source_update() -> void:
	var reference: Dictionary = landing_bundle.references[route_index]
	var result: Dictionary
	if event_core.stage == "original_room":
		if trace_cursor < reference.prefix.updates.size():
			var row: Dictionary = reference.prefix.updates[trace_cursor]
			for action: String in row.equipment:
				if not event_core.equipment(action).ok: startup_error = "來源裝備操作遭拒。"; paused = true; refresh(); return
			var input: Dictionary = row.input
			dialogue.key(bool(int(input.pad)&0x0200))
			result = event_core.step(int(input.pad),{"resource_loaded":input.resource_loaded,"resource_playing":input.resource_playing,"text_active":input.text_active},int(input.pressed))
			var prior: Dictionary = result.get("state",{}).duplicate(true); prior.erase("landing_event")
			if result.ok and prior != row.expected: startup_error = "原房來源對照不一致。"
		else:
			result = event_core.step(int(reference.prefix.terminal.pad),{"resource_loaded":0,"resource_playing":0,"text_active":false})
			post_cursor = 1
		trace_cursor += 1
	else:
		if post_cursor >= reference.post_commit.size():
			paused = true; source_replay_completed = true; route_completed.emit(LandingBundle.ROUTES[route_index]); refresh(); return
		var row: Dictionary = reference.post_commit[post_cursor]
		if row.initialize:
			result = event_core.step(0,{})
			if not result.ok or event_core.stage != "loading": startup_error = "來源載入階段不符。"; paused = true; refresh(); return
			_requests()
			if load_responses.size() != 1 or not accept_load(load_responses.pop_front()): startup_error = "來源載入回應遭拒。"; paused = true; refresh(); return
		dialogue.key(bool(int(row.input.pad)&0x0200))
		result = event_core.step(int(row.input.pad),{"text_active":row.input.text_active})
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
	var npc: PackedByteArray = str(shown_event.arrival_actor).hex_decode()
	var npc_key: String = "%d:%d" % [TransferCore.word(npc,0x34),TransferCore.word(npc,0x14)&1]
	if not landing_bundle.frames.has(npc_key): return {"ok":false,"error":"缺少事件必要角色姿勢。"}
	var npc_entry: Dictionary = landing_bundle.frames[npc_key].duplicate(true)
	npc_entry.world_xy_raw = [TransferCore.word(npc,0),TransferCore.word(npc,2)]
	entries.append(npc_entry)
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
	for index: Variant in landing_bundle.data.landing_query_indices:
		var point := Vector2((int(index)%256)*8,(int(index)/256)*8)-source_camera()
		canvas.draw_rect(Rect2(point*zoom,Vector2(8,8)*zoom),Color(0.2,0.8,0.9,0.3),false,maxf(1,zoom*0.15))
	for contact: Dictionary in transfer_bundle.data.contacts:
		if int(contact.get("script_offset",0)) == 0x2c17: continue
		var b: Array = contact.bounds_raw
		canvas.draw_rect(Rect2((Vector2(b[0],b[1])/16.0-source_camera())*zoom,Vector2(b[2]-b[0],b[3]-b[1])/16.0*zoom),Color(1,0.5,0.2,0.8),false,maxf(1,zoom*0.3))

func refresh() -> void:
	super.refresh()
	if not transfer_ready: return
	var speaker: Label = dialogue_panel.get_child(0).get_child(0).get_child(0)
	speaker.text = "LAIA" if landing_bundle.dialogues.has(dialogue_id) else "CIRRUS"
	domain_label.text = "左側事件 · %d 格落點查表範圍 · 效能未驗收" % landing_bundle.data.landing_query_indices.size()
	if int(shown_event.get("scene",8)) == 7:
		animation_label.text = "F2 切換 · 圖像 %d / 顯示 %d\n原作演出延遲 %d 次更新" % [int(animation_state.image_index),int(displayed_actor.image_index),landing_display_delay]
	if event_core.scene_id == 7:
		comparison_label.text = "更新 %d · 左側事件 %d 次 · 對照差異 %d" % [update_count,event_core.event_runs,mismatch_count]
		interaction_button.disabled = true
		note = "左側事件已完成；可在核准範圍行走。其他出口與事件維持測試邊界。" if event_core.event_completed else "沿通道向左接近觸發區。事件中按 Enter 確認對話。"
		if event_core.disabled != 0: note = "LAIA 原作事件演出中；確認對話後等待角色與鏡頭動作完成。"
	if event_core.stage in ["fade_out","loading","arrival_first_update","fade_in"]: status_label.text = "原作轉場流程 · "+str(event_core.stage)+" · 等待恢復控制"
	elif event_core.stage == "boundary": status_label.text = "測試邊界：後續場景／事件尚未開放；按 R 回到原房起點。"
	elif diagnostics.get("reason") == "test_boundary": status_label.text = "測試邊界：此位置尚未驗證；可退回或按 R 重設。"
	elif event_core.scene_id == 7: status_label.text = note

func observe_qa() -> void:
	if not landing_capture.is_empty() and not qa_capture_ready: return
	super.observe_qa()

func qa_identity() -> Dictionary:
	var result: Dictionary = super.qa_identity()
	result.schema = "ao_pc_landing_event_ui_qa_v1"; result.performance_tested = false
	result.landing_event_state = landing_capture; result.event_manifest_sha256 = landing_bundle.get("manifest_sha256",""); result.transition_manifest_sha256 = transfer_bundle.get("manifest_sha256","")
	result.content_bounds_valid = get_viewport_rect().encloses(transfer_footer.get_global_rect())
	result.footer_bottom = transfer_footer.get_global_rect().end.y
	result.viewport_bottom = get_viewport_rect().end.y
	result.screenshot_focus_events = capture_focus_events
	if transfer_ready:
		result.landing_event_runs = event_core.event_runs; result.landing_event_completed = event_core.event_completed; result.scene_id = event_core.scene_id; result.stage = event_core.stage; result.rgb = event_core.rgb.duplicate()
		result.old_scene_hidden = true
		if int(shown_event.get("scene",8)) == 7:
			for id: String in source_layers:
				if id != "player" and not id.begins_with("landing_") and source_layers[id].visible: result.old_scene_hidden = false
	return result

func _landing_auto_pad() -> int:
	if dialogue.active:
		qa_page_age += 1
		var wanted: bool = (landing_capture == "dialogue-first" and dialogue_id == "map001_00b141" and dialogue.page == 0) or (landing_capture == "dialogue-last" and dialogue_id == "map001_00b2e2" and dialogue.page == 2)
		if wanted: qa_capture_ready = true; paused = true; return 0
		if qa_page_age >= 3: dialogue.click(); qa_page_age = 0
	if event_core.event_runs == 0:
		if TransferCore.word(event_core.player,2) < 1936*16: return 0x2000
		if landing_capture == "before" and TransferCore.word(event_core.player,0) <= 882*16: qa_capture_ready = true; paused = true; return 0
		return 0x4000
	if event_core.event_completed and landing_capture == "boundary": return 0x4000
	return 0
