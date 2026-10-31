extends RefCounted
## Presentation only. All positions come from the existing displayed sample.
const HD = preload("res://character_hd_animation.gd")
const ORIGIN = Vector2(512,1536)

static func rectangle(a: Array) -> Rect2:
	return Rect2(float(a[0]),float(a[1]),float(a[2]),float(a[3]))

static func draw_shell(c: Control, art: Dictionary, offset: Vector2, zoom: float, clip: Rect2 = Rect2(0,0,448,256)) -> void:
	var shell: Dictionary = art.data.layout.shell
	var tex: Texture2D = art.textures[shell.file]
	var uv := tex.get_size()/Vector2(448,256)
	for y: int in shell.source_y.size()-1:
		for x: int in shell.source_x.size()-1:
			var target := Rect2(Vector2(shell.source_x[x],shell.source_y[y]),Vector2(shell.source_x[x+1]-shell.source_x[x],shell.source_y[y+1]-shell.source_y[y]))
			var clipped := target.intersection(clip)
			if not clipped.has_area(): continue
			var source := Rect2(Vector2(shell.art_x[x],shell.art_y[y])*uv,Vector2(shell.art_x[x+1]-shell.art_x[x],shell.art_y[y+1]-shell.art_y[y])*uv)
			var sub := Rect2(source.position+(clipped.position-target.position)/target.size*source.size,clipped.size/target.size*source.size)
			c.draw_texture_rect_region(tex,Rect2(offset+clipped.position*zoom,clipped.size*zoom),sub)

static func draw_art(c: Control, art: Dictionary, name: String, local: Rect2, offset: Vector2, zoom: float, preserve: bool=false) -> void:
	var b: Array = art.data.textures[name].visible_box
	var region := Rect2(b[0],b[1],b[2]-b[0],b[3]-b[1])
	var target: Rect2 = local
	if preserve:
		var size := region.size*minf(target.size.x/region.size.x,target.size.y/region.size.y)
		target.position += Vector2((target.size.x-size.x)/2,target.size.y-size.y); target.size = size
	c.draw_texture_rect_region(art.textures[name],Rect2(offset+target.position*zoom,target.size*zoom),region)

static func draw(c: Control, owner: Control, art: Dictionary) -> String:
	var zoom: float = minf(c.size.x/448.0,c.size.y/256.0)
	var offset := (c.size-Vector2(448,256)*zoom)/2
	c.draw_rect(Rect2(Vector2.ZERO,c.size),Color("101618"))
	draw_shell(c,art,offset,zoom)
	var items: Array[Dictionary] = []
	for layer: Dictionary in art.data.layout.layers:
		if layer.plane == "floor": draw_art(c,art,layer.file,rectangle(layer.rect),offset,zoom)
		else: items.append({"type":"art","layer":layer,"depth":float(layer.depth)})
	var ordered: Dictionary = owner.presentation_order(owner.displayed_actor,owner.source_camera())
	if not ordered.get("ok",false): return str(ordered.get("error","2.5D 顯示順序無效。"))
	for e: Dictionary in ordered.entries:
		if str(e.get("id","")) in ["object_1","object_2","object_3"]: continue
		var depth: float = owner.world_position(owner.displayed_actor).y-ORIGIN.y if e.kind=="player" else float(e.world_xy_raw[1])/16.0-ORIGIN.y
		if int(e.get("sprite_priority",2))==3: depth += 1000
		items.append({"type":"source","entry":e,"depth":depth})
	items.sort_custom(func(a: Dictionary,b: Dictionary) -> bool: return a.depth < b.depth)
	for item: Dictionary in items:
		if item.type == "art":
			var layer: Dictionary = item.layer
			draw_art(c,art,layer.file,rectangle(layer.rect),offset,zoom,str(layer.id).begins_with("chair"))
			continue
		var e: Dictionary = item.entry
		if e.kind == "player":
			var selected: Dictionary = HD.select(owner.displayed_actor,owner.render_phase)
			if not selected.get("ok",false): return str(selected.error)
			var key: String = str(selected.direction)+"/"+("idle" if selected.action=="idle" else "walk-%02d"%int(selected.walk_index))
			if not art.frames.has(key): return "2.5D 必要影格缺失。"
			var frame: Dictionary = art.frames[key]
			var point: Vector2 = owner.world_position(owner.displayed_actor)-ORIGIN
			var ellipse := PackedVector2Array()
			for i: int in 24: ellipse.append(offset+(point+Vector2(cos(i*TAU/24)*4.0,sin(i*TAU/24)*1.0))*zoom)
			c.draw_colored_polygon(ellipse,Color(0,0,0,0.2))
			var scale: float = float(frame.display_scale)
			c.draw_texture_rect_region(art.textures["player-"+str(frame.direction)+".png"],Rect2(offset+(point-Vector2(256,448)*scale)*zoom,Vector2(512,512)*scale*zoom),rectangle(frame.rect))
		else:
			var point := Vector2(float(e.world_xy_raw[0]),float(e.world_xy_raw[1]))/16.0-ORIGIN-Vector2(e.anchor[0],e.anchor[1])
			var id: String = str(e.id)
			if art.data.layout.dynamic_props.has(id):
				var prop: Dictionary = art.data.layout.dynamic_props[id]
				draw_art(c,art,prop.file,Rect2(point+Vector2(prop.offset[0],prop.offset[1]),Vector2(prop.size[0],prop.size[1])),offset,zoom)
			elif id == "object_6" and int(e.get("image_index",46)) == 46:
				draw_art(c,art,"cirrus-46.png",Rect2(point+Vector2(2,5),Vector2(20,11)),offset,zoom)
			else:
				# Required expressions, pickup poses and dynamic decorations retain
				# their source image and display sample, never a guessed new pose.
				c.draw_texture_rect(e.texture,Rect2(offset+point*zoom,Vector2(e.dimensions[0],e.dimensions[1])*zoom),false)
	for a: Array in art.data.layout.foreground_rects: draw_shell(c,art,offset,zoom,rectangle(a))
	if owner.show_overlay:
		for index: Variant in owner.room_bundle.data.movement_profile.verified_query_indices:
			var p := Vector2((int(index)%256)*8,(int(index)/256)*8)-ORIGIN
			if Rect2(0,0,448,256).has_point(p): c.draw_rect(Rect2(offset+p*zoom,Vector2(8,8)*zoom),Color(0.2,0.9,0.8,0.25),false,1.0)
		var p: Vector2 = offset+(owner.world_position(owner.displayed_actor)-ORIGIN)*zoom
		c.draw_line(p-Vector2(4,0)*zoom,p+Vector2(4,0)*zoom,Color.GOLD,1.0)
	return ""
