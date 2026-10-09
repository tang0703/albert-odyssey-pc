extends RefCounted
## Readback is confined to warmup or a separate screenshot process.
## observe() records wall-clock frame intervals; it never advances game rules.

var mode: String = "screenshot"
var warmup_seconds: float = 15.0
var requested_seconds: float = 0.0
var output_path: String = ""
var target_size: Vector2i = Vector2i.ZERO
var rendered_size: Vector2i = Vector2i.ZERO
var started_usec: int = 0
var last_usec: int = 0
var measured_start_usec: int = -1
var startup_ms: float = -1.0
var frames: Array[float] = []
var spikes_ms: Array[Dictionary] = []
var samples: Array[Dictionary] = []
var next_sample_seconds: float = 0.0
var surface_verified: bool = false
var screenshot_requested: bool = false
var screenshot_saved: bool = false
var finished: bool = false
var error_message: String = ""
var measured_start_actions: int = 0
var measured_start_battles: int = 0
var _ui: Control

func configure(path: String, mode_name: String, warmup: float, seconds: float, target: Vector2i) -> String:
	mode = "screenshot" if mode_name == "capture" else mode_name
	if mode not in ["screenshot", "soak"]:
		return "QA mode must be screenshot or soak"
	if not is_finite(warmup) or warmup < 0.0 or (mode == "soak" and warmup <= 0.0):
		return "Soak QA requires a positive finite warmup"
	if not is_finite(seconds) or seconds < 0.0 or (mode == "soak" and seconds <= 0.0):
		return "Soak QA requires positive measured seconds"
	if path.is_empty():
		return "QA output path must not be empty"
	if (target.x < 0 or target.y < 0) or ((target.x == 0) != (target.y == 0)):
		return "QA target must specify both positive dimensions or neither"
	output_path = path
	warmup_seconds = warmup if mode == "soak" else 2.0
	requested_seconds = seconds if mode == "soak" else maxf(seconds, 4.0)
	target_size = target
	rendered_size = Vector2i.ZERO
	started_usec = Time.get_ticks_usec()
	last_usec = started_usec
	measured_start_usec = -1
	startup_ms = -1.0
	frames.clear()
	spikes_ms.clear()
	samples.clear()
	next_sample_seconds = 0.0
	surface_verified = false
	screenshot_requested = false
	screenshot_saved = false
	finished = false
	error_message = ""
	measured_start_actions = 0
	measured_start_battles = 0
	return ""

func initialize(ui: Control, mode_name: String = "screenshot", warmup: float = 15.0) -> String:
	var issue: String = configure(ui.qa_path, mode_name, warmup, ui.qa_seconds, ui.qa_target)
	if not issue.is_empty():
		return issue
	if DirAccess.make_dir_recursive_absolute(output_path) != OK:
		return "Cannot create QA output directory: " + output_path
	_ui = ui
	RenderingServer.frame_post_draw.connect(_first_rendered_frame, CONNECT_ONE_SHOT)
	return ""

func _first_rendered_frame() -> void:
	if finished or not is_instance_valid(_ui):
		return
	# Godot ticks start at engine startup, before script loading and UI creation.
	startup_ms = Time.get_ticks_usec() / 1000.0
	_verify_surface(_ui, false)

func _verify_surface(ui: Control, save_screenshot: bool) -> void:
	# This guard is fail-closed: a delayed callback must never read GPU pixels
	# once a soak measurement has begun.
	if mode == "soak" and measured_start_usec >= 0:
		_fail(ui, "GPU readback attempted during measured soak")
		return
	var image: Image = ui.get_viewport().get_texture().get_image()
	if image == null or image.is_empty():
		_fail(ui, "QA rendered surface is empty; use a rendered window")
		return
	rendered_size = image.get_size()
	if target_size != Vector2i.ZERO and rendered_size != target_size:
		_fail(ui, "QA render size mismatch: actual %s, requested %s" % [rendered_size, target_size])
		return
	surface_verified = true
	ui.qa_capture_size = rendered_size
	if save_screenshot:
		if image.save_png(output_path.path_join("screen.png")) != OK:
			_fail(ui, "Could not write QA screenshot")
			return
		screenshot_saved = true

func _capture_after_render(ui: Control) -> void:
	await RenderingServer.frame_post_draw
	if not finished and is_instance_valid(ui):
		_verify_surface(ui, true)

func observe(ui: Control) -> void:
	if finished:
		return
	var now: int = Time.get_ticks_usec()
	var elapsed: float = (now - started_usec) / 1000000.0
	if not surface_verified and elapsed >= warmup_seconds:
		_fail(ui, "QA surface was not verified before warmup ended")
		return
	var was_measuring: bool = measured_start_usec >= 0
	var prior_spikes: int = spikes_ms.size()
	_record_clock(now)
	if spikes_ms.size() > prior_spikes:
		# Diagnostic counters only: no rendering readback or file I/O. These are
		# prior-frame engine timings, not proof of an OS or GPU stall's cause.
		spikes_ms[-1].merge({
			"engine_process_ms": Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0,
			"engine_physics_ms": Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0,
			"actor": ui.presentation_actor,
			"action": ui.presentation_action,
			"presentation_seconds": ui.presentation_elapsed,
			"busy": ui.busy,
			"actions": ui.qa_actions,
			"battles": ui.qa_fights,
			"log_lines": ui.log_view.get_line_count(),
		})
	if not was_measuring and measured_start_usec >= 0:
		measured_start_actions = ui.qa_actions
		measured_start_battles = ui.qa_fights
		_record_metrics(elapsed)
	if elapsed >= next_sample_seconds:
		_record_metrics(elapsed)
		next_sample_seconds = (floor(elapsed / 10.0) + 1.0) * 10.0
	if mode == "screenshot" and not screenshot_requested and elapsed >= 2.0:
		if ui.busy or ui.battle.unit_by_id(ui.battle.current)["side"] == "party":
			if ui.qa_variant == "selection" and not ui.busy:
				ui.choose_command(1)
			screenshot_requested = true
			_capture_after_render(ui)
	var measured: float = (now - measured_start_usec) / 1000000.0 if measured_start_usec >= 0 else 0.0
	var end_ready: bool = measured >= requested_seconds if mode == "soak" else elapsed >= requested_seconds and screenshot_saved
	if end_ready:
		_record_metrics(elapsed)
		_finish(ui, now)
	elif mode == "screenshot" and elapsed > requested_seconds + 10.0:
		_fail(ui, "QA screenshot could not reach a capturable battle state")

func _record_clock(now: int) -> void:
	var elapsed: float = (now - started_usec) / 1000000.0
	if measured_start_usec < 0 and elapsed >= warmup_seconds:
		measured_start_usec = now
		last_usec = now
		return
	if measured_start_usec >= 0 and now > last_usec:
		var frame_ms: float = (now - last_usec) / 1000.0
		frames.append(frame_ms)
		if frame_ms > 50.0:
			spikes_ms.append({"seconds": elapsed, "measured_seconds": (now - measured_start_usec) / 1000000.0, "frame_ms": frame_ms})
	last_usec = now

func _record_metrics(elapsed: float) -> void:
	# Engine counters require no framebuffer readback.
	samples.append({
		"seconds": elapsed,
		"phase": "measured" if measured_start_usec >= 0 else "warmup",
		"static_bytes": Performance.get_monitor(Performance.MEMORY_STATIC),
		"video_bytes": Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED),
		"nodes": Performance.get_monitor(Performance.OBJECT_NODE_COUNT),
	})

func make_report(now: int, actions: int, battles: int, speed: float) -> Dictionary:
	var ordered: Array[float] = frames.duplicate()
	ordered.sort()
	var sum_ms: float = 0.0
	for value: float in frames:
		sum_ms += value
	var mean_ms: float = sum_ms / maxi(frames.size(), 1)
	return {
		"mode": mode,
		"seconds": (now - started_usec) / 1000000.0,
		"warmup_seconds": warmup_seconds,
		"requested_measured_seconds": requested_seconds if mode == "soak" else 0.0,
		"measured_seconds": (now - measured_start_usec) / 1000000.0 if measured_start_usec >= 0 else 0.0,
		"steady_measurement": mode == "soak",
		"readback_during_measurement": mode != "soak" and screenshot_saved,
		"startup_ms": startup_ms,
		"startup_definition": "engine startup to first frame_post_draw",
		"size": [rendered_size.x, rendered_size.y],
		"surface_verified": surface_verified,
		"frames": frames.size(),
		"mean_ms": mean_ms,
		"mean_fps": 1000.0 / mean_ms if mean_ms > 0.0 else 0.0,
		"p95_ms": ordered[maxi(0, int(ceil(ordered.size() * 0.95)) - 1)] if not ordered.is_empty() else 0.0,
		"max_ms": ordered[-1] if not ordered.is_empty() else 0.0,
		"spikes_ms": spikes_ms,
		"samples": samples,
		"actions": actions,
		"battles": battles,
		"measured_actions": actions - measured_start_actions,
		"measured_battles": battles - measured_start_battles,
		"speed": speed,
		"memory_counters": "Godot engine static and video bytes; external process memory recorded separately",
		"error": error_message,
	}

func _finish(ui: Control, now: int) -> void:
	finished = true
	ui.set_process(false)
	var report: Dictionary = make_report(now, ui.qa_actions, ui.qa_fights, ui.speed)
	var file: FileAccess = FileAccess.open(output_path.path_join("report.json"), FileAccess.WRITE)
	if file == null:
		push_error("Cannot write QA report: " + output_path)
		ui.get_tree().quit(2)
		return
	file.store_string(JSON.stringify(report, "\t"))
	file.close()
	ui.get_tree().quit(0 if error_message.is_empty() else 2)

func _fail(ui: Control, issue: String) -> void:
	error_message = issue
	push_error(issue)
	_finish(ui, Time.get_ticks_usec())
