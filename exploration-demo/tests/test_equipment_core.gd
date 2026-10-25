extends SceneTree
const Core = preload("res://equipment_core.gd")
const Common = preload("res://package_loader.gd")
const Loader = preload("res://equipment_loader.gd")
var checks: int = 0
func _initialize() -> void: call_deferred("run")
func fail(message: String) -> void:
	push_error(message); quit(1)
func run() -> void:
	var base: String = ProjectSettings.globalize_path("res://../generated/equipment")
	var data: Dictionary = Common.read_json(base.path_join("core.json"))
	var room: Dictionary = Common.read_json("res://generated/room/room.json")
	var character: Dictionary = {"profile":Common.read_json("res://generated/character/profile.json"),"animation_bank":FileAccess.get_file_as_bytes("res://generated/character/animation-bank.bin"),"image_table":FileAccess.get_file_as_bytes("res://generated/character/image-table.bin")}
	var flags: PackedByteArray = FileAccess.get_file_as_bytes("res://generated/scene/flags.bin")
	var loaded: Dictionary = Loader.load_bundle(Loader.default_directory(),room.movement_profile,flags,character,room)
	if not loaded.ok or not loaded.preloaded or loaded.references.size() != 7: fail("Equipment bundle/preload failed: "+str(loaded)); return
	var routes: Array = []
	for route: String in ["equip-stairs","remove-stairs","reequip-stairs","unowned","cancel-owned","hold-equip","cancel-selection"]:
		var fixture: Dictionary = Common.read_json(base.path_join("reference/"+route+".json"))
		var core := Core.new()
		var configured: Dictionary = core.configure(data,room.movement_profile,flags,character,room)
		if not configured.ok: fail(str(configured)); return
		for row: Dictionary in fixture.updates:
			for action: String in row.equipment:
				if not core.equipment(action).ok: fail("Equipment operation rejected"); return
			var input: Dictionary = row.input
			var result: Dictionary = core.step(int(input.pad),{"resource_loaded":input.resource_loaded,"resource_playing":input.resource_playing,"text_active":input.text_active},int(input.pressed))
			if not result.ok or not result.get("applied",false): fail(route+" "+str(input.update)+": "+str(result)); return
			for key: String in result.state:
				checks += 1
				if result.state[key] != row.expected[key]: fail(route+" "+str(input.update)+" "+key+": "+str(result.state[key])+" != "+str(row.expected[key])); return
		if fixture.terminal != null:
			var result: Dictionary = core.step(int(fixture.terminal.pad),{"resource_loaded":0,"resource_playing":0,"text_active":false})
			if not result.ok or result.state != fixture.terminal.expected: fail("Scene submission prefix differs: "+route); return
			var frozen: Dictionary = core.snapshot()
			if core.step(0,{"resource_loaded":0,"resource_playing":0,"text_active":false}).applied or core.snapshot() != frozen or core.equipment("remove").ok: fail("Boundary continued"); return
		core.reset()
		if core.snapshot() != data.initial_state: fail("Incomplete reset"); return
		var before: Dictionary = core.snapshot()
		if core.equipment("equip").changed or core.equipment("remove").changed or core.snapshot() != before or core.equipment("unknown").ok: fail("Unowned/unknown operation changed state"); return
		if core.step(0,{}).ok or core.snapshot() != before: fail("Invalid input changed state"); return
		core.story = "07"
		if core.step(0,{"resource_loaded":0,"resource_playing":0,"text_active":false}).ok: fail("Inconsistent equipment state accepted"); return
		var altered: Dictionary = data.duplicate(true)
		altered.contract.programs.equipped_end[0].action = "execute_raw"
		if core.configure(altered,room.movement_profile,flags,character,room).ok: fail("Unknown instruction accepted"); return
		routes.append({"route":route,"updates":fixture.updates.size()})
	var report: Dictionary = {"passed":true,"checks":checks,"routes":routes,"scope":"Independent GDScript core; semantic equipment operations plus continuous source updates and pre-commit boundary."}
	var file := FileAccess.open(base.path_join("../../reports/equipment/q2-godot.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify(report,"\t")); file.close(); print(JSON.stringify(report)); quit(0)
