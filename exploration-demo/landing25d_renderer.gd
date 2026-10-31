extends RefCounted
const Art = preload("res://enhanced25d_renderer.gd")
const HD = preload("res://character_hd_animation.gd")
const Laia = preload("res://landing25d_animation.gd")
const ORIGIN = Vector2(512,1792)

static func actor(c: Control, art: Dictionary, prefix: String, key: String, point: Vector2, offset: Vector2, zoom: float) -> String:
	if not art.frames.has(key): return "必要角色影格未配置："+key
	var f: Dictionary = art.frames[key]
	var ellipse := PackedVector2Array()
	for i: int in 24: ellipse.append(offset+(point+Vector2(cos(i*TAU/24)*4.0,sin(i*TAU/24)))*zoom)
	c.draw_colored_polygon(ellipse,Color(0,0,0,0.2))
	var scale: float = float(f.display_scale)
	c.draw_texture_rect_region(art.textures[prefix+str(f.direction)+".png"],Rect2(offset+(point-Vector2(256,448)*scale)*zoom,Vector2(512,512)*scale*zoom),Art.rectangle(f.rect))
	return ""

static func draw(c: Control, owner: Control, art: Dictionary) -> String:
	var zoom: float = minf(c.size.x/448.0,c.size.y/256.0)
	var offset := (c.size-Vector2(448,256)*zoom)/2
	c.draw_rect(Rect2(Vector2.ZERO,c.size),Color("101618"))
	Art.draw_shell(c,art,offset,zoom)
	var items: Array[Dictionary] = []
	for layer: Dictionary in art.data.layout.layers: items.append({"type":"art","layer":layer,"depth":float(layer.depth)})
	var ordered: Dictionary = owner.presentation_order(owner.displayed_actor,owner.source_camera())
	if not ordered.get("ok",false): return str(ordered.get("error","無效的來源顯示排序。"))
	for e: Dictionary in ordered.entries:
		var depth: float = float(e.world_xy_raw[1])/16.0-ORIGIN.y
		if int(e.get("sprite_priority",2))==3: depth+=1000
		items.append({"type":"source","entry":e,"depth":depth})
	items.sort_custom(func(a: Dictionary,b: Dictionary) -> bool: return a.depth<b.depth)
	for item: Dictionary in items:
		if item.type=="art":
			var layer: Dictionary=item.layer
			Art.draw_art(c,art,layer.file,Art.rectangle(layer.rect),offset,zoom,bool(layer.preserve)); continue
		var e: Dictionary=item.entry
		var point := Vector2(e.world_xy_raw[0],e.world_xy_raw[1])/16.0-ORIGIN
		if e.kind=="player":
			var selected: Dictionary=HD.select(owner.displayed_actor,owner.render_phase)
			if not selected.ok: return str(selected.error)
			var key: String=str(selected.direction)+"/"+("idle" if selected.action=="idle" else "walk-%02d"%int(selected.walk_index))
			var error: String=actor(c,owner.enhanced_bundle,"player-",key,point,offset,zoom)
			if not error.is_empty(): return error
		elif str(e.id)=="landing_event_actor_50":
			var selected: Dictionary=Laia.select(str(owner.shown_event.arrival_actor).hex_decode(),owner.render_phase)
			if not selected.ok: return str(selected.error)
			var error: String=actor(c,art,"laia-",selected.key,point,offset,zoom)
			if not error.is_empty(): return error
		else:
			var id: String="object_"+str(e.slot)
			if id=="object_1":
				var name: String="steam-%d.png"%int(e.image_index)
				if not art.textures.has(name): return "未配置的蒸氣影格。"
				c.draw_texture_rect(art.textures[name],Rect2(offset+(point-Vector2(8,14))*zoom,Vector2(16,16)*zoom),false)
			elif art.data.layout.dynamic_props.has(id):
				var p: Dictionary=art.data.layout.dynamic_props[id]
				if int(e.image_index)!=int(p.image_index): return "未配置的物件姿勢："+id
				Art.draw_art(c,art,p.file,Rect2(point+Vector2(p.offset[0],p.offset[1]),Vector2(p.size[0],p.size[1])),offset,zoom,bool(p.preserve))
			else: return "未配置的必要樓下物件："+id
	for rect: Array in art.data.layout.foreground_rects: Art.draw_shell(c,art,offset,zoom,Art.rectangle(rect))
	if owner.show_overlay:
		for index: Variant in owner.landing_bundle.data.landing_query_indices:
			var point:=Vector2((int(index)%256)*8,(int(index)/256)*8)-ORIGIN
			c.draw_rect(Rect2(offset+point*zoom,Vector2(8,8)*zoom),Color(0.2,0.9,0.8,0.3),false,1.0)
	return ""
