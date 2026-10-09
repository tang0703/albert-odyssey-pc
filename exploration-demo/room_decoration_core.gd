extends RefCounted
## Source DE2C -> DE9C -> E00A, after camera; independent of frame rate.
const Common = preload("res://package_loader.gd")
const Movement = preload("res://movement_core.gd")
var programs: Array = []

static func word(raw: PackedByteArray, offset: int) -> int:
	return int(raw[offset]) * 256 + int(raw[offset + 1])

static func longword(raw: PackedByteArray, offset: int) -> int:
	return word(raw, offset) * 65536 + word(raw, offset + 2)

static func state_from_hex(value: String) -> Dictionary:
	var raw: PackedByteArray = value.hex_decode()
	if raw.size() != 60: return {}
	return {"cursor":word(raw,0x1c), "timer":word(raw,0x1e), "duration":word(raw,0x20),
		"image":word(raw,0x22), "pointer":longword(raw,0x30), "status":word(raw,0xa)}

func configure(values: Array) -> Dictionary:
	programs.clear()
	if values.size() != 2: return {"ok":false,"error":"Missing room decoration programs"}
	for index: int in 2:
		var value: Variant = values[index]
		if not value is Dictionary or not Movement._keys_match(value,["slot","sequence_hex","image_pointers","initial_hex"]) or value.slot != index+6:
			return {"ok":false,"error":"Unknown decoration program"}
		var expected := PackedByteArray([1,46,0,0])
		if index == 1:
			expected.clear()
			for n: int in 31: expected.append_array(PackedByteArray([5,16+n%16,0]))
			expected.append(0)
		if not value.sequence_hex is String or value.sequence_hex.hex_decode() != expected or not value.image_pointers is Array or value.image_pointers.size() != 127:
			return {"ok":false,"error":"Decoration source sequence differs"}
		for pointer: Variant in value.image_pointers:
			if not Movement.integer(pointer) or pointer < 0 or pointer > 0xffffffff: return {"ok":false,"error":"Invalid source image table word"}
		for offset: int in range(1,expected.size()-1,3):
			var pointer: int = int(value.image_pointers[expected[offset]])
			if pointer < 0x260e0000 or pointer > 0x260ef228: return {"ok":false,"error":"Invalid used image pointer"}
		var initial: Dictionary = state_from_hex(str(value.initial_hex))
		if initial.is_empty() or initial.status != 0x8180: return {"ok":false,"error":"Invalid decoration initial state"}
		var program: Dictionary = value.duplicate(true)
		program.sequence = expected
		program.initial = initial
		programs.append(program)
	return {"ok":true}

func initial_states() -> Array:
	var states: Array = []
	for program: Dictionary in programs: states.append(program.initial.duplicate(true))
	return states

func step(states: Array) -> Dictionary:
	if programs.size() != 2 or states.size() != 2: return {"ok":false,"error":"Decorations not configured"}
	var output: Array = []
	for index: int in 2:
		if not states[index] is Dictionary or not Movement._keys_match(states[index],["cursor","timer","duration","image","pointer","status"]): return {"ok":false,"error":"Invalid decoration state"}
		var state: Dictionary = states[index]
		for key: String in state:
			if not Movement.integer(state[key]): return {"ok":false,"error":"Noninteger decoration state"}
		var sequence: PackedByteArray = programs[index].sequence
		var cursor: int = int(state.cursor)
		var timer: int = int(state.timer)
		if cursor < 0 or cursor >= sequence.size()-1 or cursor%3 != 0 or timer < 1 or timer > sequence[cursor] or state.duration != sequence[cursor] or state.image != sequence[cursor+1] or state.pointer != programs[index].image_pointers[state.image] or state.status != 0x8180:
			return {"ok":false,"error":"Invalid decoration phase/image binding"}
		if timer >= sequence[cursor]: timer = 0; cursor += 3
		timer += 1
		if sequence[cursor] == 0: cursor = 0
		var result: Dictionary = state.duplicate(true)
		result.cursor = cursor; result.timer = timer; result.duration = int(sequence[cursor]); result.image = int(sequence[cursor+1])
		result.pointer = programs[index].image_pointers[result.image]
		output.append(result)
	return {"ok":true,"states":output}
