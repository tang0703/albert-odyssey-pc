extends Node2D
var data: Dictionary
var mode: String
var images: Dictionary = {}
var font := SystemFont.new()

func _ready() -> void:
	font.font_names = PackedStringArray(["Microsoft JhengHei","Arial"])
	for name: String in data.art: images[name] = texture(data.art[name].path)
	for name: String in ["player","player_room","source_background","source_laia"]: images[name] = texture(data[name].path)
	queue_redraw()

func texture(path: String) -> Texture2D:
	var image := Image.new()
	if image.load(path) != OK: push_error("Review texture missing: "+path)
	return ImageTexture.create_from_image(image)

func label(text: String, point: Vector2, size: int=24, color: Color=Color("dce6e6")) -> void:
	draw_string(font,point,text,HORIZONTAL_ALIGNMENT_LEFT,-1,size,color)

func region(meta: Dictionary) -> Rect2:
	var b: Array = meta.box
	return Rect2(b[0],b[1],b[2]-b[0],b[3]-b[1])

func figure(name: String, foot: Vector2, height: float) -> void:
	var meta: Dictionary = data[name] if name.begins_with("player") else data.art[name]
	var r: Rect2 = region(meta)
	var size := r.size*(height/r.size.y)
	var anchor := Vector2(float(meta.foot[0])-r.position.x,float(meta.foot[1])-r.position.y)*(height/r.size.y)
	draw_texture_rect_region(images[name],Rect2(foot-anchor,size),r)
	draw_line(foot-Vector2(18,0),foot+Vector2(18,0),Color("efc56b"),1)

func shell(origin: Vector2, zoom: float) -> void:
	var s: Dictionary = data.layout.shell
	var tex: Texture2D = images[s.file]
	var uv := tex.get_size()/Vector2(448,256)
	for y: int in s.source_y.size()-1:
		for x: int in s.source_x.size()-1:
			var target := Rect2(Vector2(s.source_x[x],s.source_y[y]),Vector2(s.source_x[x+1]-s.source_x[x],s.source_y[y+1]-s.source_y[y]))
			var source := Rect2(Vector2(s.art_x[x],s.art_y[y])*uv,Vector2(s.art_x[x+1]-s.art_x[x],s.art_y[y+1]-s.art_y[y])*uv)
			draw_texture_rect_region(tex,Rect2(origin+target.position*zoom,target.size*zoom),source)

func _draw() -> void:
	draw_rect(Rect2(0,0,1920,1080),Color("101b22"))
	label("MAP001 / 樓下與 LAIA · 2.5D 美術審閱",Vector2(40,58),36)
	label("W2 審閱稿｜非遊戲驗收｜未製作 52 幀｜效能未驗收",Vector2(40,100),22,Color("b0c2c5"))
	if mode == "directions":
		var dirs: Array[String] = ["down","left","right","up"]
		var names: Array[String] = ["正面 / 下","左側","右側","背面 / 上"]
		for i: int in 4:
			var x := 205.0+i*370
			draw_rect(Rect2(x-175,150,350,720),Color("192b34"))
			figure("laia-"+dirs[i]+"-01.png",Vector2(x,780),480)
			label(names[i],Vector2(x-85,210),28)
			label("36 世界單位",Vector2(x-85,840),22)
		figure("player",Vector2(1720,780),480)
		label("既有玩家",Vector2(1630,210),28)
		label("同高度比較",Vector2(1630,840),22)
		label("淡紫髮、白羽翼、粉紫服裝沿用來源辨識；眼色、金邊、鞋款及正面細節為重繪詮釋。",Vector2(40,946),25)
		label("原作未使用的方向只作美術預覽；LAIA 行走週期為 48 更新，玩家維持 40 更新。",Vector2(40,998),25)
		return
	var zoom := 3.28
	var origin := Vector2(30,145)
	shell(origin,zoom)
	var layers: Array = data.layout.layers.duplicate(true)
	for name: String in ["player","laia"]:
		var p: Array = data.sample_positions[name]
		layers.append({"id":name,"depth":p[1],"character":true})
	layers.sort_custom(func(a: Dictionary,b: Dictionary) -> bool: return float(a.depth)<float(b.depth))
	for row: Dictionary in layers:
		if row.get("character",false):
			var p: Array = data.sample_positions[row.id]
			figure("player_room" if row.id=="player" else "laia-right-01.png",origin+Vector2(p[0],p[1])*zoom,36*zoom)
		else:
			var a: Array = row.rect
			var box := Rect2(Vector2(a[0],a[1]),Vector2(a[2],a[3]))
			var r: Rect2 = region(data.art[row.file])
			if row.preserve:
				var size := r.size*minf(box.size.x/r.size.x,box.size.y/r.size.y)
				box.position += Vector2((box.size.x-size.x)/2,box.size.y-size.y); box.size = size
			draw_texture_rect_region(images[row.file],Rect2(origin+box.position*zoom,box.size*zoom),r)
	if mode == "alignment":
		for value: Variant in data.cells:
			var p := Vector2((int(value)%256)*8-512,(int(value)/256)*8-1792)
			draw_rect(Rect2(origin+p*zoom,Vector2(8,8)*zoom),Color(0.2,1,0.8,0.6),false,1)
		for key: String in ["player","laia"]:
			var line := PackedVector2Array()
			for p: Array in data.routes[1][key]: line.append(origin+Vector2(p[0],p[1])*zoom)
			if line.size()>1: draw_polyline(line,Color("ffd76a") if key=="player" else Color("ff95e0"),2)
	label("原作位置參照",Vector2(1530,160),26)
	draw_texture_rect(images.source_background,Rect2(1530,180,358,205),false)
	label("玩家 / LAIA 同框比例",Vector2(1530,440),23)
	figure("player",Vector2(1610,665),170)
	figure("laia-down-01.png",Vector2(1800,665),170)
	label("兩者均 36 世界單位",Vector2(1530,705),22)
	label("只替換外觀與構圖",Vector2(1530,780),22)
	label("不增加可走範圍",Vector2(1530,818),22)
	label("蒸氣逐幀與遮擋待 W3",Vector2(1530,880),22)
	label("椅子背面仍需修整",Vector2(1530,918),22)
	label("人物座標取既有事件樣本；青格為 98 個查表覆蓋，金線為玩家路徑，粉線為 LAIA 路徑。",Vector2(40,1030),22)
