extends SceneTree
## Static, real-GPU art review only. Never changes or rewrites source images.
## -- --art-dir=ABSOLUTE --output=ABSOLUTE.png --report=ABSOLUTE.json
const SceneBundle = preload("res://package_loader.gd")
const CharacterBundle = preload("res://character_loader.gd")
const SourceLayer = preload("res://character_layer.gd")
const PriorityShader = preload("res://character_priority.gdshader")
const DIRECTIONS: Array[String] = ["down", "left", "right", "up"]
const HEADINGS: Dictionary = {"down":2,"left":4,"right":0,"up":6}
const NAMES: Dictionary = {"down":"正面 / DOWN","left":"左側 / LEFT","right":"右側 / RIGHT","up":"背面 / UP"}
var args: Dictionary = {}
var report: Dictionary = {"schema":"ao_pc_character_art_review_v1","passed":false,
	"scope":"造型與遊戲內比例草稿；不是 52 幀定稿，也不是角色身份認定。",
	"source_images_modified":false,"animation_acceptance":false,"board_dimensions":[1920,1080]}
var scene: Dictionary = {}
var character: Dictionary = {}
var drafts: Dictionary = {}
var font: SystemFont

func _initialize() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--") and "=" in arg:
			var split: int = arg.find("=")
			args[arg.substr(2,split-2)] = arg.substr(split+1)
	call_deferred("run_review")

func fail(reason: String) -> void:
	report.error = reason
	write_report()
	push_error(reason)
	quit(1)

func write_report() -> bool:
	var path: String = str(args.get("report",""))
	if path.is_absolute_path():
		DirAccess.make_dir_recursive_absolute(path.get_base_dir())
		var file: FileAccess = FileAccess.open(path,FileAccess.WRITE)
		if file != null:
			file.store_string(JSON.stringify(report,"\t")+"\n")
			return file.get_error()==OK
	return false

func alpha_metrics(image: Image, source: bool) -> Dictionary:
	var pixels: PackedByteArray = image.get_data()
	var width: int = image.get_width()
	var height: int = image.get_height()
	var columns := PackedInt32Array()
	var rows := PackedInt32Array()
	columns.resize(width)
	rows.resize(height)
	var alpha_threshold: int = 1 if source else 128
	var transparent: int = 0
	for y: int in height:
		for x: int in width:
			var alpha: int = pixels[(y*width+x)*4+3]
			if alpha==0: transparent+=1
			if alpha>=alpha_threshold:
				columns[x]+=1
				rows[y]+=1
	var max_row: int = 0
	var max_column: int = 0
	for count: int in rows: max_row=maxi(max_row,count)
	for count: int in columns: max_column=maxi(max_column,count)
	var row_threshold: int = 1 if source else maxi(2,int(ceil(float(max_row)*0.005)))
	var column_threshold: int = 1 if source else maxi(2,int(ceil(float(max_column)*0.005)))
	var left: int = width
	var right: int = -1
	var top: int = height
	var bottom: int = -1
	for x: int in width:
		if columns[x]>=column_threshold:
			left=mini(left,x)
			right=x
	for y: int in height:
		if rows[y]>=row_threshold:
			top=mini(top,y)
			bottom=y
	if left>right or top>bottom:
		return {"ok":false,"error":"圖片沒有足夠的不透明角色像素。"}
	var band: int = maxi(1,int(ceil(float(bottom-top+1)*0.08)))
	var mass: float = 0.0
	var x_mass: float = 0.0
	for y: int in range(maxi(top,bottom-band+1),bottom+1):
		for x: int in range(left,right+1):
			var alpha: int = pixels[(y*width+x)*4+3]
			if alpha>=alpha_threshold:
				mass+=alpha
				x_mass+=(float(x)+0.5)*alpha
	if mass==0.0: return {"ok":false,"error":"找不到可計算的腳底區域。"}
	return {"ok":true,"bbox":[left,top,right+1,bottom+1],"bbox_height":bottom-top+1,
		"bbox_margins":[left,top,width-right-1,height-bottom-1],"touches_canvas_edge":left==0 or top==0 or right==width-1 or bottom==height-1,
		"feet_center":[x_mass/mass,bottom+1.0],"bottom_band_rows":band,
		"alpha_threshold":alpha_threshold,"row_min_pixels":row_threshold,"column_min_pixels":column_threshold,
		"transparent_pixels":transparent,"method":"alpha >= threshold; significant rows/columns; alpha-weighted X in bottom 8%, Y at exclusive bbox bottom"}

func label_at(parent: Node, text: String, rect: Rect2, size: int, color: Color = Color("dbe7e8"), centered: bool = false) -> Label:
	var label := Label.new()
	label.text=text
	label.position=rect.position
	label.size=rect.size
	label.add_theme_font_override("font",font)
	label.add_theme_font_size_override("font_size",size)
	label.add_theme_color_override("font_color",color)
	label.vertical_alignment=VERTICAL_ALIGNMENT_CENTER
	label.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER if centered else HORIZONTAL_ALIGNMENT_LEFT
	parent.add_child(label)
	return label

func panel(parent: Node, rect: Rect2, color: Color) -> ColorRect:
	var box := ColorRect.new()
	box.position=rect.position
	box.size=rect.size
	box.color=color
	parent.add_child(box)
	return box

func image_at(parent: Node, texture: Texture2D, rectangle: Rect2, nearest: bool) -> void:
	var node := TextureRect.new()
	node.expand_mode=TextureRect.EXPAND_IGNORE_SIZE
	node.texture=texture
	node.position=rectangle.position
	node.size=rectangle.size
	node.stretch_mode=TextureRect.STRETCH_SCALE
	node.texture_filter=CanvasItem.TEXTURE_FILTER_NEAREST if nearest else CanvasItem.TEXTURE_FILTER_LINEAR
	parent.add_child(node)

func add_guides(parent: Node, origin: Vector2, feet: Vector2, full_width: float) -> void:
	var overlay := Control.new()
	overlay.z_index=200
	overlay.draw.connect(func() -> void:
		overlay.draw_line(Vector2(0,feet.y),Vector2(full_width,feet.y),Color(1,0.79,0.39,0.7),1.5,true)
		overlay.draw_line(origin-Vector2(5,0),origin+Vector2(5,0),Color("63efe0"),1.0)
		overlay.draw_line(origin-Vector2(0,5),origin+Vector2(0,5),Color("63efe0"),1.0)
		overlay.draw_circle(feet,1.5,Color("ffd18a")))
	parent.add_child(overlay)

func scene_preview(parent: Node, rectangle: Rect2, draft: Dictionary) -> void:
	var canvas := Control.new()
	canvas.position=rectangle.position
	canvas.size=Vector2(320,224)
	canvas.scale=Vector2.ONE*(rectangle.size.x/320.0)
	canvas.clip_contents=true
	parent.add_child(canvas)
	for index: int in [1,0]: image_at(canvas,scene.textures[index],Rect2(0,0,320,224),true)
	var material := ShaderMaterial.new()
	material.shader=PriorityShader
	material.set_shader_parameter("source_foreground",character.foreground_texture)
	material.set_shader_parameter("canvas_size",Vector2(320,224))
	var actor: Dictionary = character.profile.initial_state
	var world := Vector2(float(actor.x_word),float(actor.y_word))/16.0
	var camera := Vector2(544,1536)
	var ordered: Dictionary = CharacterBundle.draw_order(character,actor,camera)
	for index: int in ordered.entries.size():
		var entry: Dictionary = ordered.entries[index]
		var player: bool = entry.kind=="player"
		var texture: Texture2D = draft.texture if player else entry.texture
		var origin: Vector2 = world-camera if player else Vector2(float(entry.world_xy_raw[0]),float(entry.world_xy_raw[1]))/16.0-camera
		var anchor: Vector2 = draft.anchor*float(draft.scale) if player else Vector2(float(entry.anchor[0]),float(entry.anchor[1]))
		var dimensions: Vector2 = Vector2(draft.image.get_size())*float(draft.scale) if player else Vector2(float(entry.dimensions[0]),float(entry.dimensions[1]))
		var layer := SourceLayer.new()
		layer.texture_filter=CanvasItem.TEXTURE_FILTER_LINEAR if player else CanvasItem.TEXTURE_FILTER_NEAREST
		canvas.add_child(layer)
		layer.show_sprite(texture,Rect2(origin-anchor,dimensions),material if player or int(entry.sprite_priority)==2 else null,index+1)
	var feet: Vector2 = world-camera+(draft.feet-draft.anchor)*float(draft.scale)
	add_guides(canvas,world-camera,feet,320.0)

func build_board(board: Control) -> void:
	panel(board,Rect2(0,0,1920,1080),Color("101b25"))
	label_at(board,"MAP001 / 首批角色造型審閱",Rect2(42,24,1600,54),37,Color("f1f4ef"))
	label_at(board,"四方向原作對照 · 相同場景、相同位置、固定鏡頭 · 造型與比例草稿，尚非 52 幀定稿",Rect2(44,80,1750,36),21,Color("a6bfca"))
	for index: int in DIRECTIONS.size():
		var direction: String = DIRECTIONS[index]
		var x: float = 42+float(index)*464
		var draft: Dictionary = drafts[direction]
		var original: Dictionary = draft.original
		panel(board,Rect2(x,138,444,862),Color("1a2b37"))
		label_at(board,NAMES[direction],Rect2(x+18,148,408,44),27,Color("eff4ed"),true)
		label_at(board,"原作像素",Rect2(x+12,202,206,32),20,Color("98bec4"),true)
		label_at(board,"HD 造型草稿",Rect2(x+226,202,206,32),20,Color("d8c294"),true)
		panel(board,Rect2(x+14,244,202,306),Color("263943"))
		panel(board,Rect2(x+228,244,202,306),Color("263943"))
		var zoom: float = minf(5.7,182.0/maxf(float(original.metrics.bbox[2]-original.metrics.bbox[0]),float(draft.metrics.bbox[2]-draft.metrics.bbox[0])*float(draft.scale)))
		var baseline: float = 504
		var source_origin := Vector2(x+115,baseline)
		var draft_origin := Vector2(x+329,baseline)
		var src_anchor := Vector2(float(original.frame.anchor[0]),float(original.frame.anchor[1]))
		image_at(board,original.texture,Rect2(source_origin-src_anchor*zoom,Vector2(32,40)*zoom),true)
		image_at(board,draft.texture,Rect2(draft_origin-draft.anchor*float(draft.scale)*zoom,Vector2(draft.image.get_size())*float(draft.scale)*zoom),false)
		var baseline_overlay := Control.new()
		baseline_overlay.position=Vector2(x+14,244)
		board.add_child(baseline_overlay)
		add_guides(baseline_overlay,source_origin-baseline_overlay.position,source_origin-baseline_overlay.position+(Vector2(float(original.metrics.feet_center[0]),float(original.metrics.feet_center[1]))-src_anchor)*zoom,202)
		var second_overlay := Control.new()
		second_overlay.position=Vector2(x+228,244)
		board.add_child(second_overlay)
		add_guides(second_overlay,draft_origin-second_overlay.position,draft_origin-second_overlay.position+(draft.feet-draft.anchor)*float(draft.scale)*zoom,202)
		label_at(board,"原作 %d px → 草稿 %.0f px 高" % [int(original.metrics.bbox_height),float(draft.target_height)],Rect2(x+14,564,416,30),20,Color("c4d4da"),true)
		label_at(board,"圖檔 %d × %d · 像素比例 %.5f" % [draft.image.get_width(),draft.image.get_height(),float(draft.scale)],Rect2(x+14,598,416,28),17,Color("96b0be"),true)
		label_at(board,"遊戲內比例 / 相同位置",Rect2(x+16,640,412,32),20,Color("e3e9df"))
		scene_preview(board,Rect2(x+16,684,412,288.4),draft)
	label_at(board,"青色十字：原作 actor origin　金線／點：不透明底部估算　｜　草稿錨點尚待逐幀人工確認；NPC、反射／陰影不在本次範圍。",Rect2(44,1010,1830,38),19,Color("a9c3cc"))

func run_review() -> void:
	for key: String in ["art-dir","output","report"]:
		if not str(args.get(key,"")).is_absolute_path():
			fail("必要 CLI 路徑須為絕對路徑：--"+key)
			return
	if DisplayServer.get_name()=="headless":
		fail("造型審閱板須使用實際 GPU；不可用 --headless 代替畫面驗收。")
		return
	if str(args.output).get_extension().to_lower()!="png" or str(args.report).get_extension().to_lower()!="json":
		fail("--output 必須是 PNG，--report 必須是 JSON。")
		return
	var scene_pin: Variant = SceneBundle.read_json("res://bundle-pin.json")
	if not scene_pin is Dictionary:
		fail("缺少核准場景 pin。")
		return
	scene=SceneBundle.load_bundle(SceneBundle.default_directory())
	if not scene.get("ok",false):
		fail(str(scene.get("error","場景包無法載入。")))
		return
	character=CharacterBundle.load_bundle(CharacterBundle.default_directory(),str(scene_pin.manifest_sha256))
	if not character.get("ok",false):
		fail(str(character.get("error","角色包無法載入。")))
		return
	var ordered: Dictionary = CharacterBundle.draw_order(character,character.profile.initial_state)
	if not ordered.get("ok",false):
		fail(str(ordered.error))
		return
	var rows: Array[Dictionary] = []
	for direction: String in DIRECTIONS:
		var path: String = str(args["art-dir"]).path_join(direction+".png")
		if not FileAccess.file_exists(path):
			fail("缺少方向草稿圖片："+path)
			return
		if path.simplify_path().to_lower()==str(args.output).simplify_path().to_lower() or path.simplify_path().to_lower()==str(args.report).simplify_path().to_lower():
			fail("輸出不得覆寫輸入圖片。")
			return
		var image := Image.new()
		var raw: PackedByteArray = FileAccess.get_file_as_bytes(path)
		if image.load_png_from_buffer(raw)!=OK or image.get_width()<2 or image.get_height()<2 or image.get_width()>8192 or image.get_height()>8192:
			fail("草稿不是支援尺寸的 PNG："+path)
			return
		image.convert(Image.FORMAT_RGBA8)
		var metrics: Dictionary = alpha_metrics(image,false)
		if not metrics.get("ok",false) or int(metrics.get("transparent_pixels",0))==0:
			fail("草稿必須具有透明背景與非空角色："+path)
			return
		var key: String = "%d:0" % int(HEADINGS[direction])
		var original: Dictionary = {"frame":character.frames[key],"texture":character.textures[key],"metrics":alpha_metrics(character.images[key],true)}
		var source_feet := Vector2(float(original.metrics.feet_center[0]),float(original.metrics.feet_center[1]))
		var source_anchor := Vector2(float(original.frame.anchor[0]),float(original.frame.anchor[1]))
		var feet := Vector2(float(metrics.feet_center[0]),float(metrics.feet_center[1]))
		var target_height: float = clampf(float(original.metrics.bbox_height),36.0,38.0)
		var scale_factor: float = target_height/float(metrics.bbox_height)
		var anchor: Vector2 = feet-(source_feet-source_anchor)/scale_factor
		drafts[direction]={"image":image,"texture":ImageTexture.create_from_image(image),"metrics":metrics,"feet":feet,
			"anchor":anchor,"scale":scale_factor,"target_height":target_height,"original":original}
		rows.append({"direction":direction,"input":{"path":path,"bytes":raw.size(),"sha256":FileAccess.get_sha256(path),"dimensions":[image.get_width(),image.get_height()]},
			"alpha_measurement":metrics,"scale_source_pixels_per_image_pixel":scale_factor,"display_bbox_height_source_pixels":target_height,
			"preview_anchor_image_pixels":[anchor.x,anchor.y],"original":{"frame":original.frame,"alpha_measurement":original.metrics,
				"identity":character.data.files[original.frame.file],"scale_source_pixels_per_image_pixel":1.0},
			"anchor_method":"HD feet - (source feet - source anchor) / scale; heuristic for review only"})
	font=SystemFont.new()
	font.font_names=PackedStringArray(["Microsoft JhengHei","Noto Sans CJK TC","sans-serif"])
	var viewport := SubViewport.new()
	viewport.size=Vector2i(1920,1080)
	viewport.disable_3d=true
	viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var board := Control.new()
	board.size=Vector2(1920,1080)
	viewport.add_child(board)
	build_board(board)
	for frame: int in 4:
		await process_frame
		await RenderingServer.frame_post_draw
	var screenshot: Image = viewport.get_texture().get_image()
	DirAccess.make_dir_recursive_absolute(str(args.output).get_base_dir())
	if screenshot.get_size()!=Vector2i(1920,1080) or screenshot.save_png(str(args.output))!=OK:
		fail("無法儲存 1920×1080 GPU 審閱板。")
		return
	for row: Dictionary in rows:
		if FileAccess.get_sha256(row.input.path)!=row.input.sha256:
			fail("審閱期間輸入圖片發生變更："+str(row.input.path))
			return
	var character_pin: Dictionary = SceneBundle.read_json("res://character-pin.json")
	report.merge({"passed":true,"renderer":RenderingServer.get_current_rendering_method(),"display_server":DisplayServer.get_name(),
		"output":{"path":args.output,"sha256":FileAccess.get_sha256(args.output),"bytes":FileAccess.get_file_as_bytes(args.output).size()},"inputs":rows,
		"review_script_sha256":FileAccess.get_sha256(ProjectSettings.globalize_path("res://character_art_review.gd")),
		"scene_manifest_sha256":scene_pin.manifest_sha256,"character_manifest_sha256":character_pin.manifest_sha256,
		"camera":[544,1536],"viewport":[320,224],"world_position_source_pixels":[718,1626],
		"world_position_source":"pinned initial actor state; no movement performed",
		"draw_order":ordered.placements,"source_renderer":"character_layer.gd + character_priority.gdshader",
		"scale_method":"clamp(source idle alpha bbox height,36,38) / draft significant-alpha bbox height",
		"limitations":["錨點由底部像素估算，並非已確認腳部解剖或正式動畫錨點。","原作角色身份未命名。","草稿顯示採線性濾鏡；原作與背景採最近鄰。","背景遮擋遵循來源優先度，HD 半透明邊緣是草稿演出，未做原作逐像素相等驗收。","原作 NPC／物件 6、7 與反射陰影仍省略。"]},true)
	if not write_report():
		push_error("審閱圖已產生，但 JSON 報告無法寫入。")
		quit(1)
		return
	print("CHARACTER_ART_REVIEW_PASSED "+str(args.output))
	quit(0)
