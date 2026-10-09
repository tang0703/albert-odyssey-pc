extends SceneTree
const Common = preload("res://package_loader.gd")
var report_path: String = ""
var fixture_path: String = ""
var failures: Array[String] = []
var rows: Array[Dictionary] = []

func _initialize() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--report="): report_path=arg.trim_prefix("--report=")
		if arg.begins_with("--fixtures="): fixture_path=arg.trim_prefix("--fixtures=")
	if DisplayServer.get_name()=="headless": push_error("Real Compatibility renderer required");quit(1);return
	call_deferred("run")

func run() -> void:
	var fixture: Variant = Common.read_json(fixture_path)
	if not fixture is Dictionary or fixture.get("schema")!="ao_room_gpu_fixtures_v1": failures.append("Missing source fixtures");finish();return
	var ui: Control = load("res://room_main.tscn").instantiate()
	ui.ui_test_mode=true
	root.add_child(ui)
	await process_frame
	if not ui.startup_error.is_empty(): failures.append(ui.startup_error);ui.queue_free();await process_frame;finish();return
	ui.change_appearance("original");ui.show_overlay=false
	var viewport := SubViewport.new()
	viewport.size=Vector2i(320,224);viewport.disable_3d=true
	viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS
	viewport.canvas_item_default_texture_filter=Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_NEAREST
	root.add_child(viewport)
	ui.map_canvas.reparent(viewport)
	ui.map_canvas.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	ui.map_canvas.position=Vector2.ZERO;ui.map_canvas.size=Vector2(320,224)
	for row: Dictionary in fixture.cases:
		if FileAccess.get_sha256(row.expected)!=row.expected_sha256 or FileAccess.get_sha256(row.mask)!=row.mask_sha256: failures.append("Source PNG changed");break
		ui.select_route(int(row.route))
		for n: int in int(row.updates): ui.single_step()
		if not ui.startup_error.is_empty(): failures.append(ui.startup_error);break
		ui.map_canvas.size=Vector2(320,224)
		ui.refresh()
		await process_frame
		await RenderingServer.frame_post_draw
		var actual: Image = viewport.get_texture().get_image()
		actual.convert(Image.FORMAT_RGBA8)
		var expected: Image = Image.load_from_file(row.expected)
		var mask: Image = Image.load_from_file(row.mask)
		var compared: int=0
		var differences: int=0
		var first: Array=[]
		for y: int in 224:
			for x: int in 320:
				if mask.get_pixel(x,y).a==0:continue
				compared+=1
				if actual.get_pixel(x,y).to_rgba32()!=expected.get_pixel(x,y).to_rgba32():
					differences+=1
					if first.size()<4:first.append([x,y,actual.get_pixel(x,y).to_rgba32(),expected.get_pixel(x,y).to_rgba32()])
		rows.append({"id":row.id,"compared":compared,"differences":differences,"first":first})
		if differences:
			failures.append("GPU pixels differ: "+str(row.id))
			actual.save_png(report_path.get_base_dir().path_join(row.id+"-actual.png"))
			break
	ui.queue_free();viewport.queue_free();await process_frame
	finish()

func finish() -> void:
	var report: Dictionary={"schema":"ao_room_gpu_validation_v1","passed":failures.is_empty(),"renderer":RenderingServer.get_video_adapter_name(),"cases":rows,"failures":failures}
	var file := FileAccess.open(report_path,FileAccess.WRITE)
	if file!=null:file.store_string(JSON.stringify(report,"  ")+"\n")
	print(JSON.stringify(report));quit(0 if failures.is_empty() else 1)
