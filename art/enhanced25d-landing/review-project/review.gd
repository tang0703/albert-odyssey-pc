extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var pc_root: String = ProjectSettings.globalize_path("res://../../..")
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(pc_root.path_join("reports/enhanced25d-landing/review-data.json")))
	if not data is Dictionary or data.get("runtime_approved",true): push_error("Missing unapproved art review data"); quit(1); return
	var mode := "room"
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--review="): mode = arg.trim_prefix("--review=")
	if mode not in ["room","directions","alignment"]: push_error("Unknown review mode"); quit(1); return
	root.size = Vector2i(1920,1080)
	var canvas: Node2D = load("res://canvas.gd").new()
	canvas.data = data; canvas.mode = mode; root.add_child(canvas)
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var output: String = pc_root.path_join("reports/enhanced25d-landing/"+mode+"-review.png")
	var result: Error = root.get_texture().get_image().save_png(output)
	print(JSON.stringify({"mode":mode,"saved":result==OK,"art_review_only":true,"performance_tested":false,"output":output}))
	quit(0 if result==OK else 1)
