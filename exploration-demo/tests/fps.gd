extends SceneTree
## Actual main-loop pacing at 30/60/120, independent of fabricated delta partitions.
var target_fps: int = 60
var output: String = ""
var frames: int = 0
var began_usec: int = 0
var failed: bool = false

func _initialize() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--fps="): target_fps = int(arg.trim_prefix("--fps="))
		if arg.begins_with("--output="): output = arg.trim_prefix("--output=")
	if target_fps not in [30, 60, 120]:
		push_error("Expected --fps=30, 60 or 120")
		quit(2)
		return
	Engine.max_fps = target_fps
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	call_deferred("run")

func _process(_delta: float) -> bool:
	frames += 1
	if began_usec > 0 and Time.get_ticks_usec() - began_usec > 60000000:
		push_error("Real-loop replay timed out")
		quit(1)
	return false

func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	ui.ui_test_mode = true
	root.add_child(ui)
	await process_frame
	if not ui.startup_error.is_empty():
		push_error(ui.startup_error)
		quit(1)
		return
	ui.ui_test_mode = false
	began_usec = Time.get_ticks_usec()
	var results: Array[Dictionary] = []
	for route: int in ui.bundle.traces.size():
		ui.select_route(route)
		ui.toggle_pause()
		await ui.route_completed
		var trace: Dictionary = ui.bundle.traces[route]
		var passed: bool = ui.mismatch_count == 0 and ui.trace_cursor == trace.updates.size() and ui.state == trace.updates.back().expected
		failed = failed or not passed
		results.append({"route":trace.id, "updates":ui.trace_cursor, "mismatches":ui.mismatch_count, "final_state":ui.state.duplicate(true), "passed":passed})
		# Avoid starting a new route inside the previous update's signal stack.
		await process_frame
	var elapsed: float = float(Time.get_ticks_usec() - began_usec) / 1000000.0
	var report: Dictionary = {"schema":"ao_pc_exploration_render_rate_test_v1", "requested_fps":target_fps,
		"frames":frames, "elapsed_seconds":elapsed, "routes":results, "passed":not failed,
		"headless":DisplayServer.get_name() == "headless", "note":"Actual Godot main-loop pacing; headless does not measure GPU rendering performance"}
	if not output.is_empty():
		var file := FileAccess.open(output, FileAccess.WRITE)
		if file == null:
			push_error("Cannot write FPS test report")
			quit(2)
			return
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	print("EXPLORATION_FPS_TEST " + JSON.stringify(report))
	ui.queue_free()
	await process_frame
	quit(1 if failed else 0)
