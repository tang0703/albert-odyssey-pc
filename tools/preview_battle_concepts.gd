extends SceneTree
## Static S2 scale proof in the real UI; deliberately not a combat build.

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var scene: PackedScene = load("res://main.tscn")
	var ui = scene.instantiate()
	ui.ui_test_mode = true
	root.size = Vector2i(1920, 1080)
	root.add_child(ui)
	await process_frame
	root.size = Vector2i(1920, 1080)
	ui.start_battle()
	ui.message_label.text = "S2 靜態造型打樣｜派克 × WEREDOG｜尚未製作動畫"
	ui.order_label.text = "造型比例預覽 — 三對三介面與另外四名角色保持原樣"
	var project: String = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var entries: Array[Dictionary] = [
		{"id":"guardian", "file":"pike-concept-v1.png", "name":"派克（打樣）", "scale":0.175},
		{"id":"scout", "file":"weredog-concept-v1.png", "name":"WEREDOG（打樣）", "scale":0.155},
	]
	for entry: Dictionary in entries:
		var original: Control = ui.fighters[entry["id"]]
		var drawing := Sprite2D.new()
		var path: String = project.path_join("art/concepts/round2/" + entry["file"])
		var bitmap := Image.load_from_file(path)
		if bitmap == null or bitmap.is_empty():
			push_error("Missing concept: " + path)
			quit(1)
			return
		drawing.texture = ImageTexture.create_from_image(bitmap)
		drawing.centered = false
		drawing.offset = -Vector2(bitmap.get_size()) * Vector2(0.5, 0.902)
		drawing.scale = Vector2(-float(entry["scale"]), float(entry["scale"]))
		drawing.position = original.position + Vector2(original.size.x * 0.5, original.size.y - 12)
		ui.stage.add_child(drawing)
		for child: Node in original.get_children():
			child.reparent(ui.stage, true)
			if child is Label: child.text = entry["name"]
		original.hide()
	for command: Button in ui.commands: command.disabled = true
	await process_frame
	await RenderingServer.frame_post_draw
	var screen: Image = root.get_texture().get_image()
	var output: String = project.path_join("reports/character-reference/concepts-in-game.png")
	DirAccess.make_dir_recursive_absolute(output.get_base_dir())
	if screen.get_size() != Vector2i(1920,1080) or screen.save_png(output) != OK:
		push_error("Concept preview screenshot failed")
		quit(1)
		return
	print("Concept preview saved: " + output)
	quit()
