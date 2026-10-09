extends RefCounted
## Pinned MAP001 camera arithmetic. No Node, wall clock, renderer or FPS input.

const Movement = preload("res://movement_core.gd")
const SOURCE_SHA: String = "fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6"
const FIELDS: Array[String] = ["x", "y", "display_x", "display_y", "dx", "dy", "offset_x", "offset_y"]
var configured: bool = false

static func integer_array_matches(value: Variant, expected: Array) -> bool:
	if not value is Array or value.size() != expected.size(): return false
	for index: int in expected.size():
		if expected[index] is Array:
			if not integer_array_matches(value[index],expected[index]): return false
		elif not Movement.integer(value[index]) or int(value[index]) != int(expected[index]): return false
	return true

func configure(profile: Dictionary) -> Dictionary:
	configured = false
	if not Movement._keys_match(profile, ["speed_limit_raw", "limits_raw", "actor_slot", "deadzone_raw", "source_sha256", "order", "ranges"]):
		return {"ok": false, "error": "Incomplete room camera profile"}
	if not Movement.integer(profile.speed_limit_raw) or int(profile.speed_limit_raw) != 128 or not Movement.integer(profile.actor_slot) or int(profile.actor_slot) != 0:
		return {"ok": false, "error": "Unknown room camera speed or target"}
	if profile.source_sha256 != SOURCE_SHA or not integer_array_matches(profile.limits_raw,[8192,24576,10240,25088]) or not integer_array_matches(profile.deadzone_raw,[2176,1408,3200,2432]):
		return {"ok": false, "error": "Unverified room camera identity or bounds"}
	if profile.order != "actor update; copy old camera to display fields; follow and clamp" or not integer_array_matches(profile.ranges,[[0x1580,0x15ac],[0xae32,0xaec4],[0xb028,0xb2ac]]):
		return {"ok": false, "error": "Unknown camera update order or source ranges"}
	configured = true
	return {"ok": true}

static func validate_state(state: Dictionary) -> String:
	if not Movement._keys_match(state, FIELDS): return "Incomplete camera state"
	for field: String in FIELDS:
		if not Movement.integer(state[field]) or state[field] < -32768 or state[field] > 32767: return "Invalid camera raw word: " + field
	if int(state.offset_x) != 0 or int(state.offset_y) != 0: return "Unverified camera displacement"
	return ""

static func signed16(value: int) -> int:
	var word: int = value & 65535
	return word if word < 32768 else word - 65536

func step(state: Dictionary, actor: Dictionary) -> Dictionary:
	if not configured: return {"ok": false, "error": "Room camera is not configured"}
	var error: String = validate_state(state)
	if not error.is_empty(): return {"ok": false, "error": error}
	for field: String in ["x_word", "y_word"]:
		if not actor.has(field) or not Movement.integer(actor[field]) or actor[field] < 0 or actor[field] > 32767:
			return {"ok": false, "error": "Invalid room camera target"}
	var result: Dictionary = state.duplicate(true)
	for field: String in FIELDS: result[field] = int(state[field])
	result.display_x = int(state.x)
	result.display_y = int(state.y)
	result.dx = 0
	result.dy = 0
	for parameters: Array in [["x", "x_word", 0xa80, 8192, 10240], ["y", "y_word", 0x780, 24576, 25088]]:
		var axis: String = str(parameters[0])
		var target: int = int(actor[parameters[1]])
		var original: int = int(state[axis])
		var upper: int = signed16(original + int(parameters[2]) + 0x200)
		var lower: int = signed16(original + int(parameters[2]) - 0x200)
		if target > upper:
			var delta: int = mini(128, signed16(target - upper))
			var proposed: int = signed16(original + delta)
			if proposed > int(parameters[4]):
				proposed = int(parameters[4])
				delta = 0
			result[axis] = proposed
			result["d" + axis] = delta
		if target < lower:
			var delta: int = mini(128, signed16(lower - target))
			var proposed: int = signed16(int(result[axis]) - delta)
			if proposed < int(parameters[3]):
				proposed = int(parameters[3])
				delta = 0
			result[axis] = proposed
			result["d" + axis] = -delta
	return {"ok": true, "state": result}
