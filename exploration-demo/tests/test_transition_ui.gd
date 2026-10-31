extends SceneTree
var failures: Array[String] = []
var checks: int = 0
var updates: int = 0
func _initialize() -> void: call_deferred("run")
func check(value: bool, message: String) -> void:
	checks += 1
	if not value: failures.append(message); push_error(message)
func key(ui: Control, code: int, pressed: bool = true, echo: bool = false) -> void:
	var event := InputEventKey.new(); event.physical_keycode = code; event.pressed = pressed; event.echo = echo; ui._input(event)
func tap(ui: Control, code: int) -> void: key(ui,code); key(ui,code,false)
func run() -> void:
	var ui: Control = load("res://transition_main.tscn").instantiate()
	ui.ui_test_mode = true; root.add_child(ui); await process_frame
	check(ui.startup_error.is_empty() and ui.transfer_ready,"Transfer entry loads: "+ui.startup_error)
	if not failures.is_empty(): ui.queue_free(); await process_frame; finish(); return
	var endings: Array = []
	for mode: String in ["hd","original","marker"]:
		ui.change_appearance(mode)
		for route: int in 4:
			ui.select_route(route)
			for n: int in 1600:
				ui.advance_update(); updates += 1
				if ui.source_replay_completed or not ui.startup_error.is_empty(): break
			check(ui.source_replay_completed and ui.mismatch_count == 0 and ui.startup_error.is_empty(),"Complete source route %s/%d: %s" % [mode,route,ui.startup_error])
			check(ui.event_core.stage == "landing" and ui.event_core.scene_id == 7 and ui.qa_identity().old_scene_hidden,"Only destination remains after transfer")
			check("延遲 2 次更新" in ui.animation_label.text,"Destination diagnostic reports its source display delay")
			if mode == "hd": endings.append(ui.event_core.transition_snapshot())
			else: check(ui.event_core.transition_snapshot() == endings[route],"Appearance preserves transfer and destination state")
			if not failures.is_empty(): break
		if not failures.is_empty(): break
	if not failures.is_empty(): ui.queue_free(); await process_frame; finish(); return
	# Natural PC device flow, including complete source pickup presentation.
	ui.change_mode(0); ui.qa_pc_mode = true; ui.paused = false
	var stages: Dictionary = {}; var transition_generation: int = ui.event_core.generation
	for n: int in 1400:
		ui.advance_update()
		var stage: String = ui.event_core.stage
		if stage not in ["original_room","landing"] and not stages.has(stage):
			stages[stage] = true
			var before: Dictionary = ui.event_core.transition_snapshot()
			tap(ui,KEY_E); ui.request_confirmation(); tap(ui,KEY_ENTER)
			check(not ui.equipment_panel.visible and not ui.interaction_pending,"Locked phase rejects actions: "+stage)
			tap(ui,KEY_SPACE); ui.advance_time(0.2)
			check(ui.paused and ui.event_core.transition_snapshot() == before,"Pause freezes phase: "+stage)
			ui.clear_held_keys(); check(ui.paused,"Focus loss pauses phase: "+stage)
			tap(ui,KEY_SPACE)
			# Press during the transition and keep it held across control recovery.
			key(ui,KEY_LEFT); key(ui,KEY_ENTER)
		if stage == "landing": break
	check(ui.event_core.stage == "landing" and ui.completed_events == 1 and ui.event_core.weapon == 27,"Natural exploration pickup equip and transfer complete: "+ui.startup_error)
	ui.qa_pc_mode = false
	check(ui.release_barrier.has(KEY_LEFT) and ui.release_barrier.has(KEY_ENTER) and ui.active_directions().is_empty(),"Held gameplay inputs require release after transfer")
	var before_xy: PackedByteArray = ui.event_core.player.slice(0,4)
	for n: int in 6: key(ui,KEY_LEFT,true,true); key(ui,KEY_ENTER,true,true); ui.advance_update()
	check(ui.event_core.player.slice(0,4) == before_xy and not ui.dialogue.active,"Held input cannot move or reopen event")
	key(ui,KEY_LEFT,false); key(ui,KEY_ENTER,false); key(ui,KEY_DOWN)
	ui.advance_update(); key(ui,KEY_DOWN,false)
	check(ui.event_core.player.slice(0,4) != before_xy,"Fresh press moves in landing")
	tap(ui,KEY_E); check(ui.equipment_panel.visible,"Landing permits source equipment semantics")
	ui.apply_equipment("remove"); check(ui.event_core.weapon == 255 and ui.event_core.item_count == 1,"Landing removal preserves item")
	ui.apply_equipment("equip"); check(ui.event_core.weapon == 27 and ui.event_core.item_count == 0,"Landing re-equip preserves item")
	tap(ui,KEY_ESCAPE)
	var before: Dictionary = ui.event_core.transition_snapshot()
	tap(ui,KEY_SPACE); ui.advance_time(0.2); check(ui.event_core.transition_snapshot() == before,"Landing pause freezes world")
	tap(ui,KEY_PERIOD); check(ui.event_core.transition_snapshot() != before,"Paused single step advances complete destination update")
	tap(ui,KEY_R)
	check(ui.event_core.stage == "original_room" and ui.event_core.story == "01" and ui.event_core.weapon == 255 and ui.event_core.item_count == 0 and not ui.audio_player.playing and ui.load_responses.is_empty(),"Reset restores complete original start")
	check("延遲 3 次更新" in ui.animation_label.text,"Reset restores original-room display delay diagnostic")
	check(not ui.accept_load({"generation":transition_generation,"id":"map001_scene7_resources"}) and ui.event_core.scene_id == 8,"Late prior-generation response cannot contaminate reset")
	key(ui,KEY_DOWN); tap(ui,KEY_R); before_xy = ui.event_core.player.slice(0,4)
	ui.paused = false; ui.qa_pc_mode = false; key(ui,KEY_DOWN,true,true); ui.advance_update()
	check(ui.event_core.player.slice(0,4) == before_xy and ui.active_directions().is_empty(),"Reset requires held direction release")
	key(ui,KEY_DOWN,false)
	# Reset at each transfer stage, including a queued completion. Replay uses
	# semantic inputs and never assigns a later source state.
	for target: String in ["fade_out","loading","arrival_first_update","fade_in"]:
		ui.reset_state(); ui.paused = false; ui.qa_pc_mode = true
		for n: int in 1400:
			ui.advance_update()
			if ui.event_core.stage == target: break
		check(ui.event_core.stage == target,"Reach reset stage: "+target)
		var generation: int = ui.event_core.generation
		ui.reset_state()
		check(ui.event_core.stage == "original_room" and ui.load_responses.is_empty() and not ui.accept_load({"generation":generation,"id":"map001_scene7_resources"}),"Reset cancels pending response: "+target)
	var partitions: Array = []
	for fps: int in [30,60,120]:
		ui.reset_state(); ui.paused = false; ui.qa_pc_mode = true
		for n: int in fps*20: ui.advance_time(1.0/float(fps))
		check(ui.event_core.stage == "landing" and ui.event_core.weapon == 27,"Natural one-way flow reaches landing at synthetic "+str(fps))
		partitions.append(ui.event_core.transition_snapshot())
	check(partitions[0] == partitions[1] and partitions[1] == partitions[2],"Synthetic 30/60/120 time partitions agree")
	ui.transfer_capture = "landing"; ui.qa_capture_ready = false; ui.qa_pc_mode = true; ui.paused = false
	ui.clear_held_keys()
	check(not ui.paused,"Explicit unattended screenshot keeps running after OS focus loss")
	ui.paused = true; ui.clear_held_keys()
	check(ui.paused,"Screenshot policy preserves explicit pause")
	ui.transfer_capture = ""; ui.paused = false; ui.clear_held_keys()
	check(ui.paused,"Interactive focus loss still pauses")
	check(ui.startup_error.is_empty(),"No runtime errors: "+ui.startup_error)
	ui.queue_free(); await process_frame; finish()
func finish() -> void:
	var result: Dictionary = {"schema":"ao_pc_transition_ui_tests_v1","passed":failures.is_empty(),"checks":checks,"source_updates":updates,"performance_tested":false,"failures":failures}
	var file := FileAccess.open("res://../reports/transition/t4-ui.json",FileAccess.WRITE); file.store_string(JSON.stringify(result,"\t")); file.close()
	print(JSON.stringify(result)); quit(0 if failures.is_empty() else 1)
