extends "res://interaction_main.gd"
const EquipmentCore = preload("res://equipment_core.gd")
const EquipmentBundle = preload("res://equipment_loader.gd")
var equipment_ready: bool = false
var equipment_panel: PanelContainer
var equipment_button: Button
var weapon_label: Label
var possession_label: Label
var equipment_note: Label
var equip_button: Button
var remove_button: Button
var close_button: Button
var equipment_selection: int = 0
var equipment_key_held: bool = false
var boundary_ticks: int = 0
var boundary_shown: bool = false
var equipment_capture: String = ""
var auto_equipment_done: bool = false

func _ready() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--qa-soak-seconds="):
			push_error("Equipment candidate does not run load or performance tests."); get_tree().quit(1); return
		if arg.begins_with("--equipment-state="): equipment_capture = arg.trim_prefix("--equipment-state=")
	super._ready()
	if not startup_error.is_empty(): return
	var directory: String = EquipmentBundle.default_directory()
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--equipment-package="): directory = arg.trim_prefix("--equipment-package=")
	var loaded: Dictionary = EquipmentBundle.load_bundle(directory,bundle.profile,bundle.flags,character_bundle,room_bundle.data)
	if not loaded.ok: startup_error = str(loaded.error); paused = true; refresh(); return
	event_bundle = loaded; event_core = EquipmentCore.new()
	var configured: Dictionary = event_core.configure(loaded.data,bundle.profile,bundle.flags,character_bundle,room_bundle.data)
	if not configured.ok: startup_error = str(configured.error); paused = true; refresh(); return
	equipment_ready = true; qa_pc_mode = not equipment_capture.is_empty()
	if equipment_capture not in ["","unowned","owned","equipped","removed","boundary"]: startup_error = "未知裝備截圖狀態。"; paused = true
	route_select.clear(); bundle.traces = []
	var labels: Array[String] = ["裝備後前往樓梯","卸下後前往樓梯","再次裝備後前往樓梯","尚未取得時操作","取得後取消","長按確認裝備","切換選項後取消"]
	for i: int in labels.size():
		route_select.add_item(labels[i])
		var trace: Dictionary = {"id":EquipmentBundle.ROUTES[i],"label":labels[i],"initial_state":EquipmentCore.project(event_core.player),"updates":[]}
		for row: Dictionary in loaded.references[i].updates: trace.updates.append({"game_pad_word":row.input.pad,"expected":EquipmentCore.project(str(row.expected.player).hex_decode())})
		bundle.traces.append(trace)
	get_window().title = "MAP001 最小裝備流程 · 功能候選版"
	replay_mode = false; mode_select.select(0); route_index = 0
	reset_state(); refresh()

func workbench_title() -> String: return "MAP001  /  裝備 Cirrus"
func workbench_subtitle() -> String: return "房內探索 · 裝備與卸下 · 樓梯後續"

func build_ui() -> void:
	super.build_ui()
	equipment_button = make_button("裝備  E",toggle_equipment)
	equipment_button.focus_mode = Control.FOCUS_NONE
	play_button.get_parent().add_child(equipment_button)
	equipment_panel = PanelContainer.new(); equipment_panel.visible = false; equipment_panel.z_index = 2100
	equipment_panel.add_theme_stylebox_override("panel",panel_style("172d40")); map_canvas.add_child(equipment_panel)
	var column := VBoxContainer.new(); column.add_theme_constant_override("separation",16); equipment_panel.add_child(column)
	column.add_child(make_label("派克  /  武器",30,"f5dba2"))
	weapon_label = make_label("",28,"f0f5f7"); column.add_child(weapon_label)
	possession_label = make_label("",24,"b8ced8"); column.add_child(possession_label)
	equipment_note = make_label("",22,"b8ced8"); equipment_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; column.add_child(equipment_note)
	equip_button = make_button("裝備 Cirrus",func() -> void: apply_equipment("equip"))
	remove_button = make_button("卸下 Cirrus",func() -> void: apply_equipment("remove"))
	close_button = make_button("返回探索  Esc",close_equipment)
	for button: Button in [equip_button,remove_button,close_button]: button.focus_mode = Control.FOCUS_NONE; column.add_child(button)
	map_canvas.resized.connect(_equipment_layout)
	equipment_panel.minimum_size_changed.connect(_equipment_layout)

func _equipment_layout() -> void:
	if equipment_panel == null: return
	equipment_panel.size = Vector2(minf(620,maxf(200,map_canvas.size.x-40)),0)
	equipment_panel.position = Vector2(20,18)

func can_open_equipment() -> bool:
	return equipment_ready and startup_error.is_empty() and not paused and not replay_mode and not dialogue.active and not dialogue_closing and not event_core.transition_pending and event_core.disabled == 0 and shown_event.get("disabled",0) == 0 and (event_core.root == null or not event_core.root.active)

func toggle_equipment() -> void:
	if equipment_panel.visible: close_equipment(); return
	if not can_open_equipment(): return
	held_keys.clear(); interaction_pending = false; dialogue.clear_input(); accumulator = 0
	equipment_panel.visible = true
	equipment_selection = 1 if event_core.weapon == 27 else (0 if event_core.item_count == 1 else 2)
	refresh()

func close_equipment() -> void:
	if equipment_panel == null: return
	equipment_panel.visible = false; held_keys.clear(); interaction_pending = false; dialogue.clear_input(); accumulator = 0
	refresh()

func apply_equipment(action: String) -> void:
	if not equipment_panel.visible or not can_open_equipment(): return
	var result: Dictionary = event_core.equipment(action)
	if not result.ok: startup_error = str(result.error); paused = true
	elif result.changed:
		equipment_selection = 1 if event_core.weapon == 27 else 0
		# The panel changes no actor/camera state or presentation phase.
		for sample: Dictionary in event_queue:
			for key: String in ["weapon","attack","story","item_count"]: sample[key] = event_core.snapshot()[key]
		for key: String in ["weapon","attack","story","item_count"]: shown_event[key] = event_core.snapshot()[key]
	refresh()

func request_confirmation() -> void:
	if equipment_panel != null and equipment_panel.visible: return
	if equipment_ready and event_core.transition_pending: return
	super.request_confirmation()

func _input(event: InputEvent) -> void:
	if event is InputEventKey:
		var key: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		if key == KEY_E:
			if event.pressed and not event.echo and not equipment_key_held: toggle_equipment()
			equipment_key_held = event.pressed; get_viewport().set_input_as_handled(); return
		if equipment_panel != null and equipment_panel.visible and key in [KEY_ENTER,KEY_KP_ENTER,KEY_ESCAPE,KEY_UP,KEY_DOWN,KEY_LEFT,KEY_RIGHT,KEY_W,KEY_A,KEY_S,KEY_D]:
			if key in [KEY_ENTER,KEY_KP_ENTER]:
				if event.pressed and not event.echo and not confirm_held and not paused:
					if equipment_selection == 2: close_equipment()
					else: apply_equipment("equip" if equipment_selection == 0 else "remove")
				confirm_held = event.pressed
			elif event.pressed and not event.echo:
				if key == KEY_ESCAPE: close_equipment()
				elif not paused:
					var direction: int = -1 if key in [KEY_UP,KEY_LEFT,KEY_W,KEY_A] else 1
					for i: int in 3:
						equipment_selection = posmod(equipment_selection+direction,3)
						if equipment_selection == 2 or (equipment_selection == 0 and not equip_button.disabled) or (equipment_selection == 1 and not remove_button.disabled): break
					refresh()
			get_viewport().set_input_as_handled(); return
	super._input(event)

func clear_held_keys() -> void:
	equipment_key_held = false
	super.clear_held_keys()

func reset_state() -> void:
	boundary_ticks = 0; boundary_shown = false; auto_equipment_done = false; equipment_key_held = false
	if equipment_panel != null: equipment_panel.visible = false
	super.reset_state()

func single_step() -> void:
	if equipment_panel != null and equipment_panel.visible: return
	super.single_step()

func advance_time(delta: float) -> void:
	if equipment_panel != null and equipment_panel.visible: return
	super.advance_time(delta)

func advance_update() -> void:
	if not equipment_ready: return
	if equipment_panel.visible: return
	if event_core.transition_pending:
		if not boundary_shown:
			event_queue.append(event_core.snapshot()); _show_sample(event_queue.pop_front()); boundary_ticks += 1
			if boundary_ticks >= 3:
				boundary_shown = true; paused = true
				if equipment_capture == "boundary": qa_capture_ready = true
			sync_source_layers(); refresh()
		return
	if replay_mode and trace_cursor < event_bundle.references[route_index].updates.size():
		for action: String in event_bundle.references[route_index].updates[trace_cursor].equipment:
			var result: Dictionary = event_core.equipment(action)
			if not result.ok: startup_error = str(result.error); paused = true; refresh(); return
	super.advance_update()
	if equipment_panel.visible and qa_capture_ready: paused = false; refresh()
	if event_core.transition_pending and replay_mode: paused = false # drain only the existing presentation queue

func _auto_pad() -> int:
	if equipment_capture == "unowned" and qa_auto_update == 0:
		toggle_equipment(); qa_capture_ready = true; paused = true; return 0
	if completed_events < 1: return super._auto_pad()
	if not auto_equipment_done:
		toggle_equipment()
		if not equipment_panel.visible: return 0
		if equipment_capture == "owned": qa_capture_ready = true; paused = true; return 0
		apply_equipment("equip")
		if equipment_capture == "removed": apply_equipment("remove")
		auto_equipment_done = true
		if equipment_capture in ["equipped","removed"]: qa_capture_ready = true; paused = true; return 0
		close_equipment(); qa_navigation = 0
	qa_navigation += 1
	if qa_navigation <= 9: return 0x1000
	if qa_navigation <= 61: return 0x8000
	if qa_navigation <= 121: return 0
	if qa_navigation <= 137: return 0x1000
	if qa_navigation <= 157: return 0x8000
	if qa_navigation <= 185: return 0x2000
	return 0

func refresh() -> void:
	if equipment_ready and event_core != null and event_core.disabled == 0:
		if event_core.story == "07": note = "曾裝備 Cirrus 的劇情狀態已保留；可前往樓梯核對後續。"
		elif event_core.story == "03": note = "已拿起 Cirrus；按 E 開啟武器面板。"
	super.refresh()
	if not equipment_ready or equipment_panel == null: return
	domain_label.text = "裝備流程 · 634 格來源範圍 · 效能未驗收"
	equipment_button.disabled = not can_open_equipment() and not equipment_panel.visible
	interaction_button.disabled = interaction_button.disabled or equipment_panel.visible or event_core.transition_pending
	weapon_label.text = "目前武器："+("Cirrus" if event_core.weapon == 27 else "未裝備")
	possession_label.text = "Cirrus："+("已裝備" if event_core.weapon == 27 else ("持有 1 把" if event_core.item_count == 1 else "尚未取得"))
	equipment_note.text = "裝備面板開啟時，房內探索暫停。\n方向鍵選擇 · Enter 確認 · Esc 返回"
	equip_button.disabled = paused or event_core.weapon == 27 or event_core.item_count != 1
	remove_button.disabled = paused or event_core.weapon != 27
	var buttons: Array[Button] = [equip_button,remove_button,close_button]
	for i: int in buttons.size(): buttons[i].modulate = Color("ffe1a5") if equipment_selection == i else Color.WHITE
	if boundary_shown: status_label.text = "測試邊界：原作已提出轉場。下一房間尚未載入；按 R 重設。"
	_equipment_layout()

func observe_qa() -> void:
	if not equipment_capture.is_empty() and not qa_capture_ready: return
	super.observe_qa()

func qa_identity() -> Dictionary:
	var result: Dictionary = super.qa_identity()
	result.schema = "ao_pc_equipment_ui_qa_v1"; result.performance_tested = false
	result.interaction_manifest_sha256 = "365489c2f1c59410f26babb2e461c3dd2d25fb597d65306c4788aca01ff6a71e"
	result.equipment_state = equipment_capture; result.equipment_manifest_sha256 = event_bundle.get("manifest_sha256","")
	result.weapon = event_core.weapon if equipment_ready else -1
	result.attack = event_core.attack if equipment_ready else -1
	result.equipment_panel_visible = equipment_panel.visible if equipment_panel != null else false
	result.boundary_shown = boundary_shown
	return result
