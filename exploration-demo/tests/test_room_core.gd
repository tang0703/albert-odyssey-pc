extends SceneTree
const Movement = preload("res://movement_core.gd")
const RoomMovement = preload("res://room_movement_core.gd")
const Camera = preload("res://room_camera_core.gd")

var failures: Array[String] = []
var checks: int = 0
var actor_updates: int = 0
var camera_updates: int = 0
var arguments: Dictionary = {}

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures.append(message)
		push_error(message)

func project_actor(actor: Dictionary) -> Dictionary:
	var result: Dictionary = {}
	for field: String in Movement.FIELDS: result[field] = int(actor[field])
	return result

func project_camera(state: Dictionary) -> Dictionary:
	var result: Dictionary = {}
	for field: String in Camera.FIELDS: result[field] = int(state[field])
	return result

func _initialize() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--") and "=" in argument:
			var split: int = argument.find("=")
			arguments[argument.substr(2,split-2)] = argument.substr(split+1)
	check(arguments.has("fixtures") and arguments.has("flags") and arguments.has("report"), "Real source fixtures, flags and report paths required")
	if failures.is_empty(): run_sources()
	var report: Dictionary = {"schema":"ao_pc_room_core_validation_v1","passed":failures.is_empty(),
		"checks":checks,"actor_updates":actor_updates,"completed_camera_updates":camera_updates,
		"fixture_sha256":FileAccess.get_sha256(str(arguments.get("fixtures",""))),"failures":failures,
		"scope":"Source-bound integer movement/camera and complete boundary rejection; UI and graphics are separate gates"}
	if arguments.has("report"):
		var file := FileAccess.open(arguments.report,FileAccess.WRITE)
		if file != null: file.store_string(JSON.stringify(report,"  ")+"\n")
		else: check(false,"Cannot write room core report")
	print(JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)

func run_sources() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(arguments.fixtures))
	check(parsed is Dictionary and parsed.get("schema","") == "ao_pc_room_reference_v1", "Valid room reference schema")
	if not failures.is_empty(): return
	var source: Dictionary = parsed
	var flags: PackedByteArray = FileAccess.get_file_as_bytes(arguments.flags)
	var movement := RoomMovement.new()
	var camera := Camera.new()
	check(not camera.step({},{}).ok,"Unconfigured camera refused")
	check(not movement.step_game_input({},0).ok,"Unconfigured room boundaries refused")
	var movement_setup: Dictionary = movement.configure_room(source.movement_profile,flags,source.boundaries)
	var camera_setup: Dictionary = camera.configure(source.camera_profile)
	check(movement_setup.ok,"Source movement configured: " + str(movement_setup.get("error","")))
	check(camera_setup.ok,"Source camera configured: " + str(camera_setup.get("error","")))
	if not failures.is_empty(): return
	for trace: Dictionary in source.traces:
		var actor: Dictionary = project_actor(trace.initial_actor)
		var cameras: Array = trace.initial_cameras.duplicate(true)
		var completed: Dictionary = {}
		for row: Dictionary in trace.updates: completed[int(row.update)] = row
		var ordinal: int = 0
		for record: Dictionary in trace.actor_fixture.updates:
			ordinal += 1
			var result: Dictionary = movement.step_game_input(actor,int(record.game_pad_word))
			check(result.ok and result.get("diagnostics",{}).get("applied",false),"Source route must apply: %s/%d" % [trace.id,ordinal])
			if not result.ok: return
			actor = result.state
			check(actor == project_actor(record.expected),"Movement parity: %s/%d" % [trace.id,ordinal])
			actor_updates += 1
			for slot: int in range(2):
				var moved: Dictionary = camera.step(cameras[slot],actor)
				check(moved.ok,"Camera accepts valid source state")
				if not moved.ok: return
				cameras[slot] = moved.state
				if completed.has(ordinal): check(cameras[slot] == project_camera(completed[ordinal].cameras[slot]),"Camera parity: %s/%d/%d" % [trace.id,ordinal,slot])
			if completed.has(ordinal): camera_updates += 1
		# Reset is the exact initial state; no retained previous-route delta/history.
		check(movement.initial_state() == project_actor(trace.initial_actor),"Replay reset retains original start")
	var before: Dictionary = movement.initial_state()
	before.x_word = 13536
	before.y_word = 26976
	before.slide_x_word = 0
	before.slide_y_word = 0
	var stopped: Dictionary = movement.step_game_input(before,0x8000)
	check(stopped.ok and not stopped.diagnostics.applied and stopped.state == before,"Event boundary preserves every movement field")
	check(stopped.diagnostics.get("event_boundary","") == "stair_script_boundary","Event boundary is diagnosed separately from a wall")
	for altered: Dictionary in [{"speed_limit_raw":129},{"actor_slot":true},{"limits_raw":[0,0,0,0]},{"source_sha256":"changed"}]:
		var bad: Dictionary = source.camera_profile.duplicate(true)
		bad.merge(altered,true)
		check(not camera.configure(bad).ok,"Changed camera source configuration refused")
		check(not camera.step(source.traces[0].initial_cameras[0],before).ok,"Failed camera configure invalidates old state")
	check(camera.configure(source.camera_profile).ok,"Camera can be configured again")
	var invalid: Dictionary = source.traces[0].initial_cameras[0].duplicate(true)
	invalid.offset_x = 1
	check(not camera.step(invalid,before).ok,"Unknown camera displacement refused")
	var changed_boundaries: Array = source.boundaries.duplicate(true)
	changed_boundaries[1].raw_bounds_inclusive[0] -= 1
	check(not movement.configure_room(source.movement_profile,flags,changed_boundaries).ok,"Changed event boundary refused")
	check(not movement.step_game_input(before,0).ok,"Failed boundary configure invalidates old state")
