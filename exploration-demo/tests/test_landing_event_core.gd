extends SceneTree
const Core = preload("res://landing_event_core.gd")
const Common = preload("res://package_loader.gd")
var checks: int = 0
func _initialize() -> void: call_deferred("run")
func fail(message: String) -> void:
	push_error(message); quit(1)
func run() -> void:
	var base: String = ProjectSettings.globalize_path("res://../generated/landing-event")
	var data: Dictionary = Common.read_json(base.path_join("core.json"))
	var transfer: Dictionary = Common.read_json("res://../generated/transition/core.json")
	var old_data: Dictionary = Common.read_json("res://../generated/equipment/core.json")
	var room: Dictionary = Common.read_json("res://generated/room/room.json")
	var character: Dictionary = {"profile":Common.read_json("res://generated/character/profile.json"),"animation_bank":FileAccess.get_file_as_bytes("res://generated/character/animation-bank.bin"),"image_table":FileAccess.get_file_as_bytes("res://generated/character/image-table.bin")}
	var flags: PackedByteArray = FileAccess.get_file_as_bytes("res://generated/scene/flags.bin")
	var routes: Array = []
	for route: String in ["equip","remove","reequip","edge-held"]:
		var fixture: Dictionary = Common.read_json(base.path_join("reference/"+route+".json"))
		var core := Core.new()
		var configured: Dictionary = core.configure_landing_event(data,transfer,old_data,room.movement_profile,flags,character,room)
		if not configured.ok: fail(str(configured)); return
		for row: Dictionary in fixture.prefix.updates:
			for action: String in row.equipment:
				if not core.equipment(action).ok: fail("Equipment request failed"); return
			var input: Dictionary = row.input
			var result: Dictionary = core.step(int(input.pad),{"resource_loaded":input.resource_loaded,"resource_playing":input.resource_playing,"text_active":input.text_active},int(input.pressed))
			var old_state: Dictionary = result.get("state",{}).duplicate(true)
			old_state.erase("landing_event")
			if not core.event_slots.is_empty() or core.event_runs != 0: fail("New event leaked into original room"); return
			if not result.ok or old_state != row.expected: fail("Original room prefix diverged: "+route+" "+str(input.update)+" "+str(result)); return
			checks += result.state.size()
		var result: Dictionary = core.step(int(fixture.prefix.terminal.pad),{"resource_loaded":0,"resource_playing":0,"text_active":false})
		if not result.ok: fail(str(result)); return
		var preserved: Array = [core.weapon,core.item_count,core.attack]
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
				result = core.step(int(row.input.pad),{"text_active":row.input.text_active})
				if not result.ok or not result.applied: fail("Transfer update failed: "+str(index)+" "+str(result)); return
			var actual: Dictionary = core.transition_snapshot()
			if actual != row.expected:
				for key: String in actual:
					if actual[key] != row.expected[key]: print(route+" "+str(index)+" "+key+" actual="+str(actual[key])+" expected="+str(row.expected[key]))
				fail("Transfer source parity failed"); return
			if preserved != [core.weapon,core.item_count,core.attack]: fail("Persistent state changed on transfer"); return
			if (core.stage != "landing" or core.disabled != 0) and core.equipment("remove").ok: fail("Transfer allowed equipment"); return
			checks += actual.size()+5; index += 1
		if core.event_runs != 1 or not core.event_completed or core.ambient_loops < 1: fail("Missing event/ambient endpoint"); return
		var endpoint: Dictionary = core.snapshot()
		for invalid_input: Dictionary in [{"pad":3,"signals":{"text_active":false}},{"pad":0,"signals":{}},{"pad":0,"signals":{"text_active":"false"}}]:
			if core.step(int(invalid_input.pad),invalid_input.signals).ok or core.snapshot() != endpoint: fail("Invalid input mutated event endpoint"); return
			checks += 2
		var expected_item: Array = [core.weapon,core.item_count,core.attack,core.story]
		var first_action: String = "remove" if core.weapon == 27 else "equip"
		if not core.equipment(first_action).changed or core.equipment(first_action).changed: fail("Post-event equipment idempotence failed"); return
		if not core.equipment("equip" if first_action == "remove" else "remove").changed or [core.weapon,core.item_count,core.attack,core.story] != expected_item: fail("Equipment did not restore inventory and story"); return
		checks += 3
		var saved_count: int = core.item_count
		core.item_count = 99
		var invalid: Dictionary = core.snapshot()
		if core.step(0,{"text_active":false}).ok or core.equipment("equip").ok or core.snapshot() != invalid: fail("Illegal persistent state accepted or mutated"); return
		core.item_count = saved_count; checks += 3
		var old_generation: int = core.generation
		core.reset()
		var reset_state: Dictionary = core.snapshot(); reset_state.erase("landing_event")
		if core.scene_resources_ready(old_generation,"map001_scene7_resources").accepted or core.stage != "original_room" or core.scene_id != 8 or reset_state != old_data.initial_state or not core.event_slots.is_empty() or core.event_completed or core.event_runs != 0 or not core.landing_objects.is_empty() or not core.arrival_actor.is_empty(): fail("Reset retained transition state"); return
		var changed: Dictionary = data.duplicate(true)
		changed.programs.main[0].action = "execute_raw"
		if core.configure_landing_event(changed,transfer,old_data,room.movement_profile,flags,character,room).ok: fail("Modified initializer accepted"); return
		checks += 8
		routes.append({"route":route,"prefix_updates":fixture.prefix.updates.size(),"transfer_updates":index})
	var report: Dictionary = {"passed":true,"checks":checks,"routes":routes,"performance_tested":false,"scope":"Independent GDScript continuous original-room, transfer and landing-event states; command slots, equipment, camera and ambient cycle. No UI, pixels, package or performance acceptance."}
	var file := FileAccess.open(base.path_join("../../reports/landing-event/l2-godot.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify(report,"\t")); file.close(); print(JSON.stringify(report)); quit(0)
