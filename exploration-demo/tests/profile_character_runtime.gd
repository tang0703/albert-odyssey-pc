extends SceneTree
## Diagnostic only: instrument the real entry without modifying its rules.
## Run with a real GPU, never alongside acceptance QA. No pixel readback or I/O
## occurs during measurement. RenderingServer signals do NOT measure GPU time.

class ProfiledCharacter extends "res://character_main.gd":
	var profiler: SceneTree

	func _process(delta: float) -> void:
		if profiler == null:
			super._process(delta)
			return
		profiler.begin_process(self, delta)
		var token: int = profiler.begin_scope("process")
		super._process(delta)
		profiler.end_scope(token)
		profiler.end_process(self)

	func advance_time(delta: float) -> void:
		var token: int = mark("advance_time")
		super.advance_time(delta)
		done(token)

	func advance_update() -> void:
		var point: Dictionary = profiler.begin_update_point(self) if profiler != null else {}
		var token: int = mark("advance_update")
		super.advance_update()
		done(token)
		if profiler != null: profiler.end_update_point(point,self)

	func prepare_update_presentation(result: Dictionary) -> String:
		var token: int = mark("prepare_presentation")
		var error: String = super.prepare_update_presentation(result)
		done(token)
		return error

	func refresh() -> void:
		var token: int = mark("refresh")
		super.refresh()
		done(token)

	func sync_source_layers() -> void:
		var token: int = mark("sync_source_layers")
		super.sync_source_layers()
		done(token)

	func reset_state() -> void:
		var token: int = mark("reset_state")
		super.reset_state()
		done(token)

	func draw_map(canvas: Control) -> void:
		var token: int = mark("draw_map")
		super.draw_map(canvas)
		done(token)

	func mark(key: String) -> int:
		return profiler.begin_scope(key) if profiler != null else 0

	func done(token: int) -> void:
		if profiler != null: profiler.end_scope(token)

var runtime: Control
var report_path: String = ""
var duration_seconds: float = 180.0
var warmup_seconds: float = 15.0
var target_size := Vector2i(3840,2160)
var appearance: String = "hd"
var started_us: int = 0
var warmup_stable_us: int = 0
var measurement_started_us: int = 0
var measurement_finished_us: int = 0
var previous_process_us: int = 0
var previous_post_us: int = 0
var process_id: int = 0
var next_memory_second: int = 0
var finished: bool = false
var failure: String = ""
var current: Dictionary = {}
var scopes: Array[Dictionary] = []
var rows: Array[Dictionary] = []
var memory_samples: Array[Dictionary] = []
var pairing_errors: Array[Dictionary] = []
var warmup_surface_changes: Array[Dictionary] = []
var last_surface := Vector2i.ZERO

func _initialize() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--profile-report="): report_path = arg.trim_prefix("--profile-report=")
		if arg.begins_with("--profile-seconds="): duration_seconds = float(arg.trim_prefix("--profile-seconds="))
		if arg.begins_with("--profile-warmup-seconds="): warmup_seconds = float(arg.trim_prefix("--profile-warmup-seconds="))
		if arg.begins_with("--profile-appearance="): appearance = arg.trim_prefix("--profile-appearance=")
		if arg.begins_with("--profile-size="):
			var parts: PackedStringArray = arg.trim_prefix("--profile-size=").split("x")
			if parts.size() == 2: target_size = Vector2i(int(parts[0]),int(parts[1]))
		if arg.begins_with("--qa-"): failure = "Do not combine this diagnostic with the independent QA runner."
	call_deferred("start")

func start() -> void:
	if DisplayServer.get_name() == "headless": failure = "Runtime profiling requires a real GPU/window; headless results are not accepted."
	if report_path.is_empty(): failure = "Supply --profile-report=<absolute JSON path>."
	if not report_path.is_absolute_path(): failure = "Profile report must use an absolute path."
	if not is_finite(duration_seconds) or duration_seconds <= 0 or not is_finite(warmup_seconds) or warmup_seconds < 0: failure = "Invalid diagnostic duration."
	if target_size != Vector2i(3840,2160): failure = "This diagnostic fixes the surface at 3840x2160."
	if appearance not in ["hd","original","marker"]: failure = "Unknown appearance."
	if not failure.is_empty():
		push_error(failure)
		quit(1)
		return
	Engine.max_fps = 60
	# Keep the actual scene and its layout. Only the script subclass measures
	# virtual call boundaries; its super calls execute all real game operations.
	runtime = load("res://character_main.tscn").instantiate()
	runtime.set_script(ProfiledCharacter)
	runtime.ui_test_mode = true
	runtime.qa_target = target_size
	root.add_child(runtime)
	if not runtime.startup_error.is_empty():
		failure = runtime.startup_error
		finish()
		return
	runtime.change_appearance(appearance)
	runtime.qa_soak_seconds = duration_seconds # Reuse the real route-completion loop only.
	runtime.change_mode(1)
	runtime.paused = false
	runtime.ui_test_mode = false
	runtime.profiler = self
	started_us = Time.get_ticks_usec()
	RenderingServer.frame_pre_draw.connect(before_draw)
	RenderingServer.frame_post_draw.connect(after_draw)

func begin_process(view: Control, delta: float) -> void:
	if finished: return
	var now: int = Time.get_ticks_usec()
	if not current.is_empty():
		pairing_errors.append({"reason":"process replaced before matching post_draw","process_id":current.process_id,"ticks_us":now})
	process_id += 1
	current = {"process_id":process_id,"engine_process_frame":Engine.get_process_frames(),
		"engine_draw_frame_at_process":Engine.get_frames_drawn(),"process_delta_seconds":delta,
		"process_start_us":now,"previous_process_start_us":previous_process_us,"previous_post_draw_us":previous_post_us,
		"route_before":str(view.bundle.traces[view.route_index].id),"trace_cursor_before":view.trace_cursor,
		"routes_completed_before":view.qa_routes_completed,"source_pose_before":pose(view),"scopes":{},"logic_updates":[]}
	previous_process_us = now
	if not scopes.is_empty():
		pairing_errors.append({"reason":"scope stack remained open","process_id":process_id})
		scopes.clear()

func end_process(view: Control) -> void:
	if finished or current.is_empty(): return
	current.process_end_us = Time.get_ticks_usec()
	current.route_after = str(view.bundle.traces[view.route_index].id)
	current.trace_cursor_after = view.trace_cursor
	current.routes_completed_after = view.qa_routes_completed
	current.source_pose_after = pose(view)
	current.catchup_logic_steps = current.logic_updates.size()
	if not view.startup_error.is_empty() or view.qa_mismatches != 0:
		failure = "Runtime/source failure: " + str(view.startup_error)
		stop_after_frame()

func pose(view: Control) -> Dictionary:
	return {"heading":view.state.get("heading",-1),"image_index":view.animation_state.get("image_index",-1),
		"animation_index":view.animation_state.get("animation_index",-1),"animation_timer":view.animation_state.get("animation_timer",-1)}

func begin_update_point(view: Control) -> Dictionary:
	if finished or current.is_empty(): return {}
	return {"start_us":Time.get_ticks_usec(),"route":str(view.bundle.traces[view.route_index].id),
		"input_index_zero_based":view.trace_cursor,"source_pose_before":pose(view)}

func end_update_point(point: Dictionary, view: Control) -> void:
	if point.is_empty() or current.is_empty(): return
	point.elapsed_us = Time.get_ticks_usec() - int(point.start_us)
	point.route_after = str(view.bundle.traces[view.route_index].id)
	point.trace_cursor_after = view.trace_cursor
	point.source_pose_after = pose(view)
	current.logic_updates.append(point)

func begin_scope(key: String) -> int:
	if finished or current.is_empty(): return 0
	var now: int = Time.get_ticks_usec()
	scopes.append({"key":key,"start_us":now,"child_us":0})
	return scopes.size()

func end_scope(token: int) -> void:
	if token == 0 or finished: return
	var now: int = Time.get_ticks_usec()
	if token != scopes.size():
		pairing_errors.append({"reason":"nested scope mismatch","process_id":process_id,"token":token})
		return
	var scope: Dictionary = scopes.pop_back()
	var elapsed: int = now - int(scope.start_us)
	if not scopes.is_empty(): scopes.back().child_us += elapsed
	var metrics: Dictionary = current.scopes
	if not metrics.has(scope.key): metrics[scope.key] = {"calls":0,"inclusive_us":0,"exclusive_us":0,"max_call_us":0}
	var record: Dictionary = metrics[scope.key]
	record.calls += 1
	record.inclusive_us += elapsed
	record.exclusive_us += elapsed - int(scope.child_us)
	record.max_call_us = maxi(record.max_call_us,elapsed)

func before_draw() -> void:
	if finished or current.is_empty(): return
	if current.has("pre_draw_us"):
		pairing_errors.append({"reason":"multiple pre_draw for one process","process_id":process_id})
	current.pre_draw_us = Time.get_ticks_usec()

func after_draw() -> void:
	if finished or current.is_empty(): return
	var now: int = Time.get_ticks_usec()
	current.post_draw_us = now
	current.engine_draw_frame_at_post = Engine.get_frames_drawn()
	# ViewportTexture size metadata doubles canvas-items stretch on this build.
	# Reuse the physical client-size probe of the independently accepted QA.
	var actual: Vector2i = runtime.qa_actual_surface_size()
	if actual != last_surface:
		warmup_surface_changes.append({"ticks_us":now,"size":[actual.x,actual.y],"measuring":measurement_started_us > 0})
		last_surface = actual
	var surface_ok: bool = actual == target_size and root.size == target_size
	if measurement_started_us == 0 and float(now - started_us) / 1000000.0 > warmup_seconds + 60.0:
		failure = "4K surface never stabilized before diagnostic timeout."
		stop_after_frame()
		return
	if not surface_ok:
		if measurement_started_us > 0:
			failure = "4K surface changed during diagnostic measurement."
			stop_after_frame()
			return
		warmup_stable_us = 0
		runtime.lock_qa_window_size()
	elif warmup_stable_us == 0:
		warmup_stable_us = now
	if not current.has("process_end_us") or not current.has("pre_draw_us"):
		pairing_errors.append({"reason":"missing process/pre_draw boundary","process_id":process_id})
	else:
		var ordered: bool = previous_post_us <= int(current.process_start_us) and int(current.process_start_us) <= int(current.process_end_us) and int(current.process_end_us) <= int(current.pre_draw_us) and int(current.pre_draw_us) <= now
		if not ordered: pairing_errors.append({"reason":"unordered frame boundaries","process_id":process_id})
		current.boundaries_ordered = ordered
	if measurement_started_us == 0:
		if surface_ok and float(now - started_us) / 1000000.0 >= warmup_seconds and float(now - warmup_stable_us) / 1000000.0 >= 0.25:
			measurement_started_us = now # This frame is the baseline, not a timed interval.
	else:
		var elapsed: float = float(now - measurement_started_us) / 1000000.0
		current.seconds = elapsed
		current.post_to_post_ms = float(now - previous_post_us) / 1000.0
		current.process_to_process_ms = float(int(current.process_start_us) - int(current.previous_process_start_us)) / 1000.0
		current.previous_post_to_process_ms = float(int(current.process_start_us) - previous_post_us) / 1000.0
		if current.has("process_end_us") and current.has("pre_draw_us"):
			current.process_span_ms = float(int(current.process_end_us) - int(current.process_start_us)) / 1000.0
			current.process_end_to_pre_draw_ms = float(int(current.pre_draw_us) - int(current.process_end_us)) / 1000.0
			current.pre_to_post_draw_ms = float(now - int(current.pre_draw_us)) / 1000.0
		rows.append(current)
		measurement_finished_us = now
		if elapsed >= next_memory_second:
			memory_samples.append({"seconds":elapsed,"process_id":process_id,
				"engine_static_memory_bytes":Performance.get_monitor(Performance.MEMORY_STATIC),
				"engine_video_memory_bytes":Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED),
				"node_count":Performance.get_monitor(Performance.OBJECT_NODE_COUNT)})
			next_memory_second = int(floor(elapsed)) + 1
		if elapsed >= duration_seconds:
			stop_after_frame()
	previous_post_us = now
	current = {}

func stop_after_frame() -> void:
	if finished: return
	finished = true
	runtime.set_process(false)
	runtime.paused = true
	call_deferred("finish")

func distribution(values: Array[float]) -> Dictionary:
	if values.is_empty(): return {"count":0}
	var ordered: Array[float] = values.duplicate()
	ordered.sort()
	var total: float = 0.0
	for value: float in values: total += value
	return {"count":values.size(),"total":total,"mean":total / float(values.size()),
		"p95":ordered[maxi(0,int(ceil(ordered.size() * 0.95)) - 1)],"max":ordered.back()}

func finish() -> void:
	finished = true
	var distributions: Dictionary = {}
	for key: String in ["post_to_post_ms","process_to_process_ms","previous_post_to_process_ms","process_span_ms","process_end_to_pre_draw_ms","pre_to_post_draw_ms"]:
		var values: Array[float] = []
		for row: Dictionary in rows:
			if row.has(key): values.append(float(row[key]))
		distributions[key] = distribution(values)
	var scope_distributions: Dictionary = {}
	for key: String in ["process","advance_time","advance_update","prepare_presentation","refresh","sync_source_layers","reset_state","draw_map"]:
		var inclusive: Array[float] = []
		var exclusive: Array[float] = []
		var calls: int = 0
		for row: Dictionary in rows:
			var metrics: Dictionary = row.scopes.get(key,{"calls":0,"inclusive_us":0,"exclusive_us":0})
			inclusive.append(float(metrics.inclusive_us) / 1000.0)
			exclusive.append(float(metrics.exclusive_us) / 1000.0)
			calls += int(metrics.calls)
		scope_distributions[key] = {"calls":calls,"inclusive_per_frame_ms":distribution(inclusive),"exclusive_per_frame_ms":distribution(exclusive)}
	var spikes: Array[Dictionary] = []
	var point_samples: Dictionary = {}
	for row: Dictionary in rows:
		for point: Dictionary in row.logic_updates:
			var key: String = "%s:%d" % [point.route,point.input_index_zero_based]
			if not point_samples.has(key): point_samples[key] = {"elapsed_ms":[],"slow_calls_over_50ms":0,"slow_render_frames_over_50ms":0,"samples":[]}
			var data: Dictionary = point_samples[key]
			data.elapsed_ms.append(float(point.elapsed_us) / 1000.0)
			if int(point.elapsed_us) > 50000: data.slow_calls_over_50ms += 1
			if float(row.post_to_post_ms) > 50.0: data.slow_render_frames_over_50ms += 1
			data.samples.append({"process_id":row.process_id,"seconds":row.seconds,"call_ms":float(point.elapsed_us) / 1000.0,"render_frame_ms":row.post_to_post_ms})
	var point_summary: Dictionary = {}
	for key: String in point_samples:
		var data: Dictionary = point_samples[key]
		var values: Array[float] = []
		for value: float in data.elapsed_ms: values.append(value)
		point_summary[key] = {"call_distribution_ms":distribution(values),"slow_calls_over_50ms":data.slow_calls_over_50ms,
			"slow_render_frames_over_50ms":data.slow_render_frames_over_50ms,"samples":data.samples}
	for index: int in rows.size():
		if float(rows[index].post_to_post_ms) > 50.0:
			var context: Array[Dictionary] = []
			for nearby: int in range(maxi(0,index - 2),mini(rows.size(),index + 3)): context.append(rows[nearby])
			spikes.append({"process_id":rows[index].process_id,"frame_ms":rows[index].post_to_post_ms,"context":context})
	var measured: float = float(measurement_finished_us - measurement_started_us) / 1000000.0 if measurement_started_us > 0 else 0.0
	var identity: Dictionary = runtime.qa_identity() if is_instance_valid(runtime) and runtime.startup_error.is_empty() else {}
	var report: Dictionary = {"schema":"ao_pc_character_runtime_profile_v1","diagnostic_only":true,"acceptance_run":false,
		"completed":failure.is_empty() and pairing_errors.is_empty() and measured >= duration_seconds,"error":failure,
		"requested_seconds":duration_seconds,"measured_seconds":measured,"warmup_seconds":warmup_seconds,
		"actual_surface":[last_surface.x,last_surface.y],"requested_surface":[target_size.x,target_size.y],
		"started_ticks_us":started_us,"measurement_started_ticks_us":measurement_started_us,"measurement_finished_ticks_us":measurement_finished_us,
		"engine_version":Engine.get_version_info(),"rendering_method":RenderingServer.get_current_rendering_method(),
		"driver":RenderingServer.get_current_rendering_driver_name(),"display_server":DisplayServer.get_name(),
		"max_fps":Engine.max_fps,"vsync_mode":DisplayServer.window_get_vsync_mode(),"identity":identity,
		"frames":rows.size(),"average_fps":float(rows.size()) / measured if measured > 0 else 0.0,
		"distributions":distributions,"scope_distributions":scope_distributions,"spikes_over_50ms":spikes,
		"repeated_source_point_statistics":point_summary,
		"pairing_errors":pairing_errors,"surface_changes":warmup_surface_changes,"memory_samples":memory_samples,"raw_frames":rows,
		"routes_completed":runtime.qa_routes_completed if is_instance_valid(runtime) else 0,
		"mismatched_updates":runtime.qa_mismatches if is_instance_valid(runtime) else 0,
		"no_image_readback":true,"no_screenshot":true,"writes_during_measurement":0,
		"timing_semantics":{
			"clock":"Time.get_ticks_usec, monotonic elapsed wall time; function spans are not OS thread CPU utilization",
			"alignment":"each row binds explicit _process start/end and subsequent RenderingServer pre/post draw using process_id and absolute ticks",
			"post_to_post":"previous post_draw to current post_draw; scope timings belong to the current process_id, never TIME_PROCESS's previous frame",
			"wait_gap":"previous post_draw to current _process includes frame limiting, VSync/driver/OS waiting and other engine work; not uniquely attributable",
			"render_span":"pre_draw to post_draw is elapsed render submission/engine/driver work and possible waits, NOT measured GPU execution",
			"inclusive_exclusive":"inclusive contains nested profiled calls; exclusive subtracts directly nested spans; do not sum inclusive scopes",
			"instrumentation":"profiling dictionary/timestamp overhead and retained raw rows affect timing and memory; this does not replace independent acceptance",
			"engine_time_process_monitor":"deliberately not sampled because previous-frame alignment is ambiguous"}}
	var file: FileAccess = FileAccess.open(report_path,FileAccess.WRITE)
	if file == null:
		push_error("Cannot write runtime profile: " + report_path)
		quit(1)
		return
	file.store_string(JSON.stringify(report,"\t") + "\n")
	print("CHARACTER_RUNTIME_PROFILE_COMPLETE frames=%d measured_seconds=%.3f completed=%s" % [rows.size(),measured,str(report.completed)])
	quit(0 if report.completed else 1)
