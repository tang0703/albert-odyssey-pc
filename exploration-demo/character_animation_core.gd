class_name CharacterAnimationCore
extends RefCounted
## Raw source animation state only. Movement is supplied by the existing core.
## No nodes, clocks, file loading, texture decoding or character-name inference.

const Movement = preload("res://movement_core.gd")
const SCHEMA: String = "ao_pc_character_animation_model_v1"
const ANIMATION_ROOT: int = 0x20220010
const IMAGE_TABLE_ROOT: int = 0x20220158
const BANK_SHA: String = "ed78a1ab97ce9f799c3ae52c1b87920027b6ae15f893d26ec65511c534858d46"
const IMAGE_TABLE_SHA: String = "308a402aaa5b8c848569c7c29010a2790f7230be16c7f64f3bc21c36eafd12f0"
const FIELDS: Dictionary = {
	"status_word":[6,2], "flags_word":[8,2], "heading":[38,2], "animation_index":[54,2],
	"render_flags_word":[20,2], "animation_cursor":[44,2], "animation_timer":[48,2],
	"animation_duration":[50,2], "image_index":[52,2], "image_table_root":[88,4],
	"image_pointer":[92,4], "animation_root":[96,4],
}
const PROFILE_KEYS: Array[String] = ["schema","actor_address","animation_root","image_table_root",
	"initial_state","animation_bank_sha256","image_table_sha256","active_records_sha256","source_code_sha256",
	"comparison_fields","code_ranges","logical_tick_seconds","supported_headings","hd_interpolation"]
const CODE_RANGES: Array = [
	[0x1c0b6,0x1c10a,"45b95eb4242c9b38f7c1ffedf1cf333c73cb270c890c42b9b932117714dea97a"],
	[0x1c20c,0x1c2aa,"57d18d5609a29bdb8a011485c20b96cf3f9f4662e3383ae3543e0351c4fe3c1d"],
	[0x1c346,0x1c360,"1ae720ecb293f7e88cad227bafc3ec4fb6725715ba6da49d2c9c494524040374"],
	[0x1ae20,0x1af74,"f0f579cc93d30f64091196c0f966a95d195ad4e6e819c741ee85e1095a54b0bd"],
	[0x268ac,0x268bc,"a9cc43c295192add1af80a40c98eee57f915f01cc68eef459c14e18dae61d94b"],
]

var _profile: Dictionary = {}
var _bank: PackedByteArray = PackedByteArray()
var _images: PackedByteArray = PackedByteArray()

static func project_state(actor: Dictionary) -> Dictionary:
	var projected: Dictionary = {}
	for key: String in FIELDS:
		if actor.has(key): projected[key] = int(actor[key]) if Movement.integer(actor[key]) else actor[key]
	return projected

static func project_movement(actor: Dictionary) -> Dictionary:
	var projected: Dictionary = {}
	for key: String in Movement.FIELDS:
		if actor.has(key): projected[key] = int(actor[key]) if Movement.integer(actor[key]) else actor[key]
	return projected

static func _hash(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	if hash.start(HashingContext.HASH_SHA256) != OK or hash.update(bytes) != OK: return ""
	return hash.finish().hex_encode()

static func _u32(bytes: PackedByteArray, offset: int) -> int:
	return (int(bytes[offset]) << 24) | (int(bytes[offset + 1]) << 16) | (int(bytes[offset + 2]) << 8) | int(bytes[offset + 3])

func configure(profile: Dictionary, animation_bank: PackedByteArray, image_table: PackedByteArray) -> Dictionary:
	_profile.clear()
	_bank = PackedByteArray()
	_images = PackedByteArray()
	var error: String = _validate_profile(profile, animation_bank, image_table)
	if not error.is_empty(): return {"ok":false,"error":error}
	_bank = animation_bank.duplicate()
	_images = image_table.duplicate()
	var state_error: String = validate_state(project_state(profile.initial_state))
	if not state_error.is_empty():
		_bank.clear()
		_images.clear()
		return {"ok":false,"error":state_error}
	_profile = profile.duplicate(true)
	return {"ok":true,"error":""}

static func _validate_profile(profile: Dictionary, bank: PackedByteArray, image_table: PackedByteArray) -> String:
	if not Movement._keys_match(profile, PROFILE_KEYS) or profile.schema != SCHEMA:
		return "Unknown or incomplete character animation profile"
	if profile.animation_bank_sha256 != BANK_SHA or profile.image_table_sha256 != IMAGE_TABLE_SHA or profile.active_records_sha256 != Movement.ANIMATION_ROOT_SHA256 or profile.source_code_sha256 != Movement.SOURCE_HASHES["TWN.BIN"]:
		return "Unknown animation source identity"
	if bank.size() != 0x148 or _hash(bank) != BANK_SHA or image_table.size() != 160 or _hash(image_table) != IMAGE_TABLE_SHA:
		return "Changed animation records or image-pointer table"
	for key: String in ["actor_address","animation_root","image_table_root"]:
		if not Movement.integer(profile[key]): return "Invalid source pointer"
	if int(profile.actor_address) != 0x060c8758 or int(profile.animation_root) != ANIMATION_ROOT or int(profile.image_table_root) != IMAGE_TABLE_ROOT:
		return "Unsupported controlled actor or roots"
	if not profile.initial_state is Dictionary or profile.initial_state.size() != 25:
		return "Missing complete initial character state"
	var movement_error: String = Movement.validate_state(project_movement(profile.initial_state))
	if not movement_error.is_empty(): return movement_error
	if not profile.supported_headings is Array or profile.supported_headings.size() != 4:
		return "Only the verified cardinal headings are supported"
	for index: int in 4:
		if not Movement.integer(profile.supported_headings[index]) or int(profile.supported_headings[index]) != index * 2:
			return "Only the verified cardinal headings are supported"
	if profile.hd_interpolation != "Not part of original animation state model":
		return "HD presentation must not replace original timing"
	if not profile.logical_tick_seconds is Dictionary or not Movement._keys_match(profile.logical_tick_seconds,["numerator","denominator"]):
		return "Missing logical period"
	if not Movement.integer(profile.logical_tick_seconds.numerator) or not Movement.integer(profile.logical_tick_seconds.denominator) or int(profile.logical_tick_seconds.numerator) != Movement.TICK_NUMERATOR or int(profile.logical_tick_seconds.denominator) != Movement.TICK_DENOMINATOR:
		return "Unknown logical period"
	if not profile.comparison_fields is Dictionary or not Movement._keys_match(profile.comparison_fields,FIELDS.keys()):
		return "Unknown animation comparison fields"
	for key: String in FIELDS:
		var field: Variant = profile.comparison_fields[key]
		if not field is Dictionary or not Movement._keys_match(field,["offset","bytes","mask"]): return "Invalid animation field definition"
		for member: String in ["offset","bytes","mask"]:
			if not Movement.integer(field[member]): return "Animation field definition is not integral"
		if int(field.offset) != FIELDS[key][0] or int(field.bytes) != FIELDS[key][1] or int(field.mask) != (1 << (int(FIELDS[key][1]) * 8)) - 1:
			return "Changed animation field definition"
	if not profile.code_ranges is Array or profile.code_ranges.size() != CODE_RANGES.size(): return "Missing original animation code pins"
	for index: int in CODE_RANGES.size():
		var record: Variant = profile.code_ranges[index]
		if not record is Dictionary or not Movement._keys_match(record,["offset","end_exclusive","sha256"]): return "Invalid original code range"
		if not Movement.integer(record.offset) or not Movement.integer(record.end_exclusive) or int(record.offset) != CODE_RANGES[index][0] or int(record.end_exclusive) != CODE_RANGES[index][1] or record.sha256 != CODE_RANGES[index][2]:
			return "Changed original animation code pin"
	return ""

func _record(animation: int, cursor: int) -> Array[int]:
	if animation < 0 or animation >= 16 or not ([0,3] if animation < 8 else [0,3,6,9,12]).has(cursor): return []
	var offset: int = _u32(_bank, animation * 4) - ANIMATION_ROOT + cursor
	if offset < 0 or offset >= _bank.size(): return []
	if _bank[offset] == 0: return [0,0,0]
	if offset + 3 > _bank.size() or not [0,4].has(int(_bank[offset + 2])): return []
	return [int(_bank[offset]),int(_bank[offset + 1]),int(_bank[offset + 2])]

func validate_state(state: Dictionary) -> String:
	if not Movement._keys_match(state,FIELDS.keys()): return "Animation state fields differ from contract"
	for key: String in FIELDS:
		if not Movement.integer(state[key]) or state[key] < 0 or state[key] > (1 << (int(FIELDS[key][1]) * 8)) - 1:
			return "Invalid raw animation field: " + key
	if int(state.animation_root) != ANIMATION_ROOT or int(state.image_table_root) != IMAGE_TABLE_ROOT or int(state.flags_word) != 9 or (int(state.status_word) & ~(2 | 0x200)) != 0x8180:
		return "Unsupported actor animation configuration"
	if not [0,2,4,6].has(int(state.heading)) or not [0,3,6,9].has(int(state.animation_cursor)) or int(state.animation_timer) > 9 or not [1,10].has(int(state.animation_duration)) or int(state.image_index) > 20:
		return "Unsupported cardinal-animation state"
	var selected: int = int(state.heading) + (8 if int(state.status_word) & 2 else 0)
	if int(state.animation_index) != selected: return "Animation selection differs from movement"
	if _bank.is_empty() or _images.is_empty(): return "Animation sources are not configured"
	var record: Array[int] = _record(selected,int(state.animation_cursor))
	if record.is_empty() or record[0] != int(state.animation_duration) or record[1] != int(state.image_index) or bool(record[2] & 4) != bool(int(state.render_flags_word) & 1) or _u32(_images,int(state.image_index) * 4) != int(state.image_pointer):
		return "Animation cache differs from source record"
	return ""

func initial_state() -> Dictionary:
	return {} if _profile.is_empty() else project_state(_profile.initial_state).duplicate(true)

func metadata() -> Dictionary:
	return _profile.duplicate(true)

static func _failure(state: Dictionary, error: String) -> Dictionary:
	return {"ok":false,"state":state.duplicate(true),"error":error,"diagnostics":{"applied":false,"reason":"invalid_input"}}

func step_after_movement(state: Dictionary, movement_result: Dictionary) -> Dictionary:
	if _profile.is_empty(): return _failure(state,"Animation profile is not configured")
	var error: String = validate_state(state)
	if not error.is_empty(): return _failure(state,error)
	if not movement_result.get("ok",false) is bool or not movement_result.get("ok",false) or not movement_result.get("state") is Dictionary or not movement_result.get("diagnostics") is Dictionary or not movement_result.diagnostics.get("applied") is bool:
		return _failure(state,"A completed movement-core result is required")
	var context: Dictionary = movement_result.state
	error = Movement.validate_state(context)
	if not error.is_empty(): return _failure(state,error)
	if not movement_result.diagnostics.applied:
		if movement_result.diagnostics.get("reason") != "test_boundary": return _failure(state,"Unsupported movement rejection")
		return {"ok":true,"state":state.duplicate(true),"error":"","diagnostics":{"applied":false,"reason":"test_boundary"}}
	var next: Dictionary = state.duplicate(true)
	for key: String in FIELDS: next[key] = int(next[key])
	for key: String in ["status_word","flags_word","heading","animation_index"]: next[key] = int(context[key])
	if not [0,2,4,6].has(int(next.heading)) or int(next.animation_index) != int(next.heading) + (8 if int(next.status_word) & 2 else 0):
		return _failure(state,"Movement selected an unsupported animation")
	if not (int(next.status_word) & 2): next.animation_cursor = 0
	next.animation_timer = (int(next.animation_timer) + 1) & 65535
	var advanced: bool = int(next.animation_timer) >= int(next.animation_duration)
	if advanced:
		next.animation_timer = 0
		next.animation_cursor = int(next.animation_cursor) + 3
		next.status_word = int(next.status_word) | 0x80
	var record: Array[int] = _record(int(next.animation_index),int(next.animation_cursor))
	if record.is_empty(): return _failure(state,"Animation cursor is outside pinned records")
	var wrapped: bool = record[0] == 0
	if wrapped:
		next.animation_cursor = 0
		next.status_word = int(next.status_word) | 0x100
		record = _record(int(next.animation_index),0)
	next.animation_duration = record[0]
	next.image_index = record[1]
	next.render_flags_word = (int(next.render_flags_word) & ~1) | (1 if record[2] & 4 else 0)
	next.image_pointer = _u32(_images,record[1] * 4)
	error = validate_state(next)
	if not error.is_empty(): return _failure(state,error)
	return {"ok":true,"state":next,"error":"","diagnostics":{"applied":true,"advanced":advanced,"wrapped":wrapped,
		"mirror_x":bool(int(next.render_flags_word) & 1),"image_index":next.image_index,"image_pointer":next.image_pointer}}
