extends SceneTree
const Core = preload("res://transition_core.gd")
const Common = preload("res://package_loader.gd")
var checks: int = 0
func _initialize() -> void: call_deferred("run")
func fail(message: String) -> void:
	push_error(message); quit(1)
func run() -> void:
	var base: String = ProjectSettings.globalize_path("res://../generated/transition")
	var data: Dictionary = Common.read_json(base.path_join("core.json"))
	var old_data: Dictionary = Common.read_json("res://../generated/equipment/core.json")
	var room: Dictionary = Common.read_json("res://generated/room/room.json")
	var character: Dictionary = {"profile":Common.read_json("res://generated/character/profile.json"),"animation_bank":FileAccess.get_file_as_bytes("res://generated/character/animation-bank.bin"),"image_table":FileAccess.get_file_as_bytes("res://generated/character/image-table.bin")}
	var flags: PackedByteArray = FileAccess.get_file_as_bytes("res://generated/scene/flags.bin")
	var routes: Array = []
	for route: String in ["equip-stairs","remove-stairs","reequip-stairs"]:
		var fixture: Dictionary = Common.read_json(base.path_join("reference/"+route+".json"))
		var core := Core.new()
		var configured: Dictionary = core.configure_transition(data,old_data,room.movement_profile,flags,character,room)
		if not configured.ok: fail(str(configured)); return
		for row: Dictionary in fixture.prefix.updates:
			for action: String in row.equipment:
				if not core.equipment(action).ok: fail("Equipment request failed"); return
			var input: Dictionary = row.input
			var result: Dictionary = core.step(int(input.pad),{"resource_loaded":input.resource_loaded,"resource_playing":input.resource_playing,"text_active":input.text_active},int(input.pressed))
			if not result.ok or result.state != row.expected: fail("Original room prefix diverged: "+route+" "+str(input.update)+" "+str(result)); return
			checks += result.state.size()
		var result: Dictionary = core.step(int(fixture.prefix.terminal.pad),{"resource_loaded":0,"resource_playing":0,"text_active":false})
		if not result.ok: fail(str(result)); return
		var preserved: Array = [core.weapon,core.item_count,core.attack,core.story]
		var index: int = 0
		for row: Dictionary in fixture.post_commit:
			if row.initialize:
				result = core.step(0,{})
				if not result.ok or core.stage != "loading": fail("Fade completion did not request loading"); return
				var before: Dictionary = core.transition_snapshot()
				if core.scene_resources_ready(core.generation-1,"map001_scene7_resources").accepted or core.scene_resources_ready(core.generation,"unknown").accepted or core.transition_snapshot() != before:
					fail("Stale or unknown load completion accepted"); return
				if not core.scene_resources_ready(core.generation,"map001_scene7_resources").accepted: fail("Valid load completion rejected"); return
				before = core.transition_snapshot()
				if core.scene_resources_ready(core.generation,"map001_scene7_resources").accepted or core.transition_snapshot() != before: fail("Duplicate load mutated scene"); return
				checks += 5
			if index > 0:
				result = core.step(int(row.input.pad),{})
				if not result.ok or not result.applied: fail("Transfer update failed: "+str(index)+" "+str(result)); return
			var actual: Dictionary = core.transition_snapshot()
			if actual != row.expected:
				for key: String in actual:
					if actual[key] != row.expected[key]: print(route+" "+str(index)+" "+key+" actual="+str(actual[key])+" expected="+str(row.expected[key]))
				fail("Transfer source parity failed"); return
			if preserved != [core.weapon,core.item_count,core.attack,core.story]: fail("Persistent state changed on transfer"); return
			if core.stage != "landing" and core.equipment("remove").ok: fail("Transfer allowed equipment"); return
			checks += actual.size()+5; index += 1
		var old_generation: int = core.generation
		core.reset()
		if core.scene_resources_ready(old_generation,"map001_scene7_resources").accepted or core.stage != "original_room" or core.scene_id != 8 or core.snapshot() != old_data.initial_state or not core.landing_objects.is_empty() or not core.arrival_actor.is_empty(): fail("Reset retained transition state"); return
		var changed: Dictionary = data.duplicate(true)
		changed.initialization[0].action = "execute_raw"
		if core.configure_transition(changed,old_data,room.movement_profile,flags,character,room).ok: fail("Modified initializer accepted"); return
		checks += 8
		routes.append({"route":route,"prefix_updates":fixture.prefix.updates.size(),"transfer_updates":index})
	var report: Dictionary = {"passed":true,"checks":checks,"routes":routes,"performance_tested":false,"scope":"Independent GDScript continuous original-room and landing states plus generation/duplicate/reset guards. No UI or package acceptance."}
	var file := FileAccess.open(base.path_join("../../reports/transition/t2-godot.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify(report,"\t")); file.close(); print(JSON.stringify(report)); quit(0)
