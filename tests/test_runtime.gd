extends SceneTree

const VM = preload("res://runtime/event_vm.gd")
const STORE = preload("res://runtime/save_store.gd")
var checks: int = 0
var failures: Array[String] = []

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)

func _initialize() -> void:
	var vm := VM.new()
	vm.start([{"op": "set_flag", "key": "seen", "value": true},
		{"op": "branch", "key": "seen", "yes": 3, "no": 2},
		{"op": "unknown_saturn_opcode"}, {"op": "show_text", "id": "verified_page"},
		{"op": "wait", "ticks": 3}, {"op": "end"}])
	vm.tick()
	vm.tick()
	vm.tick()
	check(vm.awaiting_text and vm.pc == 4, "branch reaches expected dialogue")
	for i: int in range(20):
		vm.tick()
	check(vm.pc == 4, "dialogue blocks advancement until confirmed")
	vm.confirm_text()
	vm.tick()
	check(vm.remaining_ticks == 3, "logical wait initialized")
	for i: int in range(3):
		vm.tick()
	check(not vm.ended and vm.remaining_ticks == 0, "three fixed ticks elapsed")
	vm.tick()
	check(vm.ended and vm.error.is_empty(), "explicit end")
	vm.start([{"op": "0x24"}])
	vm.tick()
	check(vm.ended and not vm.error.is_empty(), "unknown instructions fail closed")
	vm.start([{"op": "branch", "key": "missing", "yes": 0, "no": 0}])
	vm.tick()
	check(not vm.error.is_empty(), "undefined branch is not silently false")
	vm.start([{"op": "wait", "ticks": -1}])
	vm.tick()
	check(not vm.error.is_empty(), "negative wait rejected")
	var path: String = ProjectSettings.globalize_path("res://reports/save-tests/state.json")
	var state: Dictionary = {"schema": "ao_pc_save_v1", "scene": "unit_test_fixture",
		"player": {"x": 12, "y": 24}, "party": [{"id": "test", "hp": 20}],
		"flags": {"seen": true}, "safe_boundary": true}
	check(STORE.save_file(path, state) == OK, "save writes at safe boundary")
	var loaded: Dictionary = STORE.load_file(path)
	check(loaded.get("flags", {}).get("seen", false) == true
		and float(loaded.get("player", {}).get("x", -1)) == 12.0
		and float(loaded.get("player", {}).get("y", -1)) == 24.0
		and loaded.get("party", [])[0]["hp"] == 20, "save state round trip")
	state["safe_boundary"] = false
	check(STORE.save_file(path, state) == ERR_INVALID_DATA, "unsafe save refused")
	check(not STORE.load_file(path).is_empty(), "refusal preserves previous save")
	state["safe_boundary"] = true
	state["schema"] = "future_version"
	check(STORE.save_file(path, state) == ERR_INVALID_DATA, "future schema refused")
	var file: FileAccess = FileAccess.open(path + ".corrupt", FileAccess.WRITE)
	file.store_string("{truncated")
	file.close()
	check(STORE.load_file(path + ".corrupt").is_empty(), "corrupt save rejected")
	var report: Dictionary = {"checks": checks, "failures": failures, "scope": "synthetic_PC_contracts_not_original_gameplay"}
	var output: FileAccess = FileAccess.open("res://reports/runtime-tests.json", FileAccess.WRITE)
	output.store_string(JSON.stringify(report, "\t"))
	output.close()
	print(JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
