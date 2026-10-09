class_name ExplorationMovement
extends RefCounted
## Source-bound integer movement. No nodes, clocks, file loading or animation.
## A rejected query domain preserves the whole input state; it is not a wall.

const SCHEMA: String = "ao_pc_exploration_movement_v1"
const FLAGS_SHA256: String = "78863dedbf02a07158821486a059af56f31a0b18d11a9eee6a7986dd10943e5b"
const ANIMATION_ROOT_SHA256: String = "e316125b1d085bdf18b62401bcf5b8fcb976f79827d2176a98c284ba30f9e99a"
const SOURCE_HASHES: Dictionary = {"TWN.BIN": "fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6",
	"0": "95054f9128b7ab47f88c6659b103e7bee9db94c13548f815bbda5999b30da2ff"}
const TICK_NUMERATOR: int = 176473
const TICK_DENOMINATOR: int = 10546875
const SHAPE: Array[int] = [-192, -96, 64, 384, 192]
const PAD_WORDS: Dictionary = {"none": 0, "up": 0x1000, "down": 0x2000, "left": 0x4000, "right": 0x8000}
const FIELDS: Dictionary = {
	"x_word": [0, 2], "y_word": [2, 2], "status_word": [6, 2], "flags_word": [8, 2],
	"selector_word": [10, 2], "mode_word": [22, 2], "dx_word": [24, 2], "dy_word": [26, 2],
	"slide_x_word": [30, 2], "slide_y_word": [32, 2], "speed_index": [36, 2],
	"heading": [38, 2], "shape_index": [41, 1], "animation_index": [54, 2],
	"free_direction": [72, 1], "center_flag": [74, 1], "contact_bits": [75, 1],
}
const PROFILE_KEYS: Array[String] = ["schema", "actor_address", "control_word", "disabled_byte",
	"initial_state", "flags_sha256", "animation_root_sha256", "source_hashes", "shape_raw", "verified_query_indices",
	"logical_tick_seconds", "comparison_fields"]
const DIRECTION_NIBBLES: Array[int] = [255, 6, 2, 255, 4, 5, 3, 255, 0, 7, 1, 255, 255, 255, 255, 255]
const SPEED_COMPONENTS: Array = [[8, 6], [16, 11], [24, 17], [32, 22], [40, 28], [48, 34]]

var _profile: Dictionary = {}
var _flags: PackedByteArray = PackedByteArray()
var _verified: Dictionary = {}

static func integer(value: Variant) -> bool:
	return typeof(value) == TYPE_INT or (typeof(value) == TYPE_FLOAT and is_finite(value) and value == floor(value))

static func _keys_match(value: Dictionary, keys: Array) -> bool:
	if value.size() != keys.size():
		return false
	for key: Variant in keys:
		if not value.has(key):
			return false
	return true

static func validate_state(state: Dictionary) -> String:
	if not _keys_match(state, FIELDS.keys()):
		return "Movement state fields differ from versioned contract"
	for key: String in FIELDS:
		var maximum: int = (1 << (int(FIELDS[key][1]) * 8)) - 1
		if not integer(state[key]) or state[key] < 0 or state[key] > maximum:
			return "Invalid raw field: " + key
	if int(state.shape_index) != 1 or int(state.flags_word) != 9 or int(state.heading) >= 8 or int(state.speed_index) != 3:
		return "Unsupported controlled actor configuration"
	if (int(state.status_word) & ~(2 | 0x200)) != 0x8180:
		return "Unsupported actor dispatch/status mode"
	return ""

func configure(profile: Dictionary, flags: PackedByteArray) -> Dictionary:
	# Failure invalidates a previously configured core rather than retaining it.
	_profile.clear()
	_flags = PackedByteArray()
	_verified.clear()
	var error: String = _validate_profile(profile, flags)
	if not error.is_empty():
		return {"ok": false, "error": error}
	_profile = profile.duplicate(true)
	for key: String in FIELDS:
		_profile.initial_state[key] = int(profile.initial_state[key])
	_flags = flags.duplicate()
	for index: Variant in profile.verified_query_indices:
		_verified[int(index)] = true
	return {"ok": true, "error": ""}

static func _validate_profile(profile: Dictionary, flags: PackedByteArray) -> String:
	if not _keys_match(profile, PROFILE_KEYS) or profile.get("schema") != SCHEMA:
		return "Unknown or incomplete movement profile schema"
	if profile.flags_sha256 != FLAGS_SHA256 or profile.animation_root_sha256 != ANIMATION_ROOT_SHA256:
		return "Unknown scene flags or animation root identity"
	if not profile.source_hashes is Dictionary or profile.source_hashes != SOURCE_HASHES:
		return "Unknown movement source identity"
	if flags.size() != 65536:
		return "Expected exactly 65536 scene flag bytes"
	var hashing := HashingContext.new()
	if hashing.start(HashingContext.HASH_SHA256) != OK or hashing.update(flags) != OK or hashing.finish().hex_encode() != FLAGS_SHA256:
		return "Scene flag content hash mismatch"
	for key: String in ["actor_address", "control_word", "disabled_byte"]:
		if not integer(profile[key]):
			return "Invalid control field: " + key
	if int(profile.actor_address) != 0x060c8758 or int(profile.control_word) != 3 or int(profile.disabled_byte) != 0:
		return "Unsupported controlled slot or control gates"
	if not profile.initial_state is Dictionary:
		return "Initial movement state is missing"
	var state_error: String = validate_state(profile.initial_state)
	if not state_error.is_empty():
		return state_error
	if not profile.shape_raw is Array or profile.shape_raw.size() != SHAPE.size():
		return "Unsupported shape record"
	for index: int in SHAPE.size():
		if not integer(profile.shape_raw[index]) or int(profile.shape_raw[index]) != SHAPE[index]:
			return "Unsupported shape record"
	if not profile.verified_query_indices is Array or profile.verified_query_indices.is_empty():
		return "A nonempty verified flag-query domain is required"
	var seen: Dictionary = {}
	for index: Variant in profile.verified_query_indices:
		if not integer(index) or index < 0 or index >= 65536 or seen.has(int(index)):
			return "Invalid or repeated verified flag-query index"
		seen[int(index)] = true
	if not profile.logical_tick_seconds is Dictionary or not _keys_match(profile.logical_tick_seconds, ["numerator", "denominator"]):
		return "Unknown logical update period"
	if not integer(profile.logical_tick_seconds.numerator) or not integer(profile.logical_tick_seconds.denominator):
		return "Logical update period must use integer terms"
	if int(profile.logical_tick_seconds.numerator) != TICK_NUMERATOR or int(profile.logical_tick_seconds.denominator) != TICK_DENOMINATOR:
		return "Unknown logical update period"
	if not profile.comparison_fields is Dictionary or not _keys_match(profile.comparison_fields, FIELDS.keys()):
		return "Unknown state comparison contract"
	for key: String in FIELDS:
		var definition: Variant = profile.comparison_fields[key]
		if not definition is Dictionary or not _keys_match(definition, ["offset", "bytes", "mask"]):
			return "Invalid comparison definition: " + key
		for member: String in ["offset", "bytes", "mask"]:
			if not integer(definition[member]):
				return "Comparison definition is not integral: " + key
		if int(definition.offset) != FIELDS[key][0] or int(definition.bytes) != FIELDS[key][1] or int(definition.mask) != (1 << (int(FIELDS[key][1]) * 8)) - 1:
			return "Changed comparison field: " + key
	return ""

func initial_state() -> Dictionary:
	return {} if _profile.is_empty() else _profile.initial_state.duplicate(true)

func metadata() -> Dictionary:
	return _profile.duplicate(true)

static func _failure(state: Dictionary, error: String) -> Dictionary:
	return {"ok": false, "state": state.duplicate(true), "diagnostics": {"applied": false, "reason": "invalid_input"}, "error": error}

func step(state: Dictionary, direction: String) -> Dictionary:
	if not PAD_WORDS.has(direction):
		return _failure(state, "Unknown direction")
	return step_game_input(state, int(PAD_WORDS[direction]))

func step_game_input(state: Dictionary, pad_word: Variant) -> Dictionary:
	if _profile.is_empty():
		return _failure(state, "Movement profile is not configured")
	if not integer(pad_word) or not PAD_WORDS.values().has(int(pad_word)):
		return _failure(state, "Only one cardinal direction or no input is supported")
	var error: String = validate_state(state)
	if not error.is_empty():
		return _failure(state, error)
	var next: Dictionary = state.duplicate(true)
	for key: String in FIELDS:
		next[key] = int(next[key])
	_input_gate(next, int(pad_word))
	if int(next.status_word) & 2:
		_velocity(next)
	else:
		next.animation_index = int(next.heading) if int(next.flags_word) & 1 else int(next.heading) >> 1
	# Deferred perpendicular correction is consumed even after input release.
	next.dx_word = (int(next.dx_word) + int(next.slide_x_word)) & 65535
	next.dy_word = (int(next.dy_word) + int(next.slide_y_word)) & 65535
	next.slide_x_word = 0
	next.slide_y_word = 0
	var result: Dictionary = _collision_step(next, _flags)
	if not result.ok:
		return _failure(state, result.error)
	var diagnostics: Dictionary = result.diagnostics
	var outside: Array[int] = []
	for lookup: Dictionary in diagnostics.lookups:
		var index: int = int(lookup.index)
		if not _verified.has(index) and not outside.has(index):
			outside.append(index)
	if not outside.is_empty():
		outside.sort()
		return {"ok": true, "state": state.duplicate(true), "error": "", "diagnostics": {
			"applied": false, "reason": "test_boundary", "unverified_query_indices": outside, "lookups": diagnostics.lookups}}
	diagnostics.merge({"applied": true, "reason": null, "game_pad_word": int(pad_word)})
	return {"ok": true, "state": result.state, "diagnostics": diagnostics, "error": ""}

static func signed16(value: int) -> int:
	value &= 65535
	return value - 65536 if value & 32768 else value

static func divide16(value: int) -> int:
	# SH-2 C helper truncates towards zero, unlike signed arithmetic shift.
	@warning_ignore("integer_division")
	var magnitude: int = absi(value) / 16
	return -magnitude if value < 0 else magnitude

static func _input_gate(state: Dictionary, pad_word: int) -> void:
	state.status_word = int(state.status_word) & 0xfffd
	state.dx_word = 0
	state.dy_word = 0
	var direction: int = DIRECTION_NIBBLES[(pad_word >> 12) & 15]
	# configure rejects every unsupported actor/control gate combination.
	if direction != 255:
		state.heading = direction
		state.status_word = int(state.status_word) | 2
	state.speed_index = 3

static func _velocity(state: Dictionary) -> void:
	var speed: int = int(state.speed_index)
	var heading: int = int(state.heading)
	var straight: int = SPEED_COMPONENTS[speed][0]
	var diagonal: int = SPEED_COMPONENTS[speed][1]
	var xs: Array[int] = [straight, diagonal, 0, -diagonal, -straight, -diagonal, 0, diagonal]
	var ys: Array[int] = [0, diagonal, straight, diagonal, 0, -diagonal, -straight, -diagonal]
	state.dx_word = xs[heading] & 65535
	state.dy_word = ys[heading] & 65535
	state.animation_index = 8 + heading if int(state.flags_word) & 1 else 4 + (heading >> 1)

static func _sample(flags: PackedByteArray, x: int, y: int, axis: String, lookups: Array[Dictionary]) -> int:
	var index: int = (y >> 3) * 256 + (x >> 3)
	if index < 0 or index >= flags.size():
		return -1
	var flag: int = flags[index]
	lookups.append({"axis": axis, "x": x, "y": y, "index": index, "flag": flag})
	return flag

static func _contact(state: Dictionary, bit: int) -> void:
	state.contact_bits = int(state.contact_bits) | bit
	state.status_word = int(state.status_word) | 0x200

static func _queue_slide(state: Dictionary, field: String, bitmap: int, count: int, correction: int) -> void:
	if not (bitmap & (1 << count)):
		state[field] = -correction & 65535
	elif not (bitmap & 2):
		state[field] = correction & 65535

static func _collision_step(input_state: Dictionary, flags: PackedByteArray) -> Dictionary:
	var state: Dictionary = input_state.duplicate(true)
	var lookups: Array[Dictionary] = []
	var selector: int = int(state.selector_word)
	var mask: int = 0x80 if selector == 0 else 0x40
	var mode_mask: int = 0x20 if selector == 0 else 0x10
	var before: Array[int] = [int(state.x_word), int(state.y_word)]
	state.free_direction = 0
	state.contact_bits = 0
	state.status_word = int(state.status_word) & ~0x200
	var dx: int = signed16(state.dx_word)
	var dy: int = signed16(state.dy_word)
	var bypass: bool = bool(int(state.status_word) & 0x20)
	state.x_word = (int(state.x_word) + dx) & 65535
	if dx != 0 and not bypass:
		var top_unmasked: int = divide16(signed16(state.y_word) + SHAPE[1])
		var top: int = top_unmasked & 0x7ff
		var bottom: int = (top_unmasked + divide16(SHAPE[4]) - 1) & 0x7ff
		bottom += 7 - (bottom & 7)
		var edge: int = divide16(signed16(state.x_word) + SHAPE[0]) & 0x7ff
		if dx > 0:
			edge = (edge + divide16(SHAPE[3]) - 1) & 65535
		var bitmap: int = 0
		var count: int = 0
		var cursor: int = top
		while cursor <= bottom:
			cursor &= 0x7ff
			var flag: int = _sample(flags, edge, cursor, "x", lookups)
			if flag < 0:
				return {"ok": false, "error": "Original lookup exceeds captured flags; no inferred boundary"}
			bitmap = ((bitmap + int(bool(flag & mask))) * 2) & 0xffffffff
			count += 1
			cursor += 8
			if count > 256:
				return {"ok": false, "error": "Unsupported wrapping scan"}
		if signed16(bitmap) != 0:
			var correction: int = ((edge & 7) + 1 if dx > 0 else 8 - (edge & 7)) * 16
			state.x_word = (int(state.x_word) + (-correction if dx > 0 else correction)) & 0xfff0
			_contact(state, 8 if dx > 0 else 4)
			if dy == 0:
				_queue_slide(state, "slide_y_word", bitmap, count, correction)
		else:
			state.free_direction = 8 if dx > 0 else 4
	state.y_word = (int(state.y_word) + dy) & 65535
	if dy != 0 and not bypass:
		var edge: int = divide16(signed16(state.y_word) + SHAPE[1]) & 0x7ff
		var left: int = divide16(signed16(state.x_word) + SHAPE[0]) & 0x7ff
		if dy > 0:
			edge += divide16(SHAPE[4]) - 1
		var last_sample: int = divide16(SHAPE[3]) >> 3
		if (left & 7) == 0:
			last_sample -= 1
		var bitmap: int = 0
		var count: int = 0
		var cursor: int = left
		for unused_index: int in range(last_sample + 1):
			cursor &= 0x7ff
			var flag: int = _sample(flags, cursor, edge, "y", lookups)
			if flag < 0:
				return {"ok": false, "error": "Original lookup exceeds captured flags; no inferred boundary"}
			bitmap = ((bitmap + int(bool(flag & mask))) * 2) & 0xffffffff
			count += 1
			cursor += 8
		if signed16(bitmap) != 0:
			var correction: int = ((edge & 7) + 1 if dy > 0 else 8 - (edge & 7)) * 16
			state.y_word = (int(state.y_word) + (-correction if dy > 0 else correction)) & 0xfff0
			_contact(state, 2 if dy > 0 else 1)
			if dx == 0:
				_queue_slide(state, "slide_x_word", bitmap, count, correction)
		else:
			state.free_direction = 2 if dy > 0 else 1
	var center: int = _sample(flags, (signed16(state.x_word) >> 4) & 0x7ff, (signed16(state.y_word) >> 4) & 0x7ff, "center", lookups)
	if center < 0:
		return {"ok": false, "error": "Original center lookup exceeds captured flags; no inferred boundary"}
	if int(state.mode_word) & 0x10:
		state.mode_word = (int(state.mode_word) & 0xff00) | (0x13 if center & mode_mask else 0x12)
	if center & 8:
		state.selector_word = 255
	if center & 4:
		state.selector_word = 0
	state.center_flag = center
	return {"ok": true, "state": state, "diagnostics": {
		"routine_runtime": "0x060AB61A", "shape_index": int(state.shape_index), "initial_selector": selector,
		"blocking_mask": mask, "mode_mask": mode_mask, "collision_bypassed": bypass,
		"before": before, "after": [state.x_word, state.y_word], "delta_words": [state.dx_word, state.dy_word],
		"global_writes": [{"address": "0x060DDDC4", "size": 2, "value": before[0]},
			{"address": "0x060DDDC6", "size": 2, "value": before[1]}],
		"contact_bits": state.contact_bits, "free_direction_byte": state.free_direction,
		"queued_slide_words": [state.slide_x_word, state.slide_y_word], "lookups": lookups, "dynamic_verified": false}}
