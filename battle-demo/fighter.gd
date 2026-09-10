extends Control
## Original procedural stand-ins. Optional frame paths replace presentation only.
var appearance: Dictionary = {}
var state: String = "idle"
var facing: float = 1.0
var clock: float = 0.0
var playback_speed: float = 1.0
var selected: bool = false
var active: bool = false
var texture_cache: Dictionary = {}

func _process(delta: float) -> void:
	clock += delta * playback_speed
	queue_redraw()

func _draw() -> void:
	var color := Color(appearance.get("color", "79cdd4"))
	var origin := Vector2(size.x * 0.5, size.y - 12)
	draw_set_transform(origin)
	paint_ellipse(Vector2.ZERO, Vector2(58, 12), Color(0.0, 0.0, 0.0, 0.3))
	if selected or active:
		draw_arc(Vector2(0,-2), 55, 0, TAU, 48, Color("f6d99b") if selected else color, 3, true)
	var frames: Array = appearance.get("states", {}).get(state, [])
	if not frames.is_empty():
		var path: String = frames[int(clock * 8.0) % frames.size()]
		if not texture_cache.has(path) and ResourceLoader.exists(path):
			texture_cache[path] = load(path)
		if texture_cache.has(path):
			var texture: Texture2D = texture_cache[path]
			var extent: Vector2 = texture.get_size() * float(appearance.get("scale", 1.0))
			var anchor: Array = appearance.get("anchor", [0.5, 1.0])
			draw_texture_rect(texture, Rect2(-extent * Vector2(anchor[0],anchor[1]), extent), false)
			return
	var lean: float = 12.0 if state == "attack" else 0.0
	var bob: float = sin(clock * 2.5) * 2.5 if state == "idle" else 0.0
	var rotation: float = -1.25 if state == "down" else 0.0
	draw_set_transform(origin + Vector2(lean * facing, bob), rotation, Vector2(facing, 1) * float(appearance.get("scale", 1.0)))
	if state == "hurt":
		color = Color.WHITE
	if state == "down":
		color = color.darkened(0.6)
	draw_line(Vector2(-19,-12), Vector2(-13,-61), Color("36465a"), 15, true)
	draw_line(Vector2(19,-12), Vector2(10,-61), Color("36465a"), 15, true)
	draw_colored_polygon(PackedVector2Array([Vector2(-29,-111),Vector2(23,-111),Vector2(33,-47),Vector2(-36,-47)]),color.darkened(0.18))
	draw_colored_polygon(PackedVector2Array([Vector2(-22,-108),Vector2(20,-108),Vector2(13,-70),Vector2(-17,-70)]),color)
	draw_line(Vector2(-20,-55),Vector2(25,-55),Color("f1d5a0"),6,true)
	draw_circle(Vector2(0,-135),21,Color("dfc9b1"))
	draw_arc(Vector2(0,-138),22,PI,TAU,20,color,11,true)
	draw_line(Vector2(8,-138),Vector2(15,-138),Color("1c2c40"),3,true)
	match appearance.get("shape", "staff"):
		"shield":
			draw_colored_polygon(PackedVector2Array([Vector2(13,-110),Vector2(49,-100),Vector2(43,-61),Vector2(29,-45),Vector2(12,-66)]),Color("293b50"))
			draw_polyline(PackedVector2Array([Vector2(13,-110),Vector2(49,-100),Vector2(43,-61),Vector2(29,-45),Vector2(12,-66),Vector2(13,-110)]),color.lightened(0.35),4,true)
			draw_line(Vector2(29,-97),Vector2(29,-62),color,4,true)
		"staff":
			draw_line(Vector2(35,-9),Vector2(35,-159),Color("cab58c"),6,true)
			draw_circle(Vector2(35,-165),10,color.lightened(0.45))
			draw_arc(Vector2(35,-165),18,clock,clock+PI*1.6,24,color,2,true)
		"blade":
			draw_colored_polygon(PackedVector2Array([Vector2(31,-64),Vector2(68,-128),Vector2(54,-68)]),Color("dbe3e8"))
			draw_line(Vector2(21,-61),Vector2(52,-56),color,5,true)

func paint_ellipse(center: Vector2, radius: Vector2, color: Color) -> void:
	var points := PackedVector2Array()
	for i: int in range(40):
		var angle: float = i * TAU / 40.0
		points.append(center + Vector2(cos(angle),sin(angle)) * radius)
	draw_colored_polygon(points, color)
