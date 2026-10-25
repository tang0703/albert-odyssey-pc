extends SceneTree
var failures: Array[String] = []
var checks: int = 0
var updates: int = 0
func _initialize() -> void: call_deferred("run")
func check(value: bool, message: String) -> void:
	checks += 1
	if not value: failures.append(message); push_error(message)
func enter(ui: Control, pressed: bool, echo: bool = false) -> void:
	var event := InputEventKey.new()
	event.physical_keycode = KEY_ENTER; event.pressed = pressed; event.echo = echo
	ui._input(event)
func advance(ui: Control, key: int, count: int) -> void:
	ui.held_keys = {} if key == 0 else {key:true}
	for n: int in count: ui.advance_update()
func run() -> void:
	var ui: Control = load("res://interaction_main.tscn").instantiate()
	ui.ui_test_mode = true; root.add_child(ui); await process_frame
	check(ui.startup_error.is_empty(),"Interaction entry loads: "+ui.startup_error)
	if not failures.is_empty(): ui.queue_free(); await process_frame; finish(); return
	check(ui.source_layers.size() == 12 and ui.event_bundle.preloaded,"All interaction art/audio preloaded")
	var endings: Array = []
	var pickup_seen: Dictionary = {}; var spark_seen: Dictionary = {}
	for mode: String in ["hd","original","marker"]:
		ui.change_appearance(mode)
		for route: int in 13:
			ui.select_route(route)
			for row: Dictionary in ui.event_bundle.references[route].updates:
				ui.single_step(); updates += 1
				if ui.source_layers.pickup.visible: pickup_seen[int(ui.displayed_actor.image_index)] = true
				if ui.source_layers.spark.visible: spark_seen[ui.EventCore.word(str(ui.shown_event.spark).hex_decode(),0x34)] = true
				if not ui.startup_error.is_empty(): check(false,"Route %d update %d: %s" % [route,ui.trace_cursor,ui.startup_error]); break
			check(ui.source_replay_completed and ui.mismatch_count == 0,"Complete source interaction route")
			if mode == "hd": endings.append(ui.event_core.snapshot())
			else: check(ui.event_core.snapshot() == endings[route],"Appearance preserves entire story state")
			if not failures.is_empty(): break
		if not failures.is_empty(): break
	check(pickup_seen.size() == 4 and spark_seen.size() == 12,"Every pickup and spark frame presented")
	ui.change_mode(0); ui.paused = false
	advance(ui,0,4); advance(ui,KEY_DOWN,30); advance(ui,KEY_RIGHT,19); advance(ui,KEY_DOWN,10); advance(ui,0,5)
	enter(ui,true); ui.request_confirmation(); ui.advance_update()
	check(ui.event_core.story == "03" and ui.event_core.disabled == 255,"Natural fresh interaction starts pickup once")
	for n: int in 350:
		enter(ui,true,true); ui.advance_update()
		if ui.dialogue.active: break
	check(ui.dialogue.active and ui.dialogue.page_count == 1 and ui.dialogue.accepted == 0,"Opening key cannot consume pickup dialogue")
	check(ui.dialogue_id == "map001_00b061","Pickup source text")
	for n: int in 20: enter(ui,true,true); ui.advance_update()
	check(ui.dialogue.accepted == 0,"Held key does not confirm")
	var before: Dictionary = ui.event_core.snapshot()
	ui.toggle_pause(); ui.advance_time(2)
	check(ui.event_core.snapshot() == before,"Pause freezes full interaction")
	ui.change_appearance("original"); ui.change_appearance("hd")
	check(ui.event_core.snapshot() == before,"Appearance leaves story unchanged")
	ui.clear_held_keys()
	check(ui.paused and not ui.interaction_pending and not ui.confirm_held,"Focus loss clears queued inputs")
	ui.single_step(); check(ui.event_core.update == int(before.update)+1,"Single step advances whole world once")
	ui.toggle_pause(); enter(ui,false); enter(ui,true); ui.request_confirmation(); ui.request_confirmation(); ui.advance_update()
	check(not ui.dialogue.active and ui.dialogue.accepted == 1,"Repeated click/key consumes exactly one page")
	var completed: Array = []
	ui.event_finished.connect(func(number: int) -> void: completed.append(number))
	for n: int in 350:
		ui.advance_update()
		if not completed.is_empty(): break
	check(completed == [1] and ui.event_core.item_count == 1 and ui.shown_event.disabled == 0,"Actual presentation completion grants once and restores control")
	check(ui.audio_started and ui.audio_loaded,"Pickup audio load/start acknowledged before presentation completion")
	check(not ui.source_layers.spark.visible and not ui.source_layers.pickup.visible,"Completed transient actors disappear")
	var order: Dictionary = ui.presentation_order(ui.displayed_actor,ui.source_camera())
	check(order.entries.size() == 7,"Both source decorations hidden after pickup")
	enter(ui,false); enter(ui,true); ui.advance_update(); advance(ui,0,5)
	check(ui.event_core.item_count == 1 and not ui.dialogue.active,"Repeated interaction does not grant twice")
	enter(ui,false); advance(ui,KEY_UP,9); advance(ui,KEY_RIGHT,52); ui.held_keys.clear()
	for n: int in 350:
		ui.advance_update()
		if ui.dialogue.active: break
	check(ui.dialogue_id == "map001_00b0b5" and ui.dialogue.page_count == 2,"Post-pickup stairs opens unequipped source branch")
	ui.request_confirmation(); ui.advance_update()
	check(ui.dialogue.page == 1,"Stairs first confirmation preserves second page")
	ui.request_confirmation(); ui.advance_update()
	for n: int in 350:
		ui.advance_update()
		if completed.size() == 2: break
	check(completed == [1,2] and ui.state.x_word == 0x3320 and ui.state.y_word == 0x6940,"Actual stairs presentation returns to source destination")
	check(ui.event_core.story == "03" and ui.event_core.item_count == 1,"Stairs cannot silently equip or transition")
	ui.reset_state(); ui.qa_pc_mode = true; ui.paused = false
	for n: int in 350:
		ui.advance_update()
		if ui.dialogue.active: break
	check(ui.dialogue.active,"Mid-dialogue reset setup")
	ui.reset_state(); ui.qa_pc_mode = false
	check(ui.event_core.story == "01" and ui.event_core.item_count == 0 and not ui.audio_player.playing and not ui.dialogue.active and not ui.interaction_pending,"Reset restores story, objects, audio and input")
	check(ui.presentation_order(ui.displayed_actor,ui.source_camera()).entries.size() == 9,"Reset restores both decorations")
	var initial: Dictionary = ui.event_core.snapshot()
	ui.held_keys = {KEY_UP:true,KEY_DOWN:true}; ui.paused = false; ui.advance_time(1)
	check(ui.event_core.snapshot() == initial,"Multiple directions freeze entire world")
	var partitions: Array = []
	for fps: int in [30,60,120]:
		ui.reset_state(); ui.paused = false; ui.qa_pc_mode = true
		for n: int in fps*20: ui.advance_time(1.0/float(fps))
		check(ui.completed_events == 2 and ui.dialogue.accepted == 3,"Full PC pickup and stairs flow at "+str(fps))
		partitions.append(ui.event_core.snapshot())
	check(partitions[0] == partitions[1] and partitions[1] == partitions[2],"Whole story identical at 30/60/120 render partitions")
	check(ui.startup_error.is_empty(),"No deferred UI error: "+ui.startup_error)
	ui.queue_free(); await process_frame; finish()
func finish() -> void:
	var result: Dictionary = {"schema":"ao_pc_interaction_ui_tests_v1","passed":failures.is_empty(),"checks":checks,"source_updates":updates,"failures":failures}
	var file := FileAccess.open("res://../reports/interaction/p3-ui.json",FileAccess.WRITE)
	file.store_string(JSON.stringify(result,"\t")); file.close()
	print(JSON.stringify(result)); quit(0 if failures.is_empty() else 1)
