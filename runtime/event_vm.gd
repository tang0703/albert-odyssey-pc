class_name PcEventVM
extends RefCounted
## PC intermediate instructions, not Saturn bytecodes. Unknown input fails closed.

signal text_requested(text_id: String)
var instructions: Array = []
var flags: Dictionary = {}
var pc: int = 0
var remaining_ticks: int = 0
var awaiting_text: bool = false
var ended: bool = false
var error: String = ""

func start(program: Array, initial_flags: Dictionary = {}) -> void:
	instructions = program.duplicate(true)
	flags = initial_flags.duplicate(true)
	pc = 0
	remaining_ticks = 0
	awaiting_text = false
	ended = false
	error = ""

func fail(message: String) -> void:
	error = message
	ended = true
	awaiting_text = false

func tick() -> void:
	if ended or awaiting_text:
		return
	if remaining_ticks > 0:
		remaining_ticks -= 1
		return
	if pc < 0 or pc >= instructions.size():
		fail("Event ran outside explicit program boundary")
		return
	if not instructions[pc] is Dictionary:
		fail("Malformed instruction")
		return
	var instruction: Dictionary = instructions[pc]
	pc += 1
	match str(instruction.get("op", "")):
		"show_text":
			if not instruction.get("id", null) is String or str(instruction["id"]).is_empty():
				fail("Missing text id")
				return
			awaiting_text = true
			text_requested.emit(instruction["id"])
		"set_flag":
			if not instruction.get("key", null) is String or not instruction.get("value", null) is bool:
				fail("Invalid flag assignment")
				return
			flags[instruction["key"]] = instruction["value"]
		"branch":
			var key: String = str(instruction.get("key", ""))
			if not flags.has(key):
				fail("Branch reads an undefined flag")
				return
			var target: Variant = instruction.get("yes" if flags[key] else "no", null)
			if not target is int or target < 0 or target >= instructions.size():
				fail("Invalid branch target")
				return
			pc = target
		"wait":
			var ticks: Variant = instruction.get("ticks", null)
			if not ticks is int or ticks < 0:
				fail("Invalid wait duration")
				return
			remaining_ticks = ticks
		"end":
			ended = true
		_:
			fail("Unknown instruction: " + str(instruction.get("op", "<missing>")))

func confirm_text() -> void:
	awaiting_text = false
