extends SceneTree
## -- --fixtures=... --movement-profile=... --wram-low=... [--report=...]
## Without local inputs only defensive checks run; source parity is not claimed.
const AnimationCore = preload("res://character_animation_core.gd")
const Movement = preload("res://movement_core.gd")

var checks: int = 0
var failures: Array[String] = []
var updates: int = 0
var traces: int = 0
var source_status: String = "not_run"
var arguments: Dictionary = {}
var source_inputs: Dictionary = {}

func check(ok: bool, message: String) -> bool:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)
	return ok

func _initialize() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--") and "=" in argument:
			var equal: int = argument.find("=")
			arguments[argument.substr(2,equal - 2)] = argument.substr(equal + 1)
	var core = AnimationCore.new()
	check(not core.configure({},PackedByteArray(),PackedByteArray()).ok,"Incomplete animation profile refused")
	check(not core.step_after_movement({},{}).ok,"Unconfigured animation core refused")
	check(AnimationCore.project_state({}).is_empty(),"Empty actor projection remains invalid")
	if arguments.has("fixtures") or arguments.has("movement-profile") or arguments.has("wram-low"):
		_source_checks()
	var report: Dictionary = {"schema":"ao_pc_godot_character_animation_validation_v1","passed":failures.is_empty(),
		"checks":checks,"source_comparison_status":source_status,"traces":traces,"updates":updates,
		"animation_fields_per_update":AnimationCore.FIELDS.size(),"source_inputs":source_inputs,"failures":failures,
		"scope":"Pure animation state paired with the existing movement core; no UI or image rendering acceptance"}
	if arguments.has("report"):
		var output := FileAccess.open(arguments.report,FileAccess.WRITE)
		if output == null:
			push_error("Cannot write character animation validation report")
			quit(1)
			return
		output.store_string(JSON.stringify(report,"  ") + "\n")
	print(JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)

func _read_json(path: String) -> Dictionary:
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(path)) != OK or not parser.data is Dictionary:
		check(false,"Invalid source JSON: " + path)
		return {}
	return parser.data

func _source_checks() -> void:
	source_status = "failed"
	if not check(arguments.has("fixtures") and arguments.has("movement-profile") and arguments.has("wram-low"),"Source parity requires fixtures, movement profile and WRAM-low"):
		return
	for key: String in ["fixtures","movement-profile","wram-low"]:
		source_inputs[key] = {"path":arguments[key],"sha256":FileAccess.get_sha256(arguments[key])}
	var fixtures: Dictionary = _read_json(arguments.fixtures)
	var movement_profile: Dictionary = _read_json(arguments["movement-profile"])
	var low: PackedByteArray = FileAccess.get_file_as_bytes(arguments["wram-low"])
	if not check(low.size() == 0x100000,"WRAM-low must be complete"):
		return
	if not check(fixtures.get("schema") == AnimationCore.SCHEMA and fixtures.get("passed") == true and fixtures.get("profile") is Dictionary and fixtures.get("traces") is Array and not fixtures.traces.is_empty(),"Animation fixtures must contain passed source profile and traces"):
		return
	var animation = AnimationCore.new()
	var movement = Movement.new()
	var bank: PackedByteArray = low.slice(0x20010,0x20158)
	var images: PackedByteArray = low.slice(0x20158,0x201f8)
	var configured: Dictionary = animation.configure(fixtures.profile,bank,images)
	if not check(configured.ok,"Animation source configuration: " + str(configured.error)):
		return
	configured = movement.configure(movement_profile,low.slice(0x10000,0x20000))
	if not check(configured.ok,"Movement source configuration: " + str(configured.error)):
		return
	for trace: Dictionary in fixtures.traces:
		traces += 1
		var moving: Dictionary = movement.initial_state()
		var animated: Dictionary = animation.initial_state()
		if not check(AnimationCore.project_state(trace.initial_state) == animated and AnimationCore.project_movement(trace.initial_state) == moving,"Shared initial state matches both independent cores"):
			return
		for row: Dictionary in trace.updates:
			var movement_before: Dictionary = moving.duplicate(true)
			var animation_before: Dictionary = animated.duplicate(true)
			var moved: Dictionary = movement.step_game_input(moving,row.game_pad_word)
			if not check(moved.ok and moved.diagnostics.applied,"Source movement applies before animation"):
				return
			var result: Dictionary = animation.step_after_movement(animated,moved)
			if not check(result.ok and result.diagnostics.applied,"Source animation applies: " + str(result.error)):
				return
			check(moving == movement_before and animated == animation_before,"Neither core mutates caller-owned state")
			moving = moved.state
			animated = result.state
			updates += 1
			for key: String in Movement.FIELDS:
				if not check(int(moving[key]) == int(row.expected[key]),"Movement divergence frame %s field %s" % [row.frame,key]): return
			for key: String in AnimationCore.FIELDS:
				if not check(int(animated[key]) == int(row.expected[key]),"Animation divergence frame %s field %s expected %s got %s" % [row.frame,key,row.expected[key],animated[key]]): return
			check(result.diagnostics.advanced == row.advanced and result.diagnostics.wrapped == row.wrapped,"Timer advance and wrap agree with source-bound Python")
	_defensive_checks(fixtures.profile,bank,images,animation,movement)
	if failures.is_empty(): source_status = "passed"

func _defensive_checks(profile: Dictionary, bank: PackedByteArray, images: PackedByteArray, animation: RefCounted, movement: RefCounted) -> void:
	var initial: Dictionary = animation.initial_state()
	var isolated: Dictionary = animation.initial_state()
	isolated.animation_timer = 9
	check(animation.initial_state() == initial,"Initial animation state cannot be mutated by its caller")
	var move: Dictionary = movement.step(movement.initial_state(),"right")
	for pair: Array in [["animation_timer",10],["image_pointer",0],["image_index",1],["heading",1],["animation_root",0],["render_flags_word",1],["animation_duration",10]]:
		var bad: Dictionary = initial.duplicate(true)
		bad[pair[0]] = pair[1]
		var refused: Dictionary = animation.step_after_movement(bad,move)
		check(not refused.ok and refused.state == bad,"Invalid cache/state is rejected atomically: " + str(pair[0]))
	var boundary: Dictionary = animation.step_after_movement(initial,{"ok":true,"state":movement.initial_state(),"diagnostics":{"applied":false,"reason":"test_boundary"}})
	check(boundary.ok and not boundary.diagnostics.applied and boundary.state == initial,"Movement test boundary does not advance animation")
	check(not animation.step_after_movement(initial,{}).ok,"Missing movement result rejected")
	check(not animation.step_after_movement(initial,{"ok":true,"state":{},"diagnostics":{"applied":false,"reason":"test_boundary"}}).ok,"Invalid movement result is rejected even at a boundary")
	var fractional: Dictionary = initial.duplicate(true)
	fractional.animation_timer = 0.5
	check(not animation.step_after_movement(fractional,move).ok,"Fractional timer refused")
	var guard = AnimationCore.new()
	var corrupt: PackedByteArray = bank.duplicate()
	corrupt[0] ^= 1
	check(not guard.configure(profile,corrupt,images).ok,"Changed animation bank rejected")
	corrupt = images.duplicate()
	corrupt[0] ^= 1
	check(not guard.configure(profile,bank,corrupt).ok,"Changed image-pointer table rejected")
	for pair: Array in [["schema","unknown"],["actor_address",0x060c87c8],["animation_root",0],
		["animation_bank_sha256","bad"],["source_code_sha256","bad"],["supported_headings",[0,1]],
		["logical_tick_seconds",{"numerator":1,"denominator":60}]]:
		var bad: Dictionary = profile.duplicate(true)
		bad[pair[0]] = pair[1]
		check(not guard.configure(bad,bank,images).ok,"Invalid animation profile refused: " + str(pair[0]))
	var mask: Dictionary = profile.duplicate(true)
	mask.comparison_fields.image_pointer.mask = 65535
	check(not guard.configure(mask,bank,images).ok,"Changed pointer comparison mask rejected")
	check(guard.configure(profile,bank,images).ok,"Guard can be configured with known sources")
	check(not guard.configure({},bank,images).ok and not guard.step_after_movement(initial,move).ok,"Failed configuration clears previously valid sources")
