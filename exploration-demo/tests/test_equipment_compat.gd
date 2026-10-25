extends SceneTree
const Core = preload("res://equipment_core.gd")
const Common = preload("res://package_loader.gd")
const Previous = preload("res://interaction_loader.gd")
var checks: int=0
var updates: int=0
var failures: Array[String]=[]
func _initialize() -> void: call_deferred("run")
func run() -> void:
	var data: Dictionary=Common.read_json("res://generated/equipment/core.json")
	var room: Dictionary=Common.read_json("res://generated/room/room.json")
	var character: Dictionary={"profile":Common.read_json("res://generated/character/profile.json"),"animation_bank":FileAccess.get_file_as_bytes("res://generated/character/animation-bank.bin"),"image_table":FileAccess.get_file_as_bytes("res://generated/character/image-table.bin")}
	var flags: PackedByteArray=FileAccess.get_file_as_bytes("res://generated/scene/flags.bin")
	for route: String in Previous.ROUTES:
		var fixture: Dictionary=Common.read_json("res://generated/interaction/reference-"+route+".json")
		var core:=Core.new()
		var configured: Dictionary=core.configure(data,room.movement_profile,flags,character,room)
		if not configured.ok: failures.append(str(configured)); break
		for row: Dictionary in fixture.updates:
			var input: Dictionary=row.input
			var result: Dictionary=core.step(input.pad,{"resource_loaded":input.resource_loaded,"resource_playing":input.resource_playing,"text_active":input.text_active},input.pressed)
			if not result.ok or not result.applied: failures.append("Old route rejected: "+route); break
			updates+=1
			for field: String in row.expected:
				if field in ["event_index","frame"]: continue # capture metadata, never runtime state
				checks+=1
				if result.state[field]!=row.expected[field]: failures.append(route+" "+str(updates)+" "+field)
			if core.weapon!=255 or core.attack!=10 or core.transition_pending: failures.append("Old route changed equipment/transition")
			if not failures.is_empty(): break
		if not failures.is_empty(): break
	var report: Dictionary={"schema":"ao_pc_equipment_previous_routes_v1","passed":failures.is_empty(),"checks":checks,"updates":updates,"failures":failures}
	var file:=FileAccess.open("res://../reports/equipment/q4-compat.json",FileAccess.WRITE); file.store_string(JSON.stringify(report,"\t")); file.close()
	print(JSON.stringify(report)); quit(0 if failures.is_empty() else 1)
