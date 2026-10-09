extends SceneTree
## Real Godot input routing and actual source-bound movement; no fabricated walls.

var checks: int = 0
var completed_routes: int = 0
var updates_observed: int = 0

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		push_error(message)
		quit(1)
		assert(condition, message)

func set_key(code: Key, pressed: bool, echo: bool = false) -> void:
	var event := InputEventKey.new()
	event.keycode = code
	event.physical_keycode = code
	event.pressed = pressed
	event.echo = echo
	Input.parse_input_event(event)
	await process_frame

func key(code: Key) -> void:
	await set_key(code, true)
	await set_key(code, false)

func click(item: Control) -> void:
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_LEFT
	event.position = root.get_screen_transform() * item.get_global_rect().get_center()
	event.pressed = true
	Input.parse_input_event(event)
	await process_frame
	event = event.duplicate()
	event.pressed = false
	Input.parse_input_event(event)
	await process_frame

func assert_layout(node: Node, bounds: Rect2) -> void:
	for child: Node in node.get_children():
		if child is Control and child.is_visible_in_tree() and not child is Popup:
			var rect: Rect2 = child.get_global_rect()
			check(bounds.grow(1.0).encloses(rect), "Control outside logical viewport: %s %s" % [child.name, rect])
		assert_layout(child, bounds)

func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	ui.ui_test_mode = true
	root.add_child(ui)
	await process_frame
	await process_frame
	check(ui.startup_error.is_empty(), "actual approved scene package loads: " + ui.startup_error)
	check(ui.verified_indices.size() == 108 and ui.state.size() == 17, "source-bound domain and comparison fields")
	check(ui.map_canvas.texture_filter == CanvasItem.TEXTURE_FILTER_NEAREST, "background nearest-neighbour filtering")
	check(is_equal_approx(ui.map_canvas.size.x / ui.map_canvas.size.y, 320.0 / 224.0), "fixed background aspect ratio")
	assert_layout(ui, Rect2(Vector2.ZERO, ui.size))
	ui.update_completed.connect(func(_result: Dictionary) -> void: updates_observed += 1)
	ui.route_completed.connect(func(_id: String) -> void: completed_routes += 1)
	var initial: Dictionary = ui.state.duplicate(true)
	await key(KEY_SPACE)
	check(ui.paused, "Space pauses")
	await set_key(KEY_RIGHT, true)
	ui.advance_time(2.0)
	check(ui.state == initial, "paused held movement does not advance")
	await key(KEY_PERIOD)
	check(ui.update_count == 1 and ui.paused and updates_observed == 1, "period executes precisely one real core update while paused")
	await set_key(KEY_RIGHT, false)
	await key(KEY_R)
	check(ui.state == initial and ui.update_count == 0, "R restores every state field and counters")
	await click(ui.play_button)
	check(not ui.paused, "mouse play uses live Control hit testing")
	await set_key(KEY_SPACE, true)
	await set_key(KEY_SPACE, true, true)
	check(ui.paused, "keyboard auto-repeat does not repeatedly toggle pause")
	await set_key(KEY_SPACE, false)
	var overlay_before: bool = ui.show_overlay
	await key(KEY_F1)
	check(ui.show_overlay != overlay_before, "F1 overlay")
	await click(ui.overlay_button)
	check(ui.show_overlay == overlay_before, "mouse overlay")
	await set_key(KEY_UP, true)
	await set_key(KEY_W, true)
	check(ui.active_directions() == ["up"], "arrow and WASD alias count as one direction")
	await set_key(KEY_LEFT, true)
	var before_multi: Dictionary = ui.state.duplicate(true)
	var before_count: int = ui.update_count
	await key(KEY_PERIOD)
	check(ui.state == before_multi and ui.update_count == before_count and ui.diagnostics.reason == "multiple_directions", "multiple directions skip the whole update")
	await set_key(KEY_UP, false)
	await set_key(KEY_W, false)
	await set_key(KEY_LEFT, false)

	# Reach a real captured queued-correction state, then ensure multi-input cannot consume it.
	var queued_state: Dictionary = {}
	for trace: Dictionary in ui.bundle.traces:
		for record: Dictionary in trace.updates:
			if int(record.expected.slide_x_word) != 0 or int(record.expected.slide_y_word) != 0:
				queued_state = record.expected.duplicate(true)
				break
		if not queued_state.is_empty(): break
	check(not queued_state.is_empty(), "reference corpus contains actual deferred correction")
	ui.state = queued_state.duplicate(true)
	await set_key(KEY_DOWN, true)
	await set_key(KEY_RIGHT, true)
	await key(KEY_PERIOD)
	check(ui.state == queued_state, "multi-key does not consume captured deferred correction")
	await set_key(KEY_DOWN, false)
	await set_key(KEY_RIGHT, false)
	await key(KEY_R)

	# Discover a boundary from a captured valid position, without editing shape/flags/domain.
	var boundary_found: bool = false
	for trace: Dictionary in ui.bundle.traces:
		for record: Dictionary in trace.updates:
			for direction: String in ["up", "down", "left", "right"]:
				var candidate: Dictionary = ui.core.step(record.expected, direction)
				if candidate.ok and candidate.diagnostics.get("reason") == "test_boundary":
					ui.state = record.expected.duplicate(true)
					var input_key: Key = {"up": KEY_UP, "down": KEY_DOWN, "left": KEY_LEFT, "right": KEY_RIGHT}[direction]
					await set_key(input_key, true)
					await key(KEY_PERIOD)
					await set_key(input_key, false)
					check(ui.state == record.expected and ui.boundary_label.text == "測試邊界", "out-of-domain preserves all fields and labels a test boundary")
					await process_frame
					assert_layout(ui, Rect2(Vector2.ZERO, ui.size))
					boundary_found = true
					break
			if boundary_found: break
		if boundary_found: break
	check(boundary_found, "captured domain has a reachable test boundary")

	# Four traces use real core outputs and actual completion signals.
	for route: int in ui.bundle.traces.size():
		await key(KEY_1 + route)
		check(ui.replay_mode and ui.route_index == route and ui.paused, "keyboard selects captured route and pauses")
		var count: int = ui.bundle.traces[route].updates.size()
		await click(ui.play_button)
		for step: int in count:
			ui.advance_time(ui.tick_seconds)
			check(ui.current_differences.is_empty(), "all 17 fields at each actual route update")
		check(ui.paused and ui.trace_cursor == count and ui.mismatch_count == 0, "route ends naturally without state injection")
		await process_frame
		assert_layout(ui, Rect2(Vector2.ZERO, ui.size))
	check(completed_routes == 4, "four real route_completed signals")
	await click(ui.reset_button)
	check(ui.trace_cursor == 0 and ui.mismatch_count == 0, "mouse replay reset")
	await click(ui.step_button)
	check(ui.trace_cursor == 1 and ui.paused, "mouse replay step")

	# A fixed sequence of durations at three render rates must produce identical integer states.
	var final_states: Array[Dictionary] = []
	for fps: int in [30, 60, 120]:
		ui.change_mode(0)
		ui.paused = false
		await set_key(KEY_RIGHT, true)
		for frame: int in fps: ui.advance_time(1.0 / float(fps))
		await set_key(KEY_RIGHT, false)
		final_states.append({"state":ui.state.duplicate(true), "updates":ui.update_count})
	check(final_states[0] == final_states[1] and final_states[1] == final_states[2], "30/60/120 render-delta partitions yield identical updates and state")
	check(final_states[0].updates == 59, "logical period follows original 176473/10546875 seconds")
	ui.clear_held_keys()
	check(ui.held_keys.is_empty(), "focus loss clears held controls")
	ui.queue_free()
	await process_frame
	print("EXPLORATION_UI_TESTS_PASSED checks=%d" % checks)
	quit(0)
