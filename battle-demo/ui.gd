extends Control

const Core = preload("res://core.gd")
const Fighter = preload("res://fighter.gd")
const Backdrop = preload("res://backdrop.gd")
var battle: DemoBattle
var appearances: Dictionary
var fighters: Dictionary = {}
var cards: Dictionary = {}
var targets_buttons: Array[Button] = []
var commands: Array[Button] = []
var round_label: Label
var order_label: Label
var message_label: Label
var preview_label: Label
var log_view: RichTextLabel
var command_box: HBoxContainer
var target_box: HBoxContainer
var title_overlay: PanelContainer
var modal: PanelContainer
var modal_text: Label
var confirm_button: Button
var cancel_button: Button
var speed_button: Button
var stage: Control
var audio_player: AudioStreamPlayer
var selected_action: String = ""
var selected_target: String = ""
var pending: Dictionary = {}
var busy: bool = false
var started: bool = false
var paused: bool = false
var animation_left: float = 0.0
var speed: float = 1.0
var volume: float = 0.35
var resolution_index: int = 0
var qa: bool = false
var qa_path: String = ""
var qa_seconds: float = 0.0
var qa_started: int = 0
var qa_last: int = 0
var qa_frames: Array[float] = []
var qa_samples: Array[Dictionary] = []
var qa_actions: int = 0
var qa_fights: int = 0
var qa_next_sample: int = 0
var qa_shot: bool = false
var qa_variant: String = ""
var qa_target: Vector2i = Vector2i.ZERO
var qa_capture_size: Vector2i = Vector2i.ZERO
var start_button: Button
var ui_test_mode: bool = false

func _ready() -> void:
	Engine.max_fps = 60
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--qa-dir="): qa_path = arg.trim_prefix("--qa-dir="); qa = true
		if arg.begins_with("--qa-seconds="): qa_seconds = float(arg.trim_prefix("--qa-seconds="))
		if arg.begins_with("--qa-variant="): qa_variant = arg.trim_prefix("--qa-variant=")
		if arg.begins_with("--qa-size="):
			var dimensions: PackedStringArray = arg.trim_prefix("--qa-size=").split("x")
			qa_target = Vector2i(int(dimensions[0]),int(dimensions[1]))
	if qa_target.x > 0:
		get_window().borderless = true
		get_window().position = Vector2i.ZERO
		get_window().size = qa_target
	battle = Core.new()
	appearances = JSON.parse_string(FileAccess.get_file_as_string("res://data/appearances.json"))
	load_settings()
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["Microsoft JhengHei", "Microsoft YaHei", "Noto Sans CJK TC"])
	var style := Theme.new()
	style.default_font = font
	style.default_font_size = 25
	theme = style
	build_ui()
	speed_button.text = "演出 %d×" % int(speed)
	refresh()
	start_button.grab_focus()
	if qa:
		DirAccess.make_dir_recursive_absolute(qa_path)
		qa_started = Time.get_ticks_usec()
		qa_last = qa_started
		start_battle()

func panel_style(color: String = "142535") -> StyleBoxFlat:
	var result := StyleBoxFlat.new()
	result.bg_color = Color(color)
	result.border_color = Color("345064")
	result.set_border_width_all(1)
	result.set_corner_radius_all(12)
	result.content_margin_left = 22
	result.content_margin_right = 22
	result.content_margin_top = 14
	result.content_margin_bottom = 14
	return result

func label(text: String, font_size: int = 25, color: String = "e3e9ed") -> Label:
	var node := Label.new()
	node.text = text
	node.add_theme_font_size_override("font_size",font_size)
	node.add_theme_color_override("font_color",Color(color))
	return node

func button(text: String, handler: Callable) -> Button:
	var node := Button.new()
	node.text = text
	node.custom_minimum_size = Vector2(150,54)
	node.add_theme_stylebox_override("normal",panel_style("1d3548"))
	node.add_theme_stylebox_override("hover",panel_style("2c4c5e"))
	node.add_theme_stylebox_override("pressed",panel_style("3a5865"))
	var focus := panel_style("254457")
	focus.border_color = Color("f4d39c")
	focus.set_border_width_all(3)
	node.add_theme_stylebox_override("focus",focus)
	node.pressed.connect(handler)
	return node

func build_ui() -> void:
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for edge: String in ["left","right","top","bottom"]: margin.add_theme_constant_override("margin_"+edge,30)
	add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation",12)
	margin.add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	var brand := label("三曜試煉",38,"f1d4a3")
	brand.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(brand)
	header.add_child(label("TACTICAL TRIAL  /  新規則戰鬥 DEMO",21,"9bb2c4"))
	speed_button = button("演出 1×",toggle_speed)
	header.add_child(speed_button)
	header.add_child(button("設定 / 暫停",show_settings))
	round_label = label("",25,"f1d4a3")
	column.add_child(round_label)
	order_label = label("",23,"a8bdcb")
	column.add_child(order_label)
	stage = Control.new()
	stage.custom_minimum_size = Vector2(0,375)
	stage.size_flags_vertical = Control.SIZE_EXPAND_FILL
	stage.clip_contents = true
	column.add_child(stage)
	var backdrop := Backdrop.new()
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	stage.add_child(backdrop)
	stage.resized.connect(func() -> void: backdrop.queue_redraw(); layout_fighters())
	for i: int in range(battle.units.size()):
		var unit: Dictionary = battle.units[i]
		var fighter := Fighter.new()
		fighter.appearance = appearances[unit["appearance"]]
		fighter.facing = 1.0 if unit["side"] == "party" else -1.0
		fighter.size = Vector2(150,210)
		fighter.mouse_filter = Control.MOUSE_FILTER_IGNORE
		stage.add_child(fighter)
		fighters[unit["id"]] = fighter
		var name_label := label(unit["name"],22)
		name_label.position = Vector2(-15,208)
		name_label.size = Vector2(180,34)
		name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		fighter.add_child(name_label)
		var hp := ProgressBar.new()
		hp.position = Vector2(0,245)
		hp.size = Vector2(150,9)
		hp.show_percentage = false
		hp.max_value = unit["max_hp"]
		var fill := StyleBoxFlat.new()
		fill.bg_color = Color("79cdd4") if unit["side"] == "party" else Color("d9a184")
		fill.set_corner_radius_all(4)
		hp.add_theme_stylebox_override("fill",fill)
		var track := StyleBoxFlat.new()
		track.bg_color = Color("1b2d38")
		track.set_corner_radius_all(4)
		hp.add_theme_stylebox_override("background",track)
		fighter.add_child(hp)
		fighter.set_meta("hp",hp)
	var party_row := HBoxContainer.new()
	party_row.add_theme_constant_override("separation",10)
	column.add_child(party_row)
	for unit: Dictionary in battle.units:
		var card := PanelContainer.new()
		card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		card.add_theme_stylebox_override("panel",panel_style())
		var text := label("",23)
		card.add_child(text)
		party_row.add_child(card)
		cards[unit["id"]] = text
	message_label = label("",27,"f1d4a3")
	column.add_child(message_label)
	command_box = HBoxContainer.new()
	command_box.add_theme_constant_override("separation",10)
	column.add_child(command_box)
	for index: int in range(4):
		var command := button("",func() -> void: choose_command(index))
		command.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		command_box.add_child(command)
		commands.append(command)
	target_box = HBoxContainer.new()
	target_box.add_theme_constant_override("separation",10)
	column.add_child(target_box)
	for i: int in range(3):
		var target := button("",func() -> void: select_target_index(i))
		target.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		target_box.add_child(target)
		targets_buttons.append(target)
	confirm_button = button("確認行動",confirm_action)
	cancel_button = button("返回",cancel_selection)
	target_box.add_child(confirm_button)
	target_box.add_child(cancel_button)
	preview_label = label("",23,"a6c5d3")
	preview_label.custom_minimum_size.y = 36
	column.add_child(preview_label)
	log_view = RichTextLabel.new()
	log_view.custom_minimum_size = Vector2(0,95)
	log_view.scroll_following = true
	log_view.add_theme_font_size_override("normal_font_size",21)
	column.add_child(log_view)
	column.add_child(label("方向鍵 選擇  ·  Enter 確認  ·  Esc 返回 / 暫停     |     原創測試角色，非原作戰鬥還原",19,"7995a8"))
	audio_player = AudioStreamPlayer.new()
	add_child(audio_player)
	title_overlay = PanelContainer.new()
	title_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	title_overlay.add_theme_stylebox_override("panel",panel_style("0b1828"))
	add_child(title_overlay)
	var center := CenterContainer.new()
	title_overlay.add_child(center)
	var welcome := VBoxContainer.new()
	welcome.add_theme_constant_override("separation",24)
	center.add_child(welcome)
	welcome.add_child(label("TACTICAL TRIAL / 01",24,"79cdd4"))
	welcome.add_child(label("三曜試煉",76,"f1d4a3"))
	welcome.add_child(label("三位旅人，一場考驗。",32))
	welcome.add_child(label("掌握行動順序，分配魔力，在攻守之間做出選擇。",26,"a8bdcb"))
	start_button = button("開始戰鬥  →",start_battle)
	welcome.add_child(start_button)
	welcome.add_child(label("獨立新規則 demo｜原創簡易 2D 角色｜三人對三敵",22,"7995a8"))
	modal = PanelContainer.new()
	modal.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	modal.add_theme_stylebox_override("panel",panel_style("101f30"))
	modal.hide()
	add_child(modal)

func layout_fighters() -> void:
	for i: int in range(battle.units.size()):
		var fighter: Control = fighters[battle.units[i]["id"]]
		var slot: int = i % 3
		var x: float = [0.14,0.26,0.38][slot] if i < 3 else [0.86,0.74,0.62][slot]
		fighter.position = Vector2(stage.size.x*x-75,stage.size.y*0.45-95+slot*20)

func start_battle() -> void:
	battle.reset()
	started = true
	busy = false
	paused = false
	selected_action = ""
	pending.clear()
	log_view.clear()
	title_overlay.hide()
	modal.hide()
	for fighter: Control in fighters.values(): fighter.state = "idle"
	refresh()

func actions() -> Array[String]:
	return ["attack",battle.unit_by_id(battle.current)["skill"],"potion","guard"]

func refresh() -> void:
	round_label.text = "ROUND %02d   /   我方 %d 人  ·  敵方 %d 人" % [battle.round_number,battle.living("party").size(),battle.living("enemy").size()]
	var order: Array[String] = [battle.unit_by_id(battle.current)["name"]]
	for id: String in battle.queue: order.append(battle.unit_by_id(id)["name"])
	order_label.text = "行動順序   " + "   →   ".join(order)
	for unit: Dictionary in battle.units:
		var fighter: Control = fighters[unit["id"]]
		fighter.active = unit["id"] == battle.current and not busy
		fighter.selected = not selected_action.is_empty() and (selected_target == unit["id"] or (selected_action == "wave" and unit["side"] == "enemy" and unit["hp"] > 0))
		fighter.get_meta("hp").value = unit["hp"]
		cards[unit["id"]].text = "%s%s\nHP %d / %d\nMP %d / %d" % [unit["name"]," ◈" if unit["guarding"] else "",unit["hp"],unit["max_hp"],unit["mp"],unit["max_mp"]]
	var is_party: bool = battle.unit_by_id(battle.current)["side"] == "party"
	command_box.visible = selected_action.is_empty()
	target_box.visible = not selected_action.is_empty()
	var list: Array[String] = actions()
	for i: int in range(commands.size()):
		var action: String = list[i]
		var skill: Dictionary = battle.skills[action]
		commands[i].text = str(skill["name"]) + ("  %d MP" % skill["cost"] if skill["cost"] > 0 else ("  ×%d" % battle.potions if action == "potion" else ""))
		commands[i].disabled = busy or not is_party or paused or not battle.available(action)
		commands[i].tooltip_text = skill["description"]
	message_label.text = "演出中…" if busy else ("%s，請選擇行動" % battle.unit_by_id(battle.current)["name"] if is_party else "敵方正在行動…")
	if selected_action.is_empty():
		preview_label.text = "防禦可減少傷害；藥水與治療只對受傷且存活的隊友有效。"
	if not busy and is_party and selected_action.is_empty() and started and not paused:
		commands[0].grab_focus()

func choose_command(index: int) -> void:
	if busy or paused or not started or not battle.outcome.is_empty(): return
	if battle.unit_by_id(battle.current)["side"] != "party": return
	var action: String = actions()[index]
	if not battle.available(action): return
	selected_action = action
	selected_target = battle.targets(action)[0]
	pending = battle.request(action,selected_target)
	refresh()
	update_targets()
	targets_buttons[0].grab_focus()

func update_targets() -> void:
	var list: Array[String] = battle.targets(selected_action)
	if battle.skills[selected_action]["target"] == "all_foes": list = [list[0]]
	for i: int in range(targets_buttons.size()):
		targets_buttons[i].visible = i < list.size()
		if i < list.size():
			targets_buttons[i].text = ("✓ " if list[i] == selected_target else "") + ("敵方全體" if selected_action == "wave" else battle.unit_by_id(list[i])["name"])
	var affected: Array[String] = []
	if selected_action == "wave": affected.assign(battle.targets(selected_action))
	else: affected.append(selected_target)
	var parts: Array[String] = []
	for id: String in affected:
		var target: Dictionary = battle.unit_by_id(id)
		parts.append("%s %s%d" % [target["name"],"+" if selected_action in ["heal","potion"] else "−",battle.amount(selected_action,battle.unit_by_id(battle.current),target)])
	preview_label.text = str(battle.skills[selected_action]["description"]) + "  /  " + ("自身進入防禦" if selected_action == "guard" else "   ·   ".join(parts))
	message_label.text = "選擇目標，再按「確認行動」；返回不消耗資源。"

func select_target_index(index: int) -> void:
	if busy or paused or selected_action.is_empty(): return
	var list: Array[String] = battle.targets(selected_action)
	if index >= list.size(): return
	selected_target = list[index]
	pending = battle.request(selected_action,selected_target)
	refresh()
	update_targets()
	confirm_button.grab_focus()

func cancel_selection() -> void:
	if busy or paused: return
	selected_action = ""
	selected_target = ""
	pending.clear()
	refresh()

func confirm_action() -> void:
	if busy or paused or pending.is_empty(): return
	perform(pending.duplicate())

func perform(command: Dictionary) -> void:
	if busy or paused: return
	var result: Dictionary = battle.submit(command)
	if not result["ok"]: return
	busy = true
	qa_actions += 1
	selected_action = ""
	selected_target = ""
	pending.clear()
	animation_left = 0.85
	var actor_name: String = battle.unit_by_id(command["actor"])["name"]
	log_view.append_text("%s · %s\n" % [actor_name,battle.skills[command["action"]]["name"]])
	fighters[command["actor"]].state = "attack"
	for event: Dictionary in result["events"]:
		if event["type"] in ["damage","heal","guard"]:
			var fighter: Control = fighters[event["target"]]
			if event["type"] == "damage": fighter.state = "hurt"
			var text: String = "防禦" if event["type"] == "guard" else ("+" if event["type"] == "heal" else "−") + str(event["amount"])
			var popup := label(text,37,"9bdebb" if event["type"] == "heal" else "ffe2ad")
			popup.position = fighter.position + Vector2(40,-12)
			popup.mouse_filter = Control.MOUSE_FILTER_IGNORE
			popup.add_to_group("popups")
			stage.add_child(popup)
			log_view.append_text("    %s %s\n" % [battle.unit_by_id(event["target"])["name"],text])
		elif event["type"] == "down":
			log_view.append_text("    %s 倒下\n" % battle.unit_by_id(event["target"])["name"])
	# Bound the UI log; the rules journal resets between battles.
	if log_view.get_line_count() > 90:
		var lines: PackedStringArray = log_view.text.split("\n")
		log_view.text = "\n".join(lines.slice(maxi(0,lines.size()-55)))
	play_tone(command["action"] in ["heal","potion"])
	refresh()

func play_tone(healing: bool) -> void:
	if volume <= 0: return
	var sound := AudioStreamWAV.new()
	sound.format = AudioStreamWAV.FORMAT_16_BITS
	sound.mix_rate = 22050
	var samples := PackedByteArray()
	samples.resize(4410)
	for i: int in range(2205):
		var wave: float = sin(TAU * (660.0 if healing else 180.0) * i / 22050.0) * (1.0-i/2205.0)
		samples.encode_s16(i*2,int(wave*6000))
	sound.data = samples
	audio_player.stream = sound
	audio_player.volume_db = linear_to_db(maxf(volume,0.001))
	audio_player.play()

func _process(delta: float) -> void:
	if not started or ui_test_mode: return
	if qa: record_qa()
	for fighter: Control in fighters.values():
		fighter.playback_speed = 0.0 if paused else speed
	if paused: return
	if busy:
		animation_left -= delta * speed
		for popup: Node in get_tree().get_nodes_in_group("popups"):
			popup.position.y -= delta * speed * 28
		if animation_left <= 0:
			busy = false
			for popup: Node in get_tree().get_nodes_in_group("popups"): popup.queue_free()
			for unit: Dictionary in battle.units: fighters[unit["id"]].state = "down" if unit["hp"] == 0 else "idle"
			refresh()
			if not battle.outcome.is_empty():
				if qa: qa_fights += 1; start_battle()
				else: show_result()
	elif battle.outcome.is_empty():
		if battle.unit_by_id(battle.current)["side"] == "enemy": perform(battle.enemy_command())
		elif qa and qa_seconds > 0: perform(auto_command())

func auto_command() -> Dictionary:
	if qa_variant == "defeat": return battle.request("guard",battle.current)
	var actor: Dictionary = battle.unit_by_id(battle.current)
	var injured: String = ""
	for id: String in battle.living("party"):
		var u: Dictionary = battle.unit_by_id(id)
		if u["hp"] <= u["max_hp"] * 0.6 and (injured.is_empty() or u["hp"] < battle.unit_by_id(injured)["hp"]): injured = id
	if not injured.is_empty():
		if actor["skill"] == "heal" and battle.available("heal"): return battle.request("heal",injured)
		if battle.unit_by_id(injured)["hp"] < 35 and battle.available("potion"): return battle.request("potion",injured)
	var action: String = actor["skill"] if actor["skill"] != "heal" and battle.available(actor["skill"]) else "attack"
	var list: Array[String] = battle.targets(action)
	var target: String = list[0]
	for id: String in list:
		if battle.unit_by_id(id)["hp"] < battle.unit_by_id(target)["hp"]: target = id
	return battle.request(action,target)

func modal_content() -> VBoxContainer:
	for child: Node in modal.get_children(): child.queue_free()
	var center := CenterContainer.new()
	modal.add_child(center)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation",20)
	center.add_child(column)
	modal.show()
	return column

func show_result() -> void:
	var column: VBoxContainer = modal_content()
	column.add_child(label("VICTORY" if battle.outcome == "victory" else "DEFEAT",28,"79cdd4"))
	column.add_child(label("試煉完成" if battle.outcome == "victory" else "再整隊出發",60,"f1d4a3"))
	column.add_child(label("回合 %d\n我方傷害 %d  /  敵方傷害 %d\n恢復 HP %d\n我方倒下 %d  /  敵方倒下 %d" % [battle.round_number,battle.totals["party_damage"],battle.totals["enemy_damage"],battle.totals["healing"],battle.totals["party_down"],battle.totals["enemy_down"]],30))
	var retry := button("再次挑戰",start_battle)
	column.add_child(retry)
	column.add_child(button("返回標題",func() -> void: started = false; modal.hide(); title_overlay.show(); start_button.grab_focus()))
	retry.grab_focus()

func show_settings() -> void:
	if modal.visible: return
	paused = true
	var column: VBoxContainer = modal_content()
	column.add_child(label("暫停 / 設定",48,"f1d4a3"))
	column.add_child(label("音效音量",26))
	var slider := HSlider.new()
	slider.custom_minimum_size = Vector2(650,45)
	slider.min_value = 0
	slider.max_value = 1
	slider.step = 0.05
	slider.value = volume
	slider.value_changed.connect(func(value: float) -> void: volume = value; save_settings())
	column.add_child(slider)
	var resolutions := OptionButton.new()
	resolutions.custom_minimum_size = Vector2(650,54)
	for text: String in ["1920 × 1080","2560 × 1440","3840 × 2160"]: resolutions.add_item(text)
	resolutions.select(resolution_index)
	resolutions.item_selected.connect(func(index: int) -> void:
		resolution_index = index
		get_window().size = [Vector2i(1920,1080),Vector2i(2560,1440),Vector2i(3840,2160)][index]
		save_settings())
	column.add_child(resolutions)
	column.add_child(button("切換演出速度 1× / 2×",toggle_speed))
	var resume := button("繼續",close_settings)
	column.add_child(resume)
	resume.grab_focus()

func close_settings() -> void:
	paused = false
	modal.hide()
	refresh()
	if not selected_action.is_empty(): update_targets(); confirm_button.grab_focus()

func toggle_speed() -> void:
	speed = 2.0 if speed == 1.0 else 1.0
	speed_button.text = "演出 %d×" % int(speed)
	save_settings()

func save_settings() -> void:
	if qa: return
	var config := ConfigFile.new()
	config.set_value("demo","volume",volume)
	config.set_value("demo","speed",speed)
	config.set_value("demo","resolution",resolution_index)
	config.save("user://battle_demo_settings.cfg")

func load_settings() -> void:
	if qa: return
	var config := ConfigFile.new()
	if config.load("user://battle_demo_settings.cfg") == OK:
		volume = clampf(float(config.get_value("demo","volume",0.35)),0,1)
		speed = 2.0 if config.get_value("demo","speed",1.0) == 2.0 else 1.0
		resolution_index = clampi(int(config.get_value("demo","resolution",0)),0,2)
		get_window().size = [Vector2i(1920,1080),Vector2i(2560,1440),Vector2i(3840,2160)][resolution_index]

func _unhandled_key_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		if paused: close_settings()
		elif not selected_action.is_empty(): cancel_selection()
		elif started and battle.outcome.is_empty(): show_settings()
		get_viewport().set_input_as_handled()

func record_qa() -> void:
	var now: int = Time.get_ticks_usec()
	var elapsed: float = (now-qa_started)/1000000.0
	if elapsed > 2: qa_frames.append((now-qa_last)/1000.0)
	qa_last = now
	if elapsed >= qa_next_sample:
		qa_samples.append({"seconds":elapsed,"static_bytes":Performance.get_monitor(Performance.MEMORY_STATIC),"video_bytes":Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED),"nodes":Performance.get_monitor(Performance.OBJECT_NODE_COUNT)})
		qa_next_sample += 10
	if not qa_shot and elapsed > 2 and (busy or battle.unit_by_id(battle.current)["side"] == "party"):
		if qa_variant == "selection" and not busy:
			choose_command(1)
		qa_shot = true
		capture_qa()
	if elapsed >= maxf(qa_seconds,4.0):
		set_process(false)
		qa_frames.sort()
		var sum_ms: float = 0.0
		for frame_ms: float in qa_frames: sum_ms += frame_ms
		var report := {"seconds":elapsed,"size":[qa_capture_size.x,qa_capture_size.y],"frames":qa_frames.size(),"mean_ms":sum_ms/maxi(qa_frames.size(),1),"p95_ms":qa_frames[int(qa_frames.size()*0.95)] if not qa_frames.is_empty() else 0,"max_ms":qa_frames[-1] if not qa_frames.is_empty() else 0,"samples":qa_samples,"actions":qa_actions,"battles":qa_fights,"speed":speed}
		var file := FileAccess.open(qa_path.path_join("report.json"),FileAccess.WRITE)
		file.store_string(JSON.stringify(report,"\t")); file.close()
		get_tree().quit()

func capture_qa() -> void:
	await RenderingServer.frame_post_draw
	var screenshot: Image = get_viewport().get_texture().get_image()
	qa_capture_size = screenshot.get_size()
	if qa_target.x > 0 and screenshot.get_size() != qa_target:
		push_error("QA render size mismatch: " + str(screenshot.get_size()))
		get_tree().quit(2)
		return
	screenshot.save_png(qa_path.path_join("screen.png"))
