extends SceneTree
var failures: Array[String] = []
var checks: int = 0
var updates: int = 0
func _initialize() -> void: call_deferred("run")
func check(value: bool, message: String) -> void:
	checks += 1
	if not value: failures.append(message); push_error(message)
func key(ui: Control, code: int, pressed: bool = true, echo: bool = false) -> void:
	var event := InputEventKey.new(); event.physical_keycode=code; event.pressed=pressed; event.echo=echo; ui._input(event)
func tap(ui: Control, code: int) -> void: key(ui,code); key(ui,code,false)
func run() -> void:
	var ui: Control = load("res://equipment_main.tscn").instantiate()
	ui.ui_test_mode=true; root.add_child(ui); await process_frame
	check(ui.startup_error.is_empty(),"Equipment entry loads: "+ui.startup_error)
	if not failures.is_empty(): ui.queue_free(); await process_frame; finish(); return
	var endings: Array=[]
	for mode: String in ["hd","original","marker"]:
		ui.change_appearance(mode)
		for route: int in 7:
			ui.select_route(route)
			for row: Dictionary in ui.event_bundle.references[route].updates:
				ui.advance_update(); updates+=1
				if not ui.startup_error.is_empty(): break
			check(ui.source_replay_completed and ui.mismatch_count==0 and ui.startup_error.is_empty(),"Complete source route %s/%d: %s" % [mode,route,ui.startup_error])
			if ui.event_core.transition_pending:
				for n: int in 3: ui.advance_update()
				check(ui.boundary_shown and ui.paused and ui.shown_event.transition_pending,"Boundary waits for presentation queue")
			if mode=="hd": endings.append(ui.event_core.snapshot())
			else: check(ui.event_core.snapshot()==endings[route],"Appearance preserves all equipment and world state")
			if not failures.is_empty(): break
		if not failures.is_empty(): break
	ui.change_mode(0); ui.paused=false; ui.qa_pc_mode=false
	tap(ui,KEY_E)
	check(ui.equipment_panel.visible and ui.equip_button.disabled and ui.remove_button.disabled,"Unowned equipment disabled")
	var before: Dictionary=ui.event_core.snapshot()
	ui.advance_time(1); ui.single_step(); ui.advance_update(); ui.request_confirmation()
	check(ui.event_core.snapshot()==before and not ui.interaction_pending,"Panel freezes world and rejects interaction/single step")
	tap(ui,KEY_ENTER)
	check(not ui.equipment_panel.visible and not ui.interaction_pending,"Enter closes unowned panel without input leak")
	ui.qa_pc_mode=true; ui.equipment_capture="owned"
	var completed: Array=[]
	ui.event_finished.connect(func(n: int) -> void: completed.append(n))
	for n: int in 900:
		ui.advance_update()
		if ui.dialogue.active:
			tap(ui,KEY_E); check(not ui.equipment_panel.visible,"Cannot open equipment during dialogue")
		if ui.equipment_panel.visible: break
	check(completed==[1] and ui.event_core.item_count==1 and ui.shown_event.disabled==0,"Panel opens after actual pickup presentation completes")
	ui.qa_pc_mode=false; ui.equipment_capture=""
	before=ui.event_core.snapshot(); tap(ui,KEY_ESCAPE)
	check(ui.event_core.snapshot()==before and not ui.interaction_pending,"Cancel preserves complete state")
	tap(ui,KEY_E); key(ui,KEY_ENTER)
	check(ui.event_core.weapon==27 and ui.event_core.item_count==0 and ui.event_core.attack==15 and ui.event_core.story=="07","Natural equip commits verified state")
	before=ui.event_core.snapshot()
	for n: int in 5: key(ui,KEY_ENTER,true,true); ui.equip_button.pressed.emit(); ui.advance_update()
	check(ui.event_core.snapshot()==before,"Held confirmation and repeated equip clicks cannot duplicate or remove")
	key(ui,KEY_ENTER,false); tap(ui,KEY_ENTER)
	check(ui.event_core.weapon==255 and ui.event_core.item_count==1 and ui.event_core.attack==10 and ui.event_core.story=="07","Remove restores weapon inventory, retaining story bit")
	ui.equip_button.pressed.emit()
	check(ui.event_core.weapon==27 and ui.event_core.item_count==0,"Mouse equip reuses same core")
	before=ui.event_core.snapshot(); tap(ui,KEY_SPACE); tap(ui,KEY_ENTER); ui.advance_time(1)
	check(ui.event_core.snapshot()==before and ui.paused,"Paused panel rejects operations")
	ui.clear_held_keys(); check(not ui.confirm_held and not ui.equipment_key_held and ui.paused,"Focus loss clears keys and pauses")
	tap(ui,KEY_SPACE); tap(ui,KEY_DOWN); key(ui,KEY_ENTER)
	check(not ui.equipment_panel.visible and not ui.interaction_pending,"Keyboard close after selection isolates confirmation")
	key(ui,KEY_ENTER,true,true); check(not ui.interaction_pending,"Held close confirmation cannot start interaction")
	key(ui,KEY_ENTER,false)
	tap(ui,KEY_R)
	check(ui.event_core.weapon==255 and ui.event_core.attack==10 and ui.event_core.item_count==0 and ui.event_core.story=="01" and not ui.audio_player.playing and not ui.equipment_panel.visible,"Reset restores equipment story audio panel")
	before=ui.event_core.snapshot(); ui.held_keys={KEY_UP:true,KEY_DOWN:true}; ui.advance_time(1)
	check(ui.event_core.snapshot()==before,"Multi-direction freeze remains intact")
	var partitions: Array=[]
	for fps: int in [30,60,120]:
		ui.reset_state(); ui.paused=false; ui.qa_pc_mode=true; ui.equipment_capture="boundary"
		for n: int in fps*22: ui.advance_time(1.0/float(fps))
		check(ui.boundary_shown and ui.event_core.weapon==27 and ui.completed_events==1,"Natural full equipment flow reaches boundary at "+str(fps))
		partitions.append(ui.event_core.snapshot())
		before=ui.event_core.snapshot(); ui.advance_update(); ui.single_step(); tap(ui,KEY_E)
		check(ui.event_core.snapshot()==before and not ui.equipment_panel.visible,"Boundary blocks further updates and panel")
	check(partitions[0]==partitions[1] and partitions[1]==partitions[2],"Synthetic 30/60/120 partitions agree")
	ui.reset_state(); check(not ui.boundary_shown and not ui.event_core.transition_pending and ui.event_core.story=="01","Boundary reset restores complete start")
	check(ui.startup_error.is_empty(),"No UI runtime errors: "+ui.startup_error)
	ui.queue_free(); await process_frame; finish()
func finish() -> void:
	var result: Dictionary={"schema":"ao_pc_equipment_ui_tests_v1","passed":failures.is_empty(),"checks":checks,"source_updates":updates,"performance_tested":false,"failures":failures}
	var file:=FileAccess.open("res://../reports/equipment/q3-ui.json",FileAccess.WRITE); file.store_string(JSON.stringify(result,"\t")); file.close()
	print(JSON.stringify(result)); quit(0 if failures.is_empty() else 1)
