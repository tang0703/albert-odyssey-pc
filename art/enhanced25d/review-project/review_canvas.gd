extends Node2D
var data: Dictionary
var mode: String
var textures: Dictionary = {}
var font: SystemFont
const INK = Color(0.88,0.91,0.88)
const MUTED = Color(0.58,0.68,0.7)
const GOLD = Color(0.93,0.73,0.42)

func _ready() -> void:
	font = SystemFont.new(); font.font_names = PackedStringArray(["Microsoft JhengHei UI","Microsoft JhengHei"])
	for name: String in data.textures: textures[name] = texture(data.textures[name])
	textures["source"] = texture(data.source_background)
	for prop: Dictionary in data.source_props: textures["source-prop-"+str(prop.slot)] = texture(prop.texture)
	queue_redraw()

func texture(record: Dictionary) -> ImageTexture:
	if FileAccess.get_sha256(record.file) != record.sha256: push_error("Changed review image: "+str(record.file)); get_tree().quit(1)
	var image: Image = Image.load_from_file(record.file)
	return ImageTexture.create_from_image(image)

func label_at(text: String, point: Vector2, size: int=20, color: Color=INK) -> void:
	draw_string(font,point,text,HORIZONTAL_ALIGNMENT_LEFT,-1,size,color)

func rectangle(values: Array) -> Rect2:
	return Rect2(float(values[0]),float(values[1]),float(values[2]),float(values[3]))

func crop(values: Array) -> Rect2:
	return Rect2(float(values[0]),float(values[1]),float(values[2]-values[0]),float(values[3]-values[1]))

func fit_region(name: String, target: Rect2, preserve: bool=false) -> void:
	var source: Rect2 = crop(data.textures[name].visible_box)
	var dest: Rect2 = target
	if preserve:
		var zoom: float = minf(target.size.x/source.size.x,target.size.y/source.size.y)
		dest.size = source.size*zoom
		dest.position += Vector2((target.size.x-dest.size.x)/2,target.size.y-dest.size.y)
	draw_texture_rect_region(textures[name],dest,source)

func at_world(local: Vector2, area: Rect2) -> Vector2:
	return area.position + local*area.size.x/448.0

func world_rect(values: Array, area: Rect2) -> Rect2:
	return Rect2(at_world(Vector2(values[0],values[1]),area),Vector2(values[2],values[3])*area.size.x/448.0)

func draw_shell(area: Rect2) -> void:
	var shell: Dictionary = data.layout.shell
	var tex: Texture2D = textures[shell.file]
	var uv_scale: Vector2 = tex.get_size()/Vector2(448,256)
	for iy: int in shell.source_y.size()-1:
		for ix: int in shell.source_x.size()-1:
			var target := Rect2(Vector2(shell.source_x[ix],shell.source_y[iy]),Vector2(shell.source_x[ix+1]-shell.source_x[ix],shell.source_y[iy+1]-shell.source_y[iy]))
			var source := Rect2(Vector2(shell.art_x[ix],shell.art_y[iy])*uv_scale,Vector2(shell.art_x[ix+1]-shell.art_x[ix],shell.art_y[iy+1]-shell.art_y[iy])*uv_scale)
			draw_texture_rect_region(tex,Rect2(at_world(target.position,area),target.size*area.size.x/448.0),source)

func draw_actor(direction: String, foot: Vector2, height: float, cross: bool=false) -> void:
	var name: String = direction+"-idle-01.png"
	var source: Rect2 = crop(data.textures[name].visible_box)
	var size: Vector2 = source.size*height/source.size.y
	# Contact ellipse is a declared new visual effect, not a source shadow.
	var points := PackedVector2Array()
	for n: int in 32: points.append(foot+Vector2(cos(n*TAU/32)*size.x*0.26,sin(n*TAU/32)*height*0.025))
	draw_colored_polygon(points,Color(0,0,0,0.20))
	draw_texture_rect_region(textures[name],Rect2(foot-Vector2(size.x/2,size.y),size),source)
	if cross:
		draw_line(foot-Vector2(13,0),foot+Vector2(13,0),GOLD,2)
		draw_line(foot-Vector2(0,8),foot+Vector2(0,8),GOLD,2)

func draw_room(area: Rect2, overlay: bool=false) -> void:
	draw_shell(area)
	for row: Dictionary in data.layout.layers:
		if row.plane == "floor": fit_region(row.file,world_rect(row.rect,area))
	var items: Array = []
	for row: Dictionary in data.layout.layers:
		if row.plane != "floor": items.append(row)
	var foot := Vector2(data.layout.character_review_anchor_world[0]-512,data.layout.character_review_anchor_world[1]-1536)
	items.append({"id":"review_player","depth":foot.y})
	for prop: Dictionary in data.source_props:
		if prop.slot in data.layout.source_sprite_slots_in_review: items.append({"id":"source_prop","depth":float(prop.world_xy_raw[1])/16-1536,"prop":prop})
	items.sort_custom(func(a: Dictionary,b: Dictionary) -> bool: return a.depth < b.depth)
	for row: Dictionary in items:
		if row.id == "review_player": draw_actor("down",at_world(foot,area),data.review_height_world*area.size.x/448.0,overlay)
		elif row.id == "source_prop":
			var p: Dictionary = row.prop
			var point := Vector2(float(p.world_xy_raw[0])/16-512-p.anchor[0],float(p.world_xy_raw[1])/16-1536-p.anchor[1])
			var tex: Texture2D = textures["source-prop-"+str(p.slot)]
			draw_texture_rect(tex,Rect2(at_world(point,area),tex.get_size()*area.size.x/448.0),false)
		else: fit_region(row.file,world_rect(row.rect,area),row.id.begins_with("chair"))
	if overlay: draw_overlay(area)

func draw_overlay(area: Rect2) -> void:
	for index: int in data.verified_query_indices:
		var point := Vector2((index%256)*8-512,(index/256)*8-1536)
		if point.x >= 0 and point.y >= 0 and point.x < 448 and point.y < 256:
			draw_rect(Rect2(at_world(point,area),Vector2(8,8)*area.size.x/448.0),Color(0.2,0.9,0.8,0.20),false,1)
	var colors: Array[Color] = [Color(1,0.7,0.2,0.7),Color(0.3,0.95,0.8,0.7),Color(0.6,0.65,1,0.7),Color(1,0.5,0.6,0.7),Color(0.9,0.9,0.5,0.7)]
	for i: int in data.routes.size():
		var points := PackedVector2Array()
		for value: Array in data.routes[i].points: points.append(at_world(Vector2(value[0],value[1]),area))
		if points.size()>1: draw_polyline(points,colors[i%colors.size()],1)
	# Exact source interaction rectangle, never moved to fit artwork.
	var interaction := Rect2(Vector2(11856.0/16-512,27376.0/16-1536),Vector2((12208-11856)/16.0,(27648-27376)/16.0))
	draw_rect(Rect2(at_world(interaction.position,area),interaction.size*area.size.x/448.0),Color(1,0.3,0.2),false,2)

func _draw() -> void:
	if font == null: return
	draw_rect(Rect2(0,0,1920,1080),Color(0.04,0.055,0.065))
	label_at("MAP001  /  2.5D 起始房間",Vector2(48,65),34)
	label_at("美術審閱稿 · 不代表遊戲整合或效能驗收通過",Vector2(48,104),20,MUTED)
	if mode == "directions":
		var directions: Array[String] = ["down","left","right","up"]
		var captions: Array[String] = ["正面 / DOWN","左向 / LEFT","右向 / RIGHT","背面 / UP"]
		for i: int in 4:
			var x: float = 255+i*470
			draw_rect(Rect2(x-215,160,430,800),Color(0.075,0.095,0.105))
			draw_actor(directions[i],Vector2(x,900),650,true)
			label_at(captions[i],Vector2(x-100,210),23,GOLD)
		label_at("核對：比例、髮型、羽飾左右側、服裝與光源。四向核准後才製作 52 幀；本圖未表示行走動畫已完成。",Vector2(48,1025),22)
	elif mode == "alignment":
		var left := Rect2(32,230,896,512)
		var right := Rect2(992,230,896,512)
		draw_texture_rect(textures.source,left,false); draw_overlay(left)
		draw_room(right,true)
		label_at("來源底圖與既有軌跡",Vector2(32,196),26,GOLD)
		label_at("新圖層與相同世界座標",Vector2(992,196),26,GOLD)
		label_at("青格＝已驗證查表聯集；彩線＝既有五條路線；紅框＝Cirrus 互動範圍。",Vector2(48,840),24)
		label_at("格線不是通用障礙遮罩；此預覽不修改碰撞。家具遮擋與局部對位仍須後續正式驗收。",Vector2(48,890),22,MUTED)
		label_at("原作像素參照只留本地。",Vector2(48,1025),20,MUTED)
	else:
		draw_room(Rect2(32,160,1456,832))
		label_at("四方向 · 同一腳底基準",Vector2(1520,195),23,GOLD)
		for i: int in 4:
			var d: String = ["down","left","right","up"][i]
			draw_actor(d,Vector2(1630+(i%2)*180,450+(i/2)*310),220,true)
		label_at("角色高度：36 世界單位",Vector2(1520,840),20)
		label_at("背景、床、地毯、桌椅分層",Vector2(1520,880),19,MUTED)
		label_at("Cirrus 與凳子暫用來源參照",Vector2(1520,915),19,MUTED)
		label_at("尚未接入行走及事件演出",Vector2(1520,950),19,MUTED)
		label_at("畫面使用原作世界座標；全房間固定構圖只改演出。其他房間及 LAIA 事件沿用目前版本。",Vector2(48,1040),21)
