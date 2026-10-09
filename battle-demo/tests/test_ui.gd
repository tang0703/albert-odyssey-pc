extends SceneTree
var checks: int = 0
var completions: int = 0
var effects: Array[Dictionary] = []
var end_after_down: bool = true
var fixed_commands: Array[Dictionary] = []
var impact_kinds: Dictionary = {}
var impacts_match_actions: bool = true
var bystander_idle_checkpoint: float = -1.0

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

func wait_presentation(ui: Control, before: int) -> void:
	var deadline: int = Time.get_ticks_msec() + 8000
	while completions == before and Time.get_ticks_msec() < deadline:
		await process_frame
	check(completions == before + 1 and not ui.busy,"real presentation_finished within timeout")

func act(ui: Control, request: Dictionary) -> void:
	var before: int = completions
	ui.perform(request)
	check(ui.busy,"action starts presentation")
	await wait_presentation(ui,before)

func replay_appearance(override: Dictionary, record_commands: bool) -> String:
	var replay: Control = load("res://main.tscn").instantiate()
	replay.ui_test_mode = true
	replay.settings_enabled = false
	replay.appearances_override = override
	root.add_child(replay)
	replay.speed = 2.0
	replay.presentation_finished.connect(func() -> void: completions += 1)
	var presented: Array[Dictionary] = []
	replay.effect_presented.connect(func(event: Dictionary) -> void: presented.append(event.duplicate(true)))
	check(replay.startup_errors.is_empty(),"appearance replay preloads successfully")
	replay.start_battle()
	for index: int in range(8):
		var command: Dictionary
		if record_commands:
			command = replay.battle.enemy_command() if replay.battle.unit_by_id(replay.battle.current)["side"] == "enemy" else replay.auto_command()
			fixed_commands.append(command.duplicate(true))
		else:
			var recorded: Dictionary = fixed_commands[index]
			check(recorded["actor"] == replay.battle.current,"appearance does not change actor order")
			command = replay.battle.request(recorded["action"],recorded["target"])
		await act(replay,command)
	var signature: String = JSON.stringify({"units":replay.battle.units,"totals":replay.battle.totals,"potions":replay.battle.potions,"events":presented,"display":replay.display_units})
	replay.queue_free()
	await process_frame
	return signature

func appearance_independence() -> void:
	var configured: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/appearances.json"))
	var procedural: Dictionary = configured.duplicate(true)
	for definition: Dictionary in procedural.values():
		definition["renderer"] = "procedural"
		definition["states"] = {}
	var baseline: String = await replay_appearance(procedural,true)
	# A real Texture2D resource exercises sprite loading even before final art lands.
	var fixture: String = "user://ui-appearance-test.tres"
	var texture := GradientTexture2D.new()
	texture.gradient = Gradient.new()
	texture.width = 16
	texture.height = 24
	check(ResourceSaver.save(texture,fixture) == OK,"sprite replay fixture saved")
	var sprites: Dictionary = procedural.duplicate(true)
	for definition: Dictionary in sprites.values():
		definition["renderer"] = "sprite"
		definition["default_facing"] = "left"
		for animation: String in ["idle","attack","hurt","down"]:
			definition["states"][animation] = {"frames":[fixture,fixture,fixture],"durations":[0.04,0.07,0.1],"loop":animation == "idle"}
		definition["states"]["attack"]["hit_frame"] = 1
	check(await replay_appearance(sprites,false) == baseline,"same UI commands produce identical rules and events with sprite timing and facing")
	DirAccess.remove_absolute(fixture)
	var contains_art: bool = false
	for definition: Dictionary in configured.values():
		if definition.get("renderer") == "sprite": contains_art = true
	if contains_art:
		check(await replay_appearance(configured,false) == baseline,"production character art preserves identical UI battle results")
	else: print("BATTLE UI: production sprite replay pending art; procedural/synthetic sprite comparison passed")

func run() -> void:
	var ui: Control = load("res://main.tscn").instantiate()
	ui.ui_test_mode = true
	ui.settings_enabled = false
	root.add_child(ui)
	ui.presentation_finished.connect(func() -> void:
		completions += 1
		if bystander_idle_checkpoint >= 0.0:
			check(ui.fighters["healer"].state == "idle" and ui.fighters["healer"].clock >= bystander_idle_checkpoint,"finishing an action preserves bystander idle progress")
			bystander_idle_checkpoint = -1.0)
	ui.effect_presented.connect(func(event: Dictionary) -> void:
		effects.append(event)
		if event["type"] == "damage":
			for impact: Node in get_nodes_in_group("impacts"):
				if impact.get_parent() == ui.stage:
					impact_kinds[impact.kind] = true
					if impact.kind != ui.presentation_action: impacts_match_actions = false
		if event["type"] == "end":
			for unit: Dictionary in ui.battle.units:
				if unit["hp"] == 0 and not ui.fighters[unit["id"]].is_animation_finished(): end_after_down = false)
	await process_frame
	check(ui.startup_errors.is_empty() and ui.audio_streams.size() == 2,"assets and audio ready before start")
	for fighter: Control in ui.fighters.values():
		check(fighter.configured and not fighter.is_processing(),"single UI animation clock")
	check(ui.title_overlay.visible and not ui.started,"title entry")
	await key(KEY_ENTER)
	check(ui.started and not ui.title_overlay.visible,"keyboard start")
	# The healer is a bystander in the initial enemy action. Record nonzero
	# progress and inspect it in the completion callback, not after a timed frame.
	ui.fighters["healer"].advance_animation(0.37)
	bystander_idle_checkpoint = ui.fighters["healer"].clock
	# Core resolves immediately; the view waits for the authored hit point.
	var request: Dictionary = ui.battle.enemy_command()
	var target: String = request["target"]
	var hp_before: int = ui.display_units[target]["hp"]
	var before: int = completions
	ui.perform(request)
	check(ui.battle.unit_by_id(target)["hp"] < hp_before and ui.display_units[target]["hp"] == hp_before,"HP retained before hit")
	check(effects.is_empty(),"no early impact events")
	ui.show_settings()
	var frozen_time: float = ui.fighters[request["actor"]].clock
	var frozen_elapsed: float = ui.presentation_elapsed
	await create_timer(0.18).timeout
	check(ui.paused and ui.fighters[request["actor"]].clock == frozen_time and ui.presentation_elapsed == frozen_elapsed,"pause freezes animation and presentation")
	ui.toggle_speed()
	check(ui.speed == 2.0,"speed change while paused")
	ui.close_settings()
	var impact_deadline: int = Time.get_ticks_msec()+3000
	while not ui.presentation_hit and Time.get_ticks_msec() < impact_deadline: await process_frame
	check(ui.presentation_hit and not get_nodes_in_group("impacts").is_empty(),"hit creates native effect")
	ui.show_settings()
	var hurt_clock: float = ui.fighters[target].clock
	var burst_clock: float = get_nodes_in_group("impacts")[0].elapsed
	await create_timer(0.12).timeout
	check(ui.fighters[target].clock == hurt_clock and get_nodes_in_group("impacts")[0].elapsed == burst_clock,"pause freezes hurt and impact together")
	ui.close_settings()
	await wait_presentation(ui,before)
	check(ui.display_units[target]["hp"] == ui.battle.unit_by_id(target)["hp"] and not effects.is_empty(),"impact updates displayed HP")
	check(ui.battle.current == "mage","enemy to party")
	ui.commands[0].grab_focus()
	await key(KEY_RIGHT)
	check(ui.commands[1].has_focus(),"arrow command navigation")
	await key(KEY_ENTER)
	check(ui.selected_action == "wave" and ui.target_box.visible,"keyboard skill selection")
	var mp: int = ui.battle.unit_by_id("mage")["mp"]
	check(ui.preview_label.text.contains(ui.display_name("armor")) and ui.preview_label.text.contains(ui.display_name("scout")),"AOE preview all targets")
	await key(KEY_ESCAPE)
	check(ui.selected_action.is_empty() and ui.battle.unit_by_id("mage")["mp"] == mp,"escape cancels without cost")
	ui.choose_command(1)
	ui.select_target_index(0)
	before = completions
	await key(KEY_ENTER)
	check(ui.busy and ui.battle.unit_by_id("mage")["mp"] == mp-8,"keyboard confirm cost")
	ui.confirm_action(); ui.choose_command(0)
	ui.perform(ui.battle.enemy_command())
	check(ui.battle.unit_by_id("mage")["mp"] == mp-8 and ui.selected_action.is_empty() and ui.battle.journal.size() == 2,"busy duplicate inputs blocked")
	ui.toggle_speed()
	check(ui.speed == 1.0,"speed changes during actual presentation")
	await wait_presentation(ui,before)
	# Keep Enter down across a completed action and the next enemy turn.
	var held := InputEventKey.new()
	held.keycode = KEY_ENTER
	held.pressed = true
	Input.parse_input_event(held)
	await process_frame
	await act(ui,ui.battle.enemy_command())
	var held_journal: int = ui.battle.journal.size()
	for repeat_index: int in range(4):
		var repeated := InputEventKey.new()
		repeated.keycode = KEY_ENTER
		repeated.pressed = true
		repeated.echo = true
		Input.parse_input_event(repeated)
		await process_frame
	check(ui.selected_action.is_empty() and ui.battle.journal.size() == held_journal,"held Enter cannot confirm or select the next party turn")
	held.pressed = false
	Input.parse_input_event(held)
	await process_frame
	# Mouse hit testing remains live in integration mode.
	ui.start_battle()
	await act(ui,ui.battle.enemy_command())
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
	# All actions reach the real completion signal, including hurt and down.
	ui.speed = 2.0
	for outcome: String in ["victory","defeat"]:
		ui.start_battle()
		effects.clear()
		for step: int in range(300):
			if not ui.battle.outcome.is_empty(): break
			if ui.battle.unit_by_id(ui.battle.current)["side"] == "enemy": request = ui.battle.enemy_command()
			elif outcome == "defeat": request = ui.battle.request("guard",ui.battle.current)
			else: request = ui.auto_command()
			await act(ui,request)
		check(ui.battle.outcome == outcome,"UI complete " + outcome)
		check(ui.modal.visible and not ui.busy,"automatic result screen after animation " + outcome)
		check(end_after_down and effects[-1]["type"] == "end" and effects[-1]["outcome"] == outcome,"end event follows completed down animations " + outcome)
		for unit: Dictionary in ui.battle.units:
			if unit["hp"] == 0:
				check(ui.fighters[unit["id"]].state == "down" and ui.fighters[unit["id"]].is_animation_finished(),"down completes and holds last frame")
		ui.start_battle()
		check(ui.battle.potions == 3 and ui.battle.round_number == 1 and ui.battle.journal.is_empty(),"replay resets rules " + outcome)
		check(ui.presentation_events.is_empty() and ui.pending_down.is_empty() and ui.reactions.is_empty() and get_nodes_in_group("popups").is_empty() and get_nodes_in_group("impacts").is_empty(),"replay clears presentation " + outcome)
		for fighter: Control in ui.fighters.values(): check(fighter.state == "idle","replay resets animation")
	await process_frame
	check(ui.preview_label.get_global_rect().end.y <= 1080 and ui.command_box.get_global_rect().end.x <= 1920,"controls within viewport")
	check(impacts_match_actions and impact_kinds.has("attack") and impact_kinds.has("heavy"),"ordinary and heavy hits use their own effect variants")
	ui.queue_free()
	await process_frame
	await appearance_independence()
	print("BATTLE UI: %d checks passed" % checks)
	quit()
