extends SceneTree
## Actual main-loop pacing at 30/60/120, independent of fabricated delta partitions.
var target_fps: int = 60
var output: String = ""
var frames: int = 0
var rendered_frames: int = 0
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
	if DisplayServer.get_name() != "headless":
		root.borderless = true
		root.position = Vector2i.ZERO
		root.size = Vector2i(1920, 1080)
		RenderingServer.frame_post_draw.connect(func() -> void: rendered_frames += 1)
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
	# Load fonts and verify a real framebuffer before starting the measurement.
	Engine.max_fps = target_fps
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	var surface_verified: bool = false
	if DisplayServer.get_name() != "headless":
		root.borderless = true
		root.position = Vector2i.ZERO
		root.size = Vector2i(1920, 1080)
		for warmup: int in 3: await RenderingServer.frame_post_draw
		var surface: Image = root.get_texture().get_image()
		surface_verified = surface != null and surface.get_size() == Vector2i(1920, 1080)
		if not surface_verified:
			push_error("GPU framebuffer does not match 1920x1080: " + str(surface.get_size() if surface != null else Vector2i.ZERO))
			quit(1)
			return
	ui.ui_test_mode = false
	frames = 0
	rendered_frames = 0
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
	var headless: bool = DisplayServer.get_name() == "headless"
	var device: String = str(RenderingServer.call("get_video_adapter_name")) if RenderingServer.has_method("get_video_adapter_name") else "unavailable"
	var vendor: String = str(RenderingServer.call("get_video_adapter_vendor")) if RenderingServer.has_method("get_video_adapter_vendor") else "unavailable"
	var report: Dictionary = {"schema":"ao_pc_exploration_render_rate_test_v1", "requested_fps":target_fps,
		"frames":frames, "elapsed_seconds":elapsed, "routes":results, "passed":not failed,
		"actual_main_loop_fps":float(frames) / elapsed, "rendered_frames":rendered_frames,
		"actual_render_fps":float(rendered_frames) / elapsed if not headless else null,
		"headless":headless, "surface_verified":surface_verified, "actual_viewport":[root.get_texture().get_width(),root.get_texture().get_height()],
		"renderer":str(ProjectSettings.get_setting("rendering/renderer/rendering_method")), "device":device, "vendor":vendor,
		"vsync_mode":DisplayServer.window_get_vsync_mode(), "effective_max_fps":Engine.max_fps,
		"note":"Rendered-frame count and real main-loop pacing; rule parity passes independently of achieved frame rate" if not headless else "Actual main-loop pacing only; headless does not measure GPU rendering performance"}
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
