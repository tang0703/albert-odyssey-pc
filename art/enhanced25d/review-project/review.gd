extends SceneTree
var canvas: Node2D

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var pc_root: String = ProjectSettings.globalize_path("res://../../..")
	var report_path: String = pc_root.path_join("reports/enhanced25d/review-data.json")
	if not FileAccess.file_exists(report_path): push_error("Run prepare_enhanced25d_review.py first"); quit(1); return
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(report_path))
	if not data is Dictionary or data.get("runtime_approved",true): push_error("Unapproved art review contract"); quit(1); return
	var mode: String = "room"
	var output_dir: String = pc_root.path_join("reports/enhanced25d")
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--review="): mode = arg.trim_prefix("--review=")
		if arg.begins_with("--output-dir="): output_dir = arg.trim_prefix("--output-dir=")
	if mode not in ["room","directions","alignment"]: push_error("Unknown review mode"); quit(1); return
	root.size = Vector2i(1920,1080)
	canvas = load("res://review_canvas.gd").new()
	canvas.data = data; canvas.mode = mode
	root.add_child(canvas)
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var output: String = output_dir.path_join(mode+"-review.png")
	var result: Error = root.get_texture().get_image().save_png(output)
	print(JSON.stringify({"art_review_only":true,"mode":mode,"output":output,"saved":result==OK,"performance_tested":false}))
	quit(0 if result==OK else 1)
