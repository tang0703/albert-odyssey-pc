extends SceneTree
## Run with -- --profile=... --fixtures=... --flags=... [--report=...].
## --flags-wram-low=... is an explicit alternative for a 1 MiB RAM dump.
## Without local inputs, only synthetic checks run; source validation is not claimed.
const Core = preload("res://movement_core.gd")

var checks: int = 0
var failures: Array[String] = []
var update_count: int = 0
var route_count: int = 0
var source_status: String = "not_run"
var arguments: Dictionary = {}
var source_inputs: Dictionary = {}

func check(value: bool, message: String) -> bool:
	checks += 1
	if not value:
		failures.append(message)
		push_error(message)
	return value

func synthetic_state() -> Dictionary:
	var state: Dictionary = {}
	for key: String in Core.FIELDS:
		state[key] = 0
	state.merge({"x_word": 1024, "y_word": 1024, "status_word": 0x8180,
		"flags_word": 9, "mode_word": 18, "speed_index": 3, "shape_index": 1}, true)
	return state

func _initialize() -> void:
	for value: String in OS.get_cmdline_user_args():
		if value.begins_with("--") and "=" in value:
			var delimiter: int = value.find("=")
			arguments[value.substr(2, delimiter - 2)] = value.substr(delimiter + 1)
	_synthetic_checks()
	if arguments.has("profile") or arguments.has("fixtures") or arguments.has("flags") or arguments.has("flags-wram-low"):
		_source_checks()
	var report: Dictionary = {"schema": "ao_pc_godot_movement_validation_v1", "passed": failures.is_empty(),
		"checks": checks, "synthetic_checks_ran": true, "source_comparison_status": source_status,
		"traces": route_count, "updates": update_count, "fields_per_update": Core.FIELDS.size(),
		"differing_fields": failures, "source_inputs": source_inputs,
		"scope": "Pure movement port and source fixtures; no GUI or rendering performance acceptance"}
	if arguments.has("report"):
		var output := FileAccess.open(arguments.report, FileAccess.WRITE)
		if output == null:
			push_error("Cannot write requested report")
			quit(1)
			return
		output.store_string(JSON.stringify(report, "  ") + "\n")
	print(JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)

func _synthetic_checks() -> void:
	check(Core.signed16(65535) == -1 and Core.signed16(32768) == -32768, "Signed word conversion")
	check(Core.divide16(-1) == 0 and Core.divide16(-17) == -1 and Core.divide16(31) == 1, "Signed division truncates towards zero")
	check(not Core.integer(true) and not Core.integer(1.5) and not Core.integer(INF), "Non-integral input rejected")
	var core = Core.new()
	var state: Dictionary = synthetic_state()
	check(Core.validate_state(state).is_empty(), "Synthetic supported actor")
	check(not core.step(state, "up").ok, "Unconfigured core refuses movement")
	check(not core.configure({}, PackedByteArray()).ok, "Incomplete profile refused")
	for field: String in ["shape_index", "flags_word", "status_word", "speed_index", "heading"]:
		var invalid: Dictionary = state.duplicate(true)
		invalid[field] = 255
		check(not Core.validate_state(invalid).is_empty(), "Unsupported state field rejected: " + field)
	var fractional: Dictionary = state.duplicate(true)
	fractional.x_word = 4.5
	check(not Core.validate_state(fractional).is_empty(), "Fractional raw word rejected")
	var flags := PackedByteArray()
	flags.resize(65536)
	state.dx_word = 32
	var before: Dictionary = state.duplicate(true)
	var free: Dictionary = Core._collision_step(state, flags)
	check(free.ok and free.state.x_word == 1056 and free.state.y_word == 1024, "Synthetic free movement")
	check(state == before, "Collision helper preserves caller state")
	# 0x20 controls mode only. It is not a universal blocking bit.
	flags.fill(0x20)
	var mode_only: Dictionary = Core._collision_step(state, flags)
	check(mode_only.ok and mode_only.state.x_word == 1056 and mode_only.state.contact_bits == 0 and mode_only.state.mode_word == 0x13, "0x20 does not become a wall")
	flags.fill(0x80)
	var blocked: Dictionary = Core._collision_step(state, flags)
	check(blocked.ok and blocked.state.contact_bits == 8 and blocked.state.x_word < 1056, "Selector-zero mask blocks right edge")
	state.selector_word = 255
	var other_layer: Dictionary = Core._collision_step(state, flags)
	check(other_layer.ok and other_layer.state.contact_bits == 0 and other_layer.state.x_word == 1056, "Selector changes collision mask")
	flags.fill(0x40)
	check(Core._collision_step(state, flags).state.contact_bits == 8, "Alternate selector mask blocks")
	var neutral: Dictionary = synthetic_state()
	neutral.slide_y_word = 32
	Core._input_gate(neutral, 0)
	check(neutral.slide_y_word == 32 and neutral.dx_word == 0 and neutral.dy_word == 0, "Input release preserves deferred correction")
	for pair: Array in [["up", 6, 0, 65504], ["down", 2, 0, 32], ["left", 4, 65504, 0], ["right", 0, 32, 0]]:
		var moving: Dictionary = synthetic_state()
		Core._input_gate(moving, Core.PAD_WORDS[pair[0]])
		Core._velocity(moving)
		check(moving.heading == pair[1] and moving.dx_word == pair[2] and moving.dy_word == pair[3], "Direction velocity " + str(pair[0]))

func _read_json(path: String) -> Dictionary:
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(path)) != OK or not parser.data is Dictionary:
		check(false, "Invalid JSON: " + path)
		return {}
	return parser.data

func _source_checks() -> void:
	source_status = "failed"
	if not check(arguments.has("profile") and arguments.has("fixtures") and (arguments.has("flags") != arguments.has("flags-wram-low")), "Supply profile, fixtures and exactly one flags source"):
		return
	var profile: Dictionary = _read_json(arguments.profile)
	var fixtures: Dictionary = _read_json(arguments.fixtures)
	if profile.is_empty() or fixtures.is_empty():
		return
	for name: String in ["profile", "fixtures", "flags", "flags-wram-low"]:
		if arguments.has(name):
			source_inputs[name] = {"path": arguments[name], "sha256": FileAccess.get_sha256(arguments[name])}
	var flags := PackedByteArray()
	if arguments.has("flags"):
		flags = FileAccess.get_file_as_bytes(arguments.flags)
	else:
		var low: PackedByteArray = FileAccess.get_file_as_bytes(arguments["flags-wram-low"])
		if not check(low.size() == 0x100000, "WRAM-low source must be exactly 1 MiB"):
			return
		flags = low.slice(0x10000, 0x20000)
	var core = Core.new()
	var configured: Dictionary = core.configure(profile, flags)
	if not check(configured.ok, "Source profile configure: " + str(configured.error)):
		return
	if not check(fixtures.get("schema") == Core.SCHEMA and fixtures.get("passed") == true and fixtures.get("profile") == profile and fixtures.get("traces") is Array, "Source fixture/profile contract"):
		return
	var saved_initial: Dictionary = core.initial_state()
	var isolated: Dictionary = core.initial_state()
	isolated.x_word = 0
	check(core.initial_state() == saved_initial, "Initial-state caller cannot mutate core")
	for trace: Dictionary in fixtures.traces:
		route_count += 1
		var state: Dictionary = trace.initial_state.duplicate(true)
		check(Core.validate_state(state).is_empty(), "Trace initial state valid")
		for update: Dictionary in trace.updates:
			var before: Dictionary = state.duplicate(true)
			var result: Dictionary = core.step_game_input(state, update.game_pad_word)
			if not check(result.ok and result.diagnostics.applied, "Captured step applied: " + str(trace.capture) + " frame " + str(update.frame)):
				return
			check(state == before, "Step cannot mutate input state")
			state = result.state
			update_count += 1
			for key: String in Core.FIELDS:
				if not check(int(state[key]) == int(update.expected[key]), "Source mismatch %s frame %s field %s expected %s got %s" % [trace.capture, update.frame, key, update.expected[key], state[key]]):
					return
			var queried: Array[int] = []
			for item: Dictionary in result.diagnostics.lookups:
				if not queried.has(int(item.index)):
					queried.append(int(item.index))
			queried.sort()
			var expected_queries: Array[int] = []
			for item: Variant in update.query_indices:
				expected_queries.append(int(item))
			check(queried == expected_queries, "Source flag-query indices agree")
	check(core.initial_state() == saved_initial, "Replay does not mutate initial state")
	_defensive_checks(profile, flags, core)
	if failures.is_empty():
		source_status = "passed"

func _defensive_checks(profile: Dictionary, flags: PackedByteArray, core: RefCounted) -> void:
	var state: Dictionary = core.initial_state()
	for input: Variant in [-1, 0x3000, 0xffff, true, 0.5, "up"]:
		var invalid: Dictionary = core.step_game_input(state, input)
		check(not invalid.ok and invalid.state == state, "Invalid input is atomic: " + str(input))
	check(not core.step(state, "up+left").ok, "Multiple direction string rejected")
	var corrupt: PackedByteArray = flags.duplicate()
	corrupt[0] ^= 1
	var guarded = Core.new()
	check(not guarded.configure(profile, corrupt).ok, "Changed flag bytes refused")
	check(not guarded.configure(profile, flags.slice(0, 100)).ok, "Truncated flag bytes refused")
	for pair: Array in [["schema", "unknown"], ["shape_raw", [0, 0, 0, 1, 1]], ["animation_root_sha256", "bad"],
		["source_hashes", {"TWN.BIN": "bad", "0": "bad"}],
		["control_word", 1], ["actor_address", 0x060c87c8], ["verified_query_indices", []],
		["verified_query_indices", [65536]], ["verified_query_indices", [1, 1]],
		["logical_tick_seconds", {"numerator": 1, "denominator": 60}]]:
		var invalid_profile: Dictionary = profile.duplicate(true)
		invalid_profile[pair[0]] = pair[1]
		check(not guarded.configure(invalid_profile, flags).ok, "Invalid profile refused: " + str(pair[0]))
	var missing: Dictionary = profile.duplicate(true)
	missing.erase("shape_raw")
	check(not guarded.configure(missing, flags).ok, "Missing profile field refused")
	var altered_mask: Dictionary = profile.duplicate(true)
	altered_mask.comparison_fields.x_word.mask = 255
	check(not guarded.configure(altered_mask, flags).ok, "Changed comparison mask refused")
	var small: Dictionary = profile.duplicate(true)
	small.verified_query_indices = [0]
	check(guarded.configure(small, flags).ok, "Explicit smaller domain accepted")
	var boundary: Dictionary = guarded.step(state, "right")
	check(boundary.ok and not boundary.diagnostics.applied and boundary.diagnostics.reason == "test_boundary" and boundary.state == state, "Unknown region rejects the whole update without creating a wall")
	check(not guarded.configure({}, flags).ok and not guarded.step(state, "none").ok, "Failed configuration clears previous profile")
