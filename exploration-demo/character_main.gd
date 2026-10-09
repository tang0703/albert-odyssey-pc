extends "res://main.gd"
## Character entry shares the unchanged integer movement and scene package.
## Original pixels are local, preloaded and tied to independently checked sources.

const CharacterBundle = preload("res://character_loader.gd")
const AnimationModel = preload("res://character_animation_core.gd")
const SourceLayer = preload("res://character_layer.gd")
const PriorityShader = preload("res://character_priority.gdshader")

var character_bundle: Dictionary = {}
var character_override: Dictionary = {}
var animator: RefCounted
var animation_state: Dictionary = {}
var displayed_actor: Dictionary = {}
var presentation_queue: Array[Dictionary] = []
var display_delay: int = 0
var appearance_mode: String = "original"
var appearance_select: OptionButton
var animation_label: Label
var presentation_updates: int = 0
var source_layers: Dictionary = {}
var priority_material: ShaderMaterial

func _ready() -> void:
	var scene_directory: String = Bundle.default_directory()
	var character_directory: String = CharacterBundle.default_directory()
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--scene-package="): scene_directory = arg.trim_prefix("--scene-package=")
		if arg.begins_with("--character-package="): character_directory = arg.trim_prefix("--character-package=")
	if bundle_override.is_empty(): bundle_override = Bundle.load_bundle(scene_directory)
	if bundle_override.get("ok", false):
		var scene_pin: Variant = Bundle.read_json("res://bundle-pin.json")
		if not scene_pin is Dictionary:
			startup_error = "缺少場景釘選資料。"
		else:
			character_bundle = character_override if not character_override.is_empty() else CharacterBundle.load_bundle(character_directory, str(scene_pin.get("manifest_sha256", "")))
			if not character_bundle.get("ok", false):
				startup_error = str(character_bundle.get("error", "角色外觀包無法載入。"))
			else:
				animator = AnimationModel.new()
				var configured: Dictionary = animator.configure(character_bundle.profile, character_bundle.animation_bank, character_bundle.image_table)
				if not configured.get("ok", false): startup_error = str(configured.error)
				else: display_delay = int(character_bundle.presentation.actor_to_video_delay_updates)
	super._ready()
	if startup_error.is_empty():
		priority_material = ShaderMaterial.new()
		priority_material.shader = PriorityShader
		priority_material.set_shader_parameter("source_foreground", character_bundle.foreground_texture)
		var ordered: Dictionary = CharacterBundle.draw_order(character_bundle, displayed_actor, source_camera())
		if not ordered.get("ok", false):
			startup_error = str(ordered.get("error", "場景繪製順序未驗證。"))
			paused = true
		else:
			for entry: Dictionary in ordered.entries:
				var id: String = "player" if entry.kind == "player" else str(entry.id)
				var layer := SourceLayer.new()
				layer.name = id
				layer.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
				map_canvas.add_child(layer)
				source_layers[id] = layer
			map_canvas.resized.connect(sync_source_layers)
		refresh()

func build_ui() -> void:
	super.build_ui()
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 14)
	var side: Node = status_label.get_parent()
	side.add_child(row)
	side.move_child(row, 2)
	appearance_select = OptionButton.new()
	appearance_select.add_item("原作像素")
	appearance_select.add_item("診斷標記")
	appearance_select.custom_minimum_size = Vector2(190, 44)
	appearance_select.item_selected.connect(func(index: int) -> void: change_appearance("original" if index == 0 else "marker"))
	row.add_child(appearance_select)
	animation_label = make_label("", 19, "acc8c5")
	animation_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	animation_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	row.add_child(animation_label)
	if not startup_error.is_empty(): appearance_select.disabled = true

func prepare_update_presentation(result: Dictionary) -> String:
	if animator == null: return "角色動畫模型未載入。"
	var animated: Dictionary = animator.step_after_movement(animation_state, result)
	if not animated.get("ok", false): return str(animated.get("error", "動畫更新失敗。"))
	if not animated.diagnostics.applied: return ""
	var selected: Dictionary = CharacterBundle.lookup(character_bundle, animated.state)
	if not selected.get("ok", false): return str(selected.get("error", "缺少必要角色影格。"))
	# Animation never writes back to result.state, movement state or collisions.
	var incoming: Dictionary = result.state.duplicate(true)
	incoming.merge(animated.state, true)
	var next_display: Dictionary = incoming if presentation_queue.is_empty() else presentation_queue[0]
	var displayed_frame: Dictionary = CharacterBundle.lookup(character_bundle, next_display)
	if not displayed_frame.get("ok", false): return str(displayed_frame.get("error", "缺少排程中的必要角色影格。"))
	var ordered: Dictionary = CharacterBundle.draw_order(character_bundle, next_display, source_camera())
	if not ordered.get("ok", false): return str(ordered.get("error", "場景繪製順序未驗證。"))
	animation_state = animated.state
	presentation_queue.append(incoming)
	displayed_actor = presentation_queue.pop_front()
	presentation_updates += 1
	return ""

func reset_state() -> void:
	if animator != null and startup_error.is_empty():
		animation_state = animator.initial_state()
		displayed_actor = character_bundle.profile.initial_state.duplicate(true)
		presentation_queue.clear()
		for index: int in range(display_delay): presentation_queue.append(displayed_actor.duplicate(true))
		presentation_updates = 0
	super.reset_state()

func change_appearance(mode: String) -> void:
	if not startup_error.is_empty() or mode not in ["original", "marker"]: return
	appearance_mode = mode
	appearance_select.select(0 if mode == "original" else 1)
	refresh()

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		var key: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		if key == KEY_F2:
			change_appearance("marker" if appearance_mode == "original" else "original")
			get_viewport().set_input_as_handled()
			return
	super._input(event)

func refresh() -> void:
	super.refresh()
	sync_source_layers()
	if animation_label == null: return
	if animation_state.is_empty():
		animation_label.text = "必要角色資料尚未通過驗證。"
		return
	animation_label.text = "F2 切換 · 圖像 %d / 顯示 %d\n原作演出延遲 %d 次更新" % [int(animation_state.image_index), int(displayed_actor.image_index), display_delay]

func draw_player(canvas: Control, origin: Vector2, zoom: float) -> void:
	if appearance_mode == "marker":
		super.draw_player(canvas, origin, zoom)

func sync_source_layers() -> void:
	if source_layers.is_empty() or displayed_actor.is_empty() or not startup_error.is_empty(): return
	var selected: Dictionary = CharacterBundle.lookup(character_bundle, displayed_actor)
	if not selected.get("ok", false):
		startup_error = str(selected.get("error", "角色影格缺失。"))
		paused = true
		push_error(startup_error)
		return
	var ordered: Dictionary = CharacterBundle.draw_order(character_bundle, displayed_actor, source_camera())
	if not ordered.get("ok", false):
		startup_error = str(ordered.get("error", "場景繪製順序未驗證。"))
		paused = true
		push_error(startup_error)
		return
	var zoom: float = map_canvas.size.x / 320.0
	priority_material.set_shader_parameter("canvas_size", map_canvas.size)
	var camera := Vector2(float(bundle.data.camera[0]), float(bundle.data.camera[1]))
	for index: int in ordered.entries.size():
		var entry: Dictionary = ordered.entries[index]
		var player: bool = entry.kind == "player"
		var id: String = "player" if player else str(entry.id)
		var layer: Node2D = source_layers[id]
		if player and appearance_mode == "marker":
			layer.visible = false
			continue
		var frame: Dictionary = selected.frame if player else entry
		var image: Texture2D = selected.texture if player else entry.texture
		var world: Vector2 = world_position(displayed_actor) if player else Vector2(float(entry.world_xy_raw[0]), float(entry.world_xy_raw[1])) / 16.0
		var anchor: Array = frame.anchor
		var dimensions: Array = frame.dimensions
		var top_left: Vector2 = (world - camera - Vector2(float(anchor[0]), float(anchor[1]))) * zoom
		var sprite_priority: int = 2 if player else int(entry.sprite_priority)
		layer.show_sprite(image, Rect2(top_left, Vector2(float(dimensions[0]), float(dimensions[1])) * zoom), priority_material if sprite_priority == 2 else null, index)

func source_camera() -> Vector2:
	return Vector2(float(bundle.data.camera[0]), float(bundle.data.camera[1]))
