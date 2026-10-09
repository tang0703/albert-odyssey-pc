extends SceneTree
## Actual entry + source trajectories. Never inject a later actor to advance it.
const AnimationCore = preload("res://character_animation_core.gd")
const Movement = preload("res://movement_core.gd")
const Loader = preload("res://package_loader.gd")
const HD = preload("res://character_hd_animation.gd")
const HdLoader = preload("res://character_hd_loader.gd")

var checks: int = 0
var updates: int = 0
var fixture_path: String = ""
var report_path: String = ""
var hd_source_status: String = "not_run"

func _initialize() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--fixtures="): fixture_path = arg.trim_prefix("--fixtures=")
		if arg.begins_with("--report="): report_path = arg.trim_prefix("--report=")
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		write_report(false)
		push_error(message)
		quit(1)
		assert(condition, message)

func capture_state(ui: Control) -> Dictionary:
	return {"movement":ui.state.duplicate(true), "animation":ui.animation_state.duplicate(true),
		"displayed":ui.displayed_actor.duplicate(true), "queue":ui.presentation_queue.duplicate(true),
		"updates":ui.update_count, "visual_updates":ui.presentation_updates, "trace_cursor":ui.trace_cursor,
		"expected":ui.expected.duplicate(true),"render_phase":ui.render_phase,"accumulator":ui.accumulator}

func same_partition(a: Dictionary, b: Dictionary) -> bool:
	var left: Dictionary = a.duplicate(true)
	var right: Dictionary = b.duplicate(true)
	for key: String in ["render_phase","accumulator"]:
		if not is_equal_approx(float(left[key]),float(right[key])): return false
		left.erase(key)
		right.erase(key)
	return left==right

func write_report(passed: bool) -> void:
	if report_path.is_empty(): return
	var file: FileAccess = FileAccess.open(report_path,FileAccess.WRITE)
	if file!=null:
		file.store_string(JSON.stringify({"schema":"ao_pc_character_ui_tests_v2","passed":passed,
			"checks":checks,"source_updates":updates,"hd_package_status":hd_source_status,
			"modes":["hd","original","marker"],"synthetic_hd_package":false},"\t")+"\n")

func run() -> void:
	if not FileAccess.file_exists("res://character-pin.json") or not FileAccess.file_exists("res://character-hd-pin.json"):
		print("CHARACTER_UI_HD_STATUS=not_run (actual approved 52-frame HD package unavailable)")
		write_report(false)
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
	check(ui.appearance_mode=="hd" and ui.appearance_select.item_count==3,"actual entry offers all three appearances and defaults to HD")
	check(ui.hd_bundle.get("preloaded",false) and ui.hd_bundle.frames.size()==52 and ui.hd_bundle.textures.size()==52 and ui.hd_bundle.atlases.size()==4,"all 52 actual HD frames and four atlases preloaded before play")
	check(ui.display_delay == 3, "source-proven actor-to-video queue")
	var original_traces: Array = ui.bundle.traces.duplicate(true)
	var resources: Dictionary = {}
	var hd_resources: Dictionary = {}
	for key: String in ui.character_bundle.textures:
		resources[key] = ui.character_bundle.textures[key].get_instance_id()
	for key: String in ui.hd_bundle.textures: hd_resources[key]=ui.hd_bundle.textures[key].get_instance_id()
	if not fixture_path.is_empty():
		var fixtures: Variant = Loader.read_json(fixture_path)
		check(fixtures is Dictionary and fixtures.get("passed") == true and fixtures.get("traces") is Array, "passed original capture fixtures required")
		for mode: String in ["hd", "original", "marker"]:
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
					var selected: Dictionary = HD.select(ui.displayed_actor,ui.render_phase)
					check(selected.ok and HdLoader.lookup(ui.hd_bundle,selected).ok,"displayed source pose always resolves to an actual HD frame")
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
	ui.change_appearance("hd")
	check(capture_state(ui) == start, "appearance changes do not reset phase, queue, collision or movement")
	ui.paused = true
	ui.held_keys = {KEY_RIGHT:true}
	ui.advance_time(5.0)
	check(capture_state(ui) == start, "paused animation and movement freeze")
	ui.single_step()
	check(ui.update_count == 1 and ui.presentation_updates == 1 and ui.paused, "single step advances one logical and visual update")
	check(ui.render_phase==0.0 and ui.accumulator==0.0,"successful single-step resets fractional presentation phase")
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
	check(same_partition(partitions[0],partitions[1]) and same_partition(partitions[1],partitions[2]), "30/60/120 render-time partitions preserve all visual and logical state")
	check(partitions[0].updates == 59, "original logical clock retained")
	for key: String in resources:
		check(ui.character_bundle.textures[key].get_instance_id() == resources[key], "textures stay preloaded through routes, mode changes and reset")
	for key: String in hd_resources:
		check(ui.hd_bundle.textures[key].get_instance_id()==hd_resources[key],"HD atlas regions stay preloaded through all source routes and modes")
	hd_phase_checks(ui)
	hd_failure_checks(ui)
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
	if not fixture_path.is_empty() and updates==2052*3:
		hd_source_status="passed"
		print("CHARACTER_UI_HD_STATUS=passed")
	else:
		print("CHARACTER_UI_HD_STATUS=not_run (full 2052 source updates per mode required)")
	write_report(true)
	print("CHARACTER_UI_TESTS_PASSED checks=%d source_updates=%d" % [checks,updates])
	quit(0)

func prepare_walking(ui: Control, ticks: int) -> void:
	ui.change_mode(0)
	ui.change_appearance("hd")
	ui.held_keys={KEY_RIGHT:true}
	ui.paused=false
	for index: int in ticks: ui.advance_time(ui.tick_seconds)
	check(ui.startup_error.is_empty(),"source-driven walking setup succeeds")

func hd_phase_checks(ui: Control) -> void:
	prepare_walking(ui,7)
	check(int(ui.displayed_actor.animation_timer)==3,"displayed timer reaches exact first third boundary context through real updates")
	var before: Dictionary = capture_state(ui)
	ui.advance_time(ui.tick_seconds*0.2)
	var first: Dictionary = HD.select(ui.displayed_actor,ui.render_phase)
	ui.advance_time(ui.tick_seconds*0.2)
	var second: Dictionary = HD.select(ui.displayed_actor,ui.render_phase)
	check(first.subframe_index==0 and second.subframe_index==1 and ui.update_count==before.updates,"fractional time switches HD frame at 3⅓ updates without moving source state")
	check(ui.state==before.movement and ui.animation_state==before.animation,"HD-only phase cannot mutate movement or original animation")
	var frozen: Dictionary = capture_state(ui)
	ui.toggle_pause()
	ui.advance_time(4.0)
	check(capture_state(ui)==frozen,"pause freezes subframe, accumulator, movement and source queue")
	ui.toggle_pause()
	check(capture_state(ui)==frozen,"resume preserves the fractional phase")
	ui.held_keys={KEY_RIGHT:true,KEY_DOWN:true}
	ui.advance_time(1.0)
	check(capture_state(ui)==frozen,"multi-direction input freezes fractional phase as well as source state")
	ui.held_keys={KEY_RIGHT:true}
	ui.advance_time(ui.tick_seconds*0.1)
	check(is_equal_approx(ui.render_phase,0.5) and ui.update_count==frozen.updates,"releasing extra direction resumes sub-tick presentation immediately")
	ui.paused=true
	ui.single_step()
	check(ui.render_phase==0 and ui.accumulator==0 and ui.update_count==frozen.updates+1,"single-step from partial phase advances once and lands at phase zero")
	ui.reset_state()
	check(ui.render_phase==0 and ui.accumulator==0 and ui.presentation_updates==0,"reset clears HD subframe and original delay queue")
	var partition_results: Array[Dictionary] = []
	for mode: String in ["hd","original","marker"]:
		for fps: int in [30,60,120]:
			ui.change_mode(0)
			ui.change_appearance(mode)
			ui.held_keys={KEY_RIGHT:true}
			ui.paused=false
			for frame: int in fps: ui.advance_time(1.0/float(fps))
			partition_results.append(capture_state(ui))
	for value: Dictionary in partition_results:
		check(same_partition(value,partition_results[0]),"three appearance modes and 30/60/120 render partitions share one source timeline")

func hd_failure_checks(ui: Control) -> void:
	# Source frame/timer reached naturally. Next delayed pose timer3 would select
	# subframe1 at old phase0.7 but subframe0 after a successful single step.
	prepare_walking(ui,6)
	ui.advance_time(ui.tick_seconds*0.7)
	ui.paused=true
	var candidate: Dictionary = ui.presentation_queue[0].duplicate(true)
	var required: Dictionary = HD.select(candidate,0.0)
	var saved: Texture2D = ui.hd_bundle.textures[required.frame_id]
	var before: Dictionary = capture_state(ui)
	ui.hd_bundle.textures.erase(required.frame_id)
	ui.single_step()
	check(not ui.startup_error.is_empty() and ui.paused and capture_state(ui)==before,"missing HD phase-zero pose rejects single-step before raw state, queue or phase commits")
	ui.hd_bundle.textures[required.frame_id]=saved
	ui.startup_error=""
	prepare_walking(ui,7)
	ui.advance_time(ui.tick_seconds*0.2)
	var next_fraction: Dictionary = HD.select(ui.displayed_actor,0.4)
	saved=ui.hd_bundle.textures[next_fraction.frame_id]
	before=capture_state(ui)
	ui.hd_bundle.textures.erase(next_fraction.frame_id)
	ui.advance_time(ui.tick_seconds*0.2)
	check(not ui.startup_error.is_empty() and ui.paused and capture_state(ui)==before,"missing HD render-only subframe preserves previous fractional clock and all source state")
	ui.hd_bundle.textures[next_fraction.frame_id]=saved
	ui.startup_error=""
	prepare_walking(ui,0)
	ui.change_mode(1)
	before=capture_state(ui)
	var all_textures: Dictionary = ui.hd_bundle.textures.duplicate()
	ui.hd_bundle.textures.clear()
	ui.single_step()
	check(not ui.startup_error.is_empty() and ui.paused and capture_state(ui)==before,"missing HD incoming/replay pose preserves expected state and trace cursor")
	ui.hd_bundle.textures=all_textures
	ui.startup_error=""
