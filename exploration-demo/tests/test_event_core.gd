extends SceneTree
const Core = preload("res://event_core.gd")
const Common = preload("res://package_loader.gd")
const Loader = preload("res://event_loader.gd")
var checks: int = 0

func _initialize() -> void:
	call_deferred("run")

func fail(message: String) -> void:
	push_error(message)
	quit(1)

func run() -> void:
	var base: String = ProjectSettings.globalize_path("res://../generated/event")
	var data: Dictionary = Common.read_json(base.path_join("core.json"))
	var room: Dictionary = Common.read_json("res://generated/room/room.json")
	var character: Dictionary = {"profile":Common.read_json("res://generated/character/profile.json"),
		"animation_bank":FileAccess.get_file_as_bytes("res://generated/character/animation-bank.bin"),
		"image_table":FileAccess.get_file_as_bytes("res://generated/character/image-table.bin")}
	var flags: PackedByteArray = FileAccess.get_file_as_bytes("res://generated/scene/flags.bin")
	var routes: Array = []
	var loaded: Dictionary = Loader.load_bundle(Loader.default_directory(),room.movement_profile,flags,character,room)
	if not loaded.ok or not loaded.preloaded: fail("Event loader failed: "+str(loaded)); return
	var invalid: Dictionary = data.duplicate(true)
	invalid.contract.programs.entry[0].action = "execute_raw_saturn_bytes"
	var rejected := Core.new()
	if rejected.configure(invalid,room.movement_profile,flags,character,room).ok: fail("Unknown instruction accepted"); return
	invalid = data.duplicate(true)
	invalid.contract.programs.retreat[0].args.index = 5
	if rejected.configure(invalid,room.movement_profile,flags,character,room).ok: fail("Changed source operand accepted"); return
	for route: String in ["center","top","bottom","reenter","wait","hold"]:
		var fixture: Dictionary = Common.read_json(base.path_join("reference/"+route+".json"))
		var core := Core.new()
		var configured: Dictionary = core.configure(data,room.movement_profile,flags,character,room)
		if not configured.ok: fail(str(configured.error)); return
		for row: Dictionary in fixture.updates:
			var inputs: Dictionary = row.input
			var result: Dictionary = core.step(int(inputs.pad),{"resource_loaded":inputs.resource_loaded,"resource_playing":inputs.resource_playing,"text_active":inputs.text_active})
			if not result.ok or not result.get("applied",false): fail(route+" update "+str(inputs.update)+": "+str(result)); return
			for key: String in result.state:
				checks += 1
				if result.state[key] != row.expected[key]:
					fail(route+" update "+str(inputs.update)+" field "+key+" actual "+str(result.state[key])+" expected "+str(row.expected[key])); return
		core.reset()
		for key: String in core.snapshot():
			if core.snapshot()[key] != data.initial_state[key]: fail("Reset differs: "+key); return
		var before: Dictionary = core.snapshot()
		if core.step(0,{}).ok or core.snapshot() != before: fail("Invalid device signals changed state"); return
		routes.append({"route":route,"updates":fixture.updates.size()})
	var report: Dictionary = {"schema":"ao_pc_event_godot_core_v1","passed":true,"checks":checks,"routes":routes,
		"scope":"Independent GDScript named-instruction core, original device acknowledgements; no later state injection."}
	var output := FileAccess.open(base.path_join("../../reports/event/d2-godot.json"),FileAccess.WRITE)
	output.store_string(JSON.stringify(report,"\t")); output.close()
	print(JSON.stringify(report))
	quit(0)
