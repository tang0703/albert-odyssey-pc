extends "res://movement_core.gd"
## The original collision model plus explicit source event test boundaries.
## Rejecting an event preserves the complete input state; it is not a wall.

const MAP_SHA: String = "8216f3dfd7ae8ca7fb8cee0129f7431de7f72939e75b22be1a74f030bf4535e9"
const RoomCamera = preload("res://room_camera_core.gd")
var boundaries: Array = []
var room_configured: bool = false

func configure(profile: Dictionary, flags: PackedByteArray) -> Dictionary:
	room_configured = false
	boundaries.clear()
	return super.configure(profile, flags)

func configure_room(profile: Dictionary, flags: PackedByteArray, records: Array) -> Dictionary:
	room_configured = false
	boundaries.clear()
	var result: Dictionary = super.configure(profile, flags)
	if not result.ok: return result
	if records.size() != 2: return {"ok": false, "error": "Unknown room event boundary population"}
	for index: int in range(2):
		if not records[index] is Dictionary: return {"ok": false, "error": "Invalid room boundary record"}
		var record: Dictionary = records[index]
		var keys: Array[String] = ["id", "type", "raw_bounds_inclusive", "source_offset", "runtime_address", "source_sha256"]
		if index == 1: keys.append_array(["event_pointer", "event_file_offset"])
		if not _keys_match(record, keys): return {"ok": false, "error": "Incomplete room boundary contract"}
		var expected: Array = [["stair_scene_boundary",0,[13696,26880,14576,27008],0x1580,0x060cb55a],
			["stair_script_boundary",2,[13568,26368,14080,27136],0x1590,0x060cb57a]][index]
		for field: String in ["type", "source_offset", "runtime_address"]:
			if not integer(record[field]): return {"ok": false, "error": "Invalid raw boundary field"}
		if record.id != expected[0] or int(record.type) != expected[1] or not RoomCamera.integer_array_matches(record.raw_bounds_inclusive,expected[2]) or int(record.source_offset) != expected[3] or int(record.runtime_address) != expected[4] or record.source_sha256 != MAP_SHA:
			return {"ok": false, "error": "Room event boundary differs from confirmed source"}
		if index == 1 and (not integer(record.event_pointer) or not integer(record.event_file_offset) or int(record.event_pointer) != 0x260e2f1a or int(record.event_file_offset) != 0x2f22):
			return {"ok": false, "error": "Unverified staircase event pointer"}
	boundaries = records.duplicate(true)
	room_configured = true
	return {"ok": true}

func step_game_input(state: Dictionary, pad_word: Variant) -> Dictionary:
	if not room_configured: return {"ok": false, "error": "Room boundaries are not configured"}
	var result: Dictionary = super.step_game_input(state, pad_word)
	if not result.ok or not result.diagnostics.applied: return result
	for record: Dictionary in boundaries:
		var bounds: Array = record.raw_bounds_inclusive
		if int(result.state.x_word) >= int(bounds[0]) and int(result.state.x_word) <= int(bounds[2]) and int(result.state.y_word) >= int(bounds[1]) and int(result.state.y_word) <= int(bounds[3]):
			result.state = state.duplicate(true)
			result.diagnostics.applied = false
			result.diagnostics.reason = "test_boundary"
			result.diagnostics.event_boundary = record.id
			return result
	return result
