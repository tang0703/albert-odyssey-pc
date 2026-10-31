extends SceneTree
# Exercise viewport hit testing and dispatched keyboard events, not button signals.
var failures: Array[String]=[]
var checks: int=0
func _initialize() -> void: call_deferred("run")
func check(value: bool,message: String) -> void:
	checks+=1
	if not value: failures.append(message)
func key(code: int,pressed: bool=true,echo: bool=false) -> void:
	var event:=InputEventKey.new();event.physical_keycode=code;event.pressed=pressed;event.echo=echo;Input.parse_input_event(event)
	await process_frame
func click(button: Button) -> void:
	var point: Vector2=root.get_screen_transform()*button.get_global_rect().get_center()
	var move:=InputEventMouseMotion.new();move.position=point;Input.parse_input_event(move);await process_frame
	for pressed: bool in [true,false]:
		var event:=InputEventMouseButton.new();event.position=point;event.button_index=MOUSE_BUTTON_LEFT;event.pressed=pressed;Input.parse_input_event(event);await process_frame
func run() -> void:
	var ui: Control=load("res://landing25d_main.tscn").instantiate();ui.ui_test_mode=true;root.add_child(ui)
	await process_frame;await process_frame
	check(ui.startup_error.is_empty(),"Entry loads")
	ui.qa_pc_mode=true;ui.equipment_capture="owned";ui.paused=false
	for n: int in 900:
		ui.advance_update()
		if ui.equipment_panel.visible:break
	ui.qa_pc_mode=false;ui.equipment_capture=""
	await process_frame;await process_frame
	check(ui.completed_events==1 and ui.equipment_panel.visible,"Natural pickup ends before input test")
	await click(ui.equip_button)
	check(ui.event_core.weapon==27 and ui.event_core.item_count==0,"Viewport mouse hit equips")
	await click(ui.equip_button)
	check(ui.event_core.weapon==27 and ui.event_core.item_count==0,"Disabled button ignores physical click")
	await click(ui.remove_button)
	check(ui.event_core.weapon==255 and ui.event_core.item_count==1 and ui.event_core.story=="07","Viewport mouse hit removes")
	await click(ui.close_button)
	check(not ui.equipment_panel.visible and not ui.interaction_pending,"Mouse closes without interaction leak")
	await key(KEY_E);await key(KEY_E,false)
	check(ui.equipment_panel.visible,"Dispatched E opens panel")
	await key(KEY_ENTER);await key(KEY_ENTER,true,true)
	check(ui.event_core.weapon==27,"Dispatched held Enter commits once")
	await key(KEY_ENTER,false);await key(KEY_ESCAPE);await key(KEY_ESCAPE,false)
	check(not ui.equipment_panel.visible and not ui.interaction_pending,"Esc isolates closed panel input")
	await key(KEY_R);await key(KEY_R,false)
	check(ui.event_core.story=="01" and ui.event_core.weapon==255 and ui.event_core.item_count==0,"Dispatched reset restores start")
	ui.qa_pc_mode=true;ui.equipment_capture="";ui.paused=false
	for n: int in 1400:
		ui.advance_update()
		if ui.event_core.stage=="landing":break
	ui.qa_pc_mode=false
	check(ui.event_core.stage=="landing","Natural flow reaches destination before dispatched landing input")
	await process_frame;await process_frame
	await click(ui.equipment_button)
	check(ui.equipment_panel.visible,"Destination equipment button opens panel")
	await click(ui.remove_button)
	check(ui.event_core.weapon==255 and ui.event_core.item_count==1,"Destination mouse removal preserves item")
	await click(ui.equip_button);await click(ui.close_button)
	check(ui.event_core.weapon==27 and ui.event_core.item_count==0 and not ui.interaction_pending,"Destination equip and close isolate input")
	await key(KEY_R);await key(KEY_R,false)
	check(ui.event_core.scene_id==8 and ui.event_core.story=="01" and ui.event_core.weapon==255 and ui.load_responses.is_empty(),"Destination dispatched reset restores original room")
	ui.qa_pc_mode=true;ui.paused=false
	for n: int in 2000:
		ui.advance_update()
		if ui.dialogue.active and ui.dialogue_id=="map001_00b141": break
	ui.qa_pc_mode=false
	check(ui.dialogue.active and ui.dialogue.page_count==5,"Natural LAIA dialogue opens all five first pages")
	await process_frame;await process_frame
	var old_page: int=ui.dialogue.page
	await click(ui.continue_button);await click(ui.continue_button)
	ui.advance_update()
	check(ui.dialogue.page==old_page+1,"Duplicate physical clicks before logical update advance once")
	await key(KEY_ENTER);await key(KEY_ENTER,true,true);ui.advance_update()
	old_page=ui.dialogue.page
	await key(KEY_ENTER,true,true);ui.advance_update()
	check(ui.dialogue.page==old_page,"Held Enter cannot skip next page")
	await key(KEY_ENTER,false)
	await key(KEY_E);await key(KEY_E,false)
	check(not ui.equipment_panel.visible,"Physical E blocked during LAIA dialogue")
	await key(KEY_R);await key(KEY_R,false)
	check(ui.event_core.scene_id==8 and not ui.dialogue.active and ui.event_core.event_runs==0,"Physical reset cancels LAIA dialogue")
	ui.queue_free();await process_frame
	var report: Dictionary={"schema":"ao_pc_landing25d_dispatched_input_v1","passed":failures.is_empty(),"checks":checks,"failures":failures,"performance_tested":false}
	var file:=FileAccess.open("res://../reports/enhanced25d-landing/input.json",FileAccess.WRITE);file.store_string(JSON.stringify(report,"\t"));file.close()
	print(JSON.stringify(report));quit(0 if failures.is_empty() else 1)
