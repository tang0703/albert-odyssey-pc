extends SceneTree
const Common = preload("res://package_loader.gd")
var failures: Array[String] = []
var checks: int = 0
var updates: int = 0

func _initialize() -> void: call_deferred("run")
func check(value: bool, message: String) -> void:
	checks += 1
	if not value: failures.append(message); push_error(message)

func run() -> void:
	var ui: Control = load("res://event_main.tscn").instantiate()
	ui.ui_test_mode = true
	root.add_child(ui)
	await process_frame
	check(ui.startup_error.is_empty(),"Event entry loads: "+ui.startup_error)
	if not failures.is_empty(): ui.queue_free(); await process_frame; finish(); return
	check(ui.source_layers.size() == 10 and ui.event_bundle.preloaded,"All event art preloaded")
	var endings: Array = []
	for mode: String in ["hd","original","marker"]:
		ui.change_appearance(mode)
		for route: int in 6:
			ui.select_route(route)
			for row: Dictionary in ui.event_bundle.references[route].updates:
				ui.single_step()
				updates += 1
				if not ui.startup_error.is_empty(): check(false,"Source UI route %d update %d: %s" % [route,ui.trace_cursor,ui.startup_error]); break
			check(ui.source_replay_completed and ui.mismatch_count == 0,"Complete real event reference route")
			if mode == "hd": endings.append(ui.event_core.snapshot())
			else: check(ui.event_core.snapshot() == endings[route],"Appearance preserves all event state")
			if not failures.is_empty(): break
		if not failures.is_empty(): break
	# PC whole-page provider uses actual input edges, not original text-active data.
	ui.change_mode(0); ui.paused = false; ui.held_keys = {KEY_DOWN:true}
	for n: int in 30: ui.advance_update()
	ui.held_keys = {KEY_RIGHT:true}
	for n: int in 67: ui.advance_update()
	ui.held_keys.clear()
	ui.dialogue.key(true) # A held pre-dialogue press must not advance the new page.
	for n: int in 250:
		ui.advance_update()
		if ui.dialogue.active: break
	check(ui.dialogue.active and ui.dialogue.page == 0 and ui.event_core.disabled == 255,"Natural trigger opens first page and locks control")
	check(ui.audio_started and ui.audio_loaded,"Actual audio load/start acknowledged")
	for n: int in 30: ui.dialogue.key(true,true); ui.advance_update()
	check(ui.dialogue.page == 0 and ui.dialogue.accepted == 0,"Pre-held and repeat confirmations do not advance")
	ui.dialogue.key(false); ui.dialogue.key(true)
	ui.request_confirmation(); ui.request_confirmation()
	ui.advance_update()
	check(ui.dialogue.page == 1 and ui.dialogue.accepted == 1,"Keyboard and duplicate mouse edges coalesce once per update")
	for n: int in 30: ui.dialogue.key(true,true); ui.advance_update()
	check(ui.dialogue.page == 1,"Holding confirmation does not skip second page")
	var before: Dictionary = ui.event_core.snapshot()
	ui.toggle_pause(); ui.advance_time(2)
	check(ui.event_core.snapshot() == before and ui.dialogue.page == 1,"Pause freezes complete event")
	ui.change_appearance("original"); ui.change_appearance("hd")
	check(ui.event_core.snapshot() == before,"Mid-dialogue appearance preserves core")
	ui.clear_held_keys()
	check(ui.paused and not ui.dialogue.pending and ui.held_keys.is_empty(),"Focus loss pauses and clears input")
	ui.single_step()
	check(ui.event_core.update == int(before.update)+1 and ui.dialogue.page == 1,"Single step runs one whole update")
	ui.toggle_pause(); ui.dialogue.key(true); ui.advance_update()
	check(not ui.dialogue.active and ui.dialogue.accepted == 2,"Second fresh confirmation closes dialogue")
	var completed: Array = []
	ui.event_finished.connect(func(number: int) -> void: completed.append(number))
	for n: int in 300:
		ui.advance_update()
		if not completed.is_empty(): break
	check(completed == [1] and ui.event_core.disabled == 0,"Actual event completion restores control")
	check(ui.state.x_word == 0x3320 and ui.state.y_word == 0x6940,"Source scripted return destination")
	ui.dialogue.key(false)
	ui.held_keys = {KEY_LEFT:true}
	for n: int in 40: ui.advance_update()
	ui.held_keys = {KEY_RIGHT:true}
	for n: int in 60: ui.advance_update()
	ui.held_keys.clear()
	for n: int in 600:
		if ui.dialogue.active: ui.request_confirmation()
		ui.advance_update()
		if completed.size() == 2: break
	check(completed == [1,2] and ui.event_core.runs == 2,"PC reentry naturally completes a second event")
	# Reset in the middle of a dialogue, not only after a completed event.
	ui.reset_state(); ui.qa_pc_mode = true
	for n: int in 350:
		ui.advance_update()
		if ui.dialogue.active: break
	check(ui.dialogue.active,"Mid-dialogue reset setup")
	ui.reset_state()
	ui.qa_pc_mode = false
	check(ui.event_core.runs == 0 and not ui.dialogue.active and ui.dialogue.accepted == 0 and not ui.audio_player.playing,"Reset clears event, input and audio")
	var starts: Dictionary = ui.event_core.snapshot()
	ui.held_keys = {KEY_UP:true,KEY_DOWN:true}; ui.paused = false; ui.advance_time(1)
	check(ui.event_core.snapshot() == starts,"Multiple directions freeze whole event")
	var partitions: Array = []
	for fps: int in [30,60,120]:
		ui.reset_state(); ui.paused = false; ui.held_keys = {KEY_RIGHT:true}
		for n: int in fps: ui.advance_time(1.0/float(fps))
		partitions.append(ui.event_core.snapshot())
	check(partitions[0] == partitions[1] and partitions[1] == partitions[2],"30/60/120 input partitions agree")
	partitions.clear()
	for fps: int in [30,60,120]:
		ui.reset_state(); ui.paused = false; ui.qa_pc_mode = true
		for n: int in fps*12: ui.advance_time(1.0/float(fps))
		check(ui.completed_events == 1 and ui.dialogue.accepted == 2,"Full PC event completes at render partition "+str(fps))
		partitions.append(ui.event_core.snapshot())
	check(partitions[0] == partitions[1] and partitions[1] == partitions[2],"Whole PC event is identical at 30/60/120 render partitions")
	check(ui.startup_error.is_empty(),"No deferred event UI failure: "+ui.startup_error)
	ui.queue_free(); await process_frame
	finish()

func finish() -> void:
	var result: Dictionary = {"schema":"ao_pc_event_ui_tests_v1","passed":failures.is_empty(),"checks":checks,"source_updates":updates,"failures":failures}
	var file := FileAccess.open("res://../reports/event/d3-ui.json",FileAccess.WRITE)
	file.store_string(JSON.stringify(result,"\t")); file.close()
	print(JSON.stringify(result)); quit(0 if failures.is_empty() else 1)
