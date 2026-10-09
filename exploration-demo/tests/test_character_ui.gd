extends SceneTree
## Actual entry + source trajectories. Never inject a later actor to advance it.
const AnimationCore = preload("res://character_animation_core.gd")
const Movement = preload("res://movement_core.gd")
const Loader = preload("res://package_loader.gd")

var checks: int = 0
var updates: int = 0
var fixture_path: String = ""

func _initialize() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--fixtures="): fixture_path = arg.trim_prefix("--fixtures=")
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		push_error(message)
		quit(1)
		assert(condition, message)

func capture_state(ui: Control) -> Dictionary:
	return {"movement":ui.state.duplicate(true), "animation":ui.animation_state.duplicate(true),
		"displayed":ui.displayed_actor.duplicate(true), "queue":ui.presentation_queue.duplicate(true),
		"updates":ui.update_count, "visual_updates":ui.presentation_updates, "trace_cursor":ui.trace_cursor,
		"expected":ui.expected.duplicate(true)}

func run() -> void:
	if not FileAccess.file_exists("res://character-pin.json"):
		print("CHARACTER_UI_SOURCE_STATUS=not_run (local appearance package unavailable)")
		quit(0)
		return
	var ui: Control = load("res://character_main.tscn").instantiate()
	ui.ui_test_mode = true
	root.add_child(ui)
	await process_frame
	await process_frame
	check(ui.startup_error.is_empty(), "approved character entry loads: " + ui.startup_error)
	check(ui.state.size() == 17 and ui.verified_indices.size() == 108, "unchanged movement fields and domain")
	check(ui.character_bundle.textures.size() == 20, "all original poses preloaded")
	check(ui.display_delay == 3, "source-proven actor-to-video queue")
	var original_traces: Array = ui.bundle.traces.duplicate(true)
	var resources: Dictionary = {}
	for key: String in ui.character_bundle.textures:
		resources[key] = ui.character_bundle.textures[key].get_instance_id()
	if not fixture_path.is_empty():
		var fixtures: Variant = Loader.read_json(fixture_path)
		check(fixtures is Dictionary and fixtures.get("passed") == true and fixtures.get("traces") is Array, "passed original capture fixtures required")
		for mode: String in ["original", "marker"]:
			ui.change_appearance(mode)
			for trace: Dictionary in fixtures.traces:
				var route_updates: Array = []
				for row: Dictionary in trace.updates:
					route_updates.append({"frame":row.frame, "game_pad_word":row.game_pad_word, "expected":AnimationCore.project_movement(row.expected)})
				ui.bundle.traces = [{"id":"source_animation", "label":"source_animation", "initial_state":AnimationCore.project_movement(trace.initial_state), "updates":route_updates}]
				ui.route_index = 0
				ui.change_mode(1)
				ui.paused = false
				for index: int in trace.updates.size():
					ui.advance_time(ui.tick_seconds)
					check(ui.current_differences.is_empty(), "movement keeps source parity in " + mode)
					check(ui.animation_state == AnimationCore.project_state(trace.updates[index].expected), "animation follows actual source update")
					var source_display: Dictionary = trace.initial_state if index < 3 else trace.updates[index - 3].expected
					check(ui.displayed_actor == source_display, "display preserves independently verified three-update source delay")
					updates += 1
				check(ui.paused and ui.trace_cursor == trace.updates.size() and ui.mismatch_count == 0, "source replay completes through real entry")
		print("CHARACTER_UI_SOURCE_STATUS=passed updates=%d" % updates)
	else:
		print("CHARACTER_UI_SOURCE_STATUS=not_run (supply --fixtures for source parity)")
	ui.bundle.traces = original_traces
	ui.route_index = 0
	ui.change_mode(0)
	var start: Dictionary = capture_state(ui)
	ui.change_appearance("original")
	ui.change_appearance("marker")
	check(capture_state(ui) == start, "appearance changes do not reset phase, queue, collision or movement")
	ui.paused = true
	ui.held_keys = {KEY_RIGHT:true}
	ui.advance_time(5.0)
	check(capture_state(ui) == start, "paused animation and movement freeze")
	ui.single_step()
	check(ui.update_count == 1 and ui.presentation_updates == 1 and ui.paused, "single step advances one logical and visual update")
	ui.held_keys = {KEY_RIGHT:true, KEY_DOWN:true}
	var before_multi: Dictionary = capture_state(ui)
	ui.single_step()
	check(capture_state(ui) == before_multi, "multiple directions freeze the entire animation and display queue")
	ui.clear_held_keys()
	check(ui.held_keys.is_empty(), "focus release clears all held directions")
	ui.reset_state()
	check(capture_state(ui) == start, "reset restores full raw animation state and display history")
	var partitions: Array[Dictionary] = []
	for fps: int in [30,60,120]:
		ui.change_mode(0)
		ui.paused = false
		ui.held_keys = {KEY_RIGHT:true}
		for frame: int in fps: ui.advance_time(1.0 / float(fps))
		partitions.append(capture_state(ui))
	check(partitions[0] == partitions[1] and partitions[1] == partitions[2], "30/60/120 render-time partitions preserve all visual and logical state")
	check(partitions[0].updates == 59, "original logical clock retained")
	for key: String in resources:
		check(ui.character_bundle.textures[key].get_instance_id() == resources[key], "textures stay preloaded through routes, mode changes and reset")
	# A queued pose can differ from the incoming pose. Both reject atomically.
	ui.change_mode(1)
	var before_queued: Dictionary = capture_state(ui)
	var queued_key: String = "%d:%d" % [ui.displayed_actor.animation_index, ui.displayed_actor.animation_cursor]
	var saved_texture: Texture2D = ui.character_bundle.textures[queued_key]
	ui.character_bundle.textures.erase(queued_key)
	ui.single_step()
	check(not ui.startup_error.is_empty() and ui.paused and capture_state(ui) == before_queued, "missing queued pose preserves movement, phase, display queue and replay cursor")
	ui.character_bundle.textures[queued_key] = saved_texture
	ui.startup_error = ""
	# A broken incoming pose lookup must also reject before movement commits.
	ui.change_mode(0)
	ui.held_keys = {KEY_RIGHT:true}
	var before_bad: Dictionary = capture_state(ui)
	ui.character_bundle.textures.clear()
	ui.single_step()
	check(not ui.startup_error.is_empty() and ui.paused and capture_state(ui) == before_bad, "missing required frame rejects the complete update")
	ui.queue_free()
	await process_frame
	print("CHARACTER_UI_TESTS_PASSED checks=%d source_updates=%d" % [checks,updates])
	quit(0)
