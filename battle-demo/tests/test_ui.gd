extends SceneTree
var checks: int = 0

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message); quit(1); assert(value,message)

func _initialize() -> void:
	call_deferred("run")

func key(code: Key) -> void:
	var press := InputEventKey.new()
	press.keycode = code; press.pressed = true
	Input.parse_input_event(press)
	await process_frame
	var release := InputEventKey.new()
	release.keycode = code; release.pressed = false
	Input.parse_input_event(release)
	await process_frame

func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	ui.ui_test_mode = true
	root.add_child(ui)
	await process_frame
	check(ui.title_overlay.visible and not ui.started,"title entry")
	await key(KEY_ENTER)
	check(ui.started and not ui.title_overlay.visible,"keyboard start")
	# Let the initial enemy action complete, then exercise a real party turn.
	ui.perform(ui.battle.enemy_command())
	ui.busy = false
	ui.refresh()
	check(ui.battle.current == "mage","enemy to party")
	ui.commands[0].grab_focus()
	await key(KEY_RIGHT)
	check(ui.commands[1].has_focus(),"arrow command navigation")
	await key(KEY_ENTER)
	check(ui.selected_action == "wave" and ui.target_box.visible,"keyboard skill selection")
	var mp: int = ui.battle.unit_by_id("mage")["mp"]
	check(ui.preview_label.text.contains("重甲兵") and ui.preview_label.text.contains("斥候"),"AOE preview all targets")
	await key(KEY_ESCAPE)
	check(ui.selected_action.is_empty() and ui.battle.unit_by_id("mage")["mp"] == mp,"escape cancels without cost")
	ui.choose_command(1)
	ui.select_target_index(0)
	await key(KEY_ENTER)
	check(ui.busy and ui.battle.unit_by_id("mage")["mp"] == mp-8,"keyboard confirm cost")
	ui.confirm_action(); ui.choose_command(0)
	check(ui.battle.unit_by_id("mage")["mp"] == mp-8 and ui.selected_action.is_empty(),"busy double click blocked")
	ui.show_settings()
	check(ui.paused and ui.modal.visible,"pause")
	ui.close_settings()
	check(not ui.paused and not ui.modal.visible,"resume")
	# Mouse hit testing on a rendered command button.
	ui.start_battle()
	ui.perform(ui.battle.enemy_command()); ui.busy = false; ui.refresh()
	await process_frame
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.position = root.get_screen_transform() * ui.commands[0].get_global_rect().get_center()
	click.pressed = true
	Input.parse_input_event(click)
	await process_frame
	click = click.duplicate(); click.pressed = false
	Input.parse_input_event(click)
	await process_frame
	check(ui.selected_action == "attack","mouse command selection")
	ui.cancel_selection()
	# Finish both outcomes through presentation and confirm replay resets all state.
	for outcome: String in ["victory","defeat"]:
		ui.start_battle()
		for step: int in range(300):
			if not ui.battle.outcome.is_empty(): break
			var request: Dictionary
			if ui.battle.unit_by_id(ui.battle.current)["side"] == "enemy": request = ui.battle.enemy_command()
			elif outcome == "defeat": request = ui.battle.request("guard",ui.battle.current)
			else: request = ui.auto_command()
			ui.perform(request)
			ui.busy = false
			for popup: Node in get_nodes_in_group("popups"): popup.queue_free()
			await process_frame
		check(ui.battle.outcome == outcome,"UI complete " + outcome)
		ui.show_result()
		check(ui.modal.visible,"result screen " + outcome)
		ui.start_battle()
		check(ui.battle.potions == 3 and ui.battle.round_number == 1 and ui.battle.journal.is_empty(),"replay reset " + outcome)
	# Check the logical 1080p layout; stretch scales the same geometry at higher resolutions.
	await process_frame
	check(ui.preview_label.get_global_rect().end.y <= 1080 and ui.command_box.get_global_rect().end.x <= 1920,"controls within viewport")
	print("BATTLE UI: %d checks passed" % checks)
	ui.queue_free()
	await process_frame
	quit()
