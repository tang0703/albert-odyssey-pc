extends SceneTree
const Common = preload("res://package_loader.gd")
const Decorations = preload("res://room_decoration_core.gd")
var checks: int = 0
var updates: int = 0
var report_path: String = ""
var failures: Array[String] = []

func _initialize() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--report="): report_path = arg.trim_prefix("--report=")
	call_deferred("run")

func check(value: bool, message: String) -> void:
	checks += 1
	if not value: failures.append(message); push_error(message)

func snapshot(ui: Control) -> Dictionary:
	return {"state":ui.state.duplicate(true),"animation":ui.animation_state.duplicate(true),
		"camera":ui.camera_states.duplicate(true),"decorations":ui.decoration_states.duplicate(true),
		"displayed_decorations":ui.displayed_decorations.duplicate(true),"displayed_actor":ui.displayed_actor.duplicate(true),
		"shown_camera":ui.bundle.data.camera.duplicate(),"actor_queue":ui.presentation_queue.duplicate(true),
		"room_queue":ui.room_queue.duplicate(true),"updates":ui.presentation_updates,"cursor":ui.trace_cursor,
		"phase":ui.render_phase,"accumulator":ui.accumulator}

func run() -> void:
	var ui: Control = load("res://room_main.tscn").instantiate()
	ui.ui_test_mode = true
	root.add_child(ui)
	await process_frame
	check(ui.startup_error.is_empty(),"Room entry loads: "+ui.startup_error)
	if not failures.is_empty(): ui.queue_free(); await process_frame; finish(); return
	check(ui.source_layers.size()==9 and ui.room_bundle.textures.size()==19 and ui.verified_indices.size()==613,"All room art preloaded and evidence domain preserved")
	var resources: Dictionary = {}
	for key: String in ui.room_bundle.textures: resources[key]=ui.room_bundle.textures[key].get_instance_id()
	var first_run: Array[Dictionary] = []
	for mode: String in ["hd","original","marker"]:
		ui.change_appearance(mode)
		for route: int in ui.bundle.traces.size():
			ui.select_route(route)
			var trace: Dictionary = ui.bundle.traces[route]
			for index: int in trace.updates.size():
				ui.single_step()
				if not ui.startup_error.is_empty(): check(false,"Route %s update %d: %s" % [trace.id,index,ui.startup_error]); break
				var row: Dictionary = trace.updates[index]
				check(ui.state==row.expected,"Source movement "+str(index))
				check(ui.animation_state==ui.animator.project_state(row.actor_expected),"Source animation "+str(index))
				if row.camera_expected != null: check(ui.camera_states==row.camera_expected,"Source cameras "+str(index))
				check(ui.presentation_updates==index+1,"Exactly one complete presentation per step")
				updates += 1
			check(ui.paused and ui.trace_cursor==trace.updates.size() and ui.mismatch_count==0,"Route completion without stuck flow")
			if mode=="hd": first_run.append(snapshot(ui))
			else: check(snapshot(ui)==first_run[route],"Appearance changes no core or presentation state")
			if not failures.is_empty(): break
		if not failures.is_empty(): break
	# Check independently captured full object loop state after every update.
	var decor_proof: Variant = Common.read_json("res://../reports/room/decoration-validation.json")
	if not decor_proof is Dictionary: decor_proof = Common.read_json(ProjectSettings.globalize_path("res://").path_join("../reports/room/decoration-validation.json"))
	check(decor_proof is Dictionary and decor_proof.get("passed",false),"Actual decoration source gate required")
	if decor_proof is Dictionary:
		ui.select_route(4)
		for row: Dictionary in decor_proof.captures[0].history:
			if int(row.update)>0: ui.single_step()
			var expected: Array = []
			for raw: String in row.states: expected.append(Decorations.state_from_hex(raw))
			check(ui.decoration_states==expected,"Source decorations "+str(row.update))
	ui.change_mode(0);ui.clear_held_keys();ui.reset_state()
	var initial: Dictionary = snapshot(ui)
	ui.held_keys={KEY_RIGHT:true};ui.paused=false;ui.advance_time(ui.tick_seconds*7.4)
	var frozen: Dictionary = snapshot(ui)
	ui.toggle_pause();ui.advance_time(2.0)
	check(snapshot(ui)==frozen,"Pause freezes camera, decorations, fractional phase and queues")
	ui.toggle_pause();check(snapshot(ui)==frozen,"Resume preserves phase")
	ui.held_keys={KEY_RIGHT:true,KEY_DOWN:true};ui.advance_time(1.0)
	check(snapshot(ui)==frozen,"Multiple directions freeze entire update")
	ui.clear_held_keys();check(ui.held_keys.is_empty(),"Focus loss clears keys")
	ui.reset_state();check(snapshot(ui)==initial,"Reset restores all initial states and queues")
	var partitions: Array[Dictionary] = []
	for fps: int in [30,60,120]:
		ui.change_mode(0);ui.held_keys={KEY_RIGHT:true};ui.paused=false
		for n: int in fps: ui.advance_time(1.0/float(fps))
		var value: Dictionary = snapshot(ui)
		value.erase("phase");value.erase("accumulator")
		partitions.append(value)
	check(partitions[0]==partitions[1] and partitions[1]==partitions[2],"30/60/120 partitions agree for player/camera/decorations")
	# The same rightward input reaches the source staircase pre-event boundary.
	ui.change_mode(0);ui.held_keys={KEY_DOWN:true}
	for n: int in 30: ui.single_step()
	ui.held_keys={KEY_RIGHT:true}
	for n: int in 160: ui.single_step()
	check(ui.diagnostics.get("event_boundary","")=="stair_script_boundary","Original staircase stops at explicit test boundary")
	var boundary: Dictionary = snapshot(ui)
	ui.single_step();check(snapshot(ui)==boundary,"Pressing against exit preserves entire update and queues")
	for key: String in resources: check(ui.room_bundle.textures[key].get_instance_id()==resources[key],"Room texture remains preloaded")
	# Required queued decoration loss rejects before logical or visual commit.
	ui.change_mode(0);ui.clear_held_keys();ui.reset_state()
	var key: String = "7:%d" % ui.decoration_states[1].image
	var saved: Texture2D = ui.room_bundle.frames[key].texture
	ui.room_bundle.frames[key].texture=null
	var before_bad: Dictionary = snapshot(ui)
	ui.single_step()
	check(not ui.startup_error.is_empty() and snapshot(ui)==before_bad,"Missing queued decoration rejects atomically")
	ui.room_bundle.frames[key].texture=saved
	ui.queue_free();await process_frame
	finish()

func finish() -> void:
	var report: Dictionary = {"schema":"ao_pc_room_ui_tests_v1","passed":failures.is_empty(),"checks":checks,"source_updates":updates,"modes":["hd","original","marker"],"failures":failures}
	if not report_path.is_empty():
		var file := FileAccess.open(report_path,FileAccess.WRITE)
		if file != null: file.store_string(JSON.stringify(report,"  ")+"\n")
	print(JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
