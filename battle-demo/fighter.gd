extends Control
## Presentation only: all textures are validated and loaded before playback.
signal animation_completed(animation_name: String)
signal animation_hit(animation_name: String)

const REQUIRED_STATES: Array[String] = ["idle", "attack", "hurt", "down"]
const PROCEDURAL_STATES: Dictionary = {
	"idle": {"durations": [1.0], "loop": true},
	"attack": {"durations": [0.22, 0.33], "loop": false, "hit_frame": 1},
	"hurt": {"durations": [0.28], "loop": false},
	"down": {"durations": [0.5], "loop": false},
}

var _appearance: Dictionary = {}
var _state: String = "idle"
var appearance: Dictionary:
	get:
		return _appearance
	set(value):
		configure(value)
var state: String:
	get:
		return _state
	set(value):
		set_animation(value)
var facing: float = 1.0:
	set(value):
		facing = value
		queue_redraw()
var clock: float = 0.0
var playback_speed: float = 1.0
var selected: bool = false:
	set(value):
		selected = value
		queue_redraw()
var active: bool = false:
	set(value):
		active = value
		queue_redraw()
var texture_cache: Dictionary = {}
var error_message: String = ""
var configured: bool = false
var frame_index: int = 0
var animation_elapsed: float = 0.0
var animation_states: Dictionary = {}
var renderer: String = "procedural"
var _finished: bool = false
var _hit_sent: bool = false

func _ready() -> void:
	if not configured and error_message.is_empty():
		configure(appearance)

func _reject(message: String) -> String:
	error_message = message
	configured = false
	texture_cache.clear()
	animation_states.clear()
	queue_redraw()
	return message

func configure(definition: Dictionary) -> String:
	# CACHE_MODE_IGNORE keeps each fighter's lifetime independent of other scenes.
	configured = false
	error_message = ""
	texture_cache.clear()
	animation_states.clear()
	_appearance = definition.duplicate(true)
	var states: Variant = definition.get("states", {})
	if not states is Dictionary:
		return _reject("appearance.states must be a dictionary")
	var legacy_empty: bool = true
	for entry: Variant in states.values():
		if not entry is Array or not entry.is_empty():
			legacy_empty = false
	if not definition.has("renderer") and not legacy_empty:
		return _reject("Nonempty states require an explicit sprite renderer")
	renderer = str(definition.get("renderer", "procedural"))
	if renderer not in ["procedural", "sprite"]:
		return _reject("Unknown appearance renderer: " + renderer)
	var anchor: Variant = definition.get("anchor", [0.5, 1.0])
	if not anchor is Array or anchor.size() != 2:
		return _reject("anchor must contain two normalized coordinates")
	for coordinate: Variant in anchor:
		if not _is_number(coordinate) or not is_finite(float(coordinate)) or float(coordinate) < 0.0 or float(coordinate) > 1.0:
			return _reject("anchor must contain finite coordinates between 0 and 1")
	var scale_value: Variant = definition.get("scale", 1.0)
	if not _is_number(scale_value) or not is_finite(float(scale_value)) or float(scale_value) <= 0.0:
		return _reject("scale must be finite and greater than zero")
	if definition.get("default_facing", "right") not in ["left", "right"]:
		return _reject("default_facing must be left or right")
	if renderer == "procedural":
		if not legacy_empty:
			return _reject("Procedural renderer does not accept sprite animation states")
		animation_states = PROCEDURAL_STATES.duplicate(true)
	else:
		for animation_name: String in REQUIRED_STATES:
			var spec: Variant = states.get(animation_name)
			if not spec is Dictionary:
				return _reject("Missing required animation: " + animation_name)
			var frames: Variant = spec.get("frames")
			var durations: Variant = spec.get("durations")
			if not frames is Array or frames.is_empty():
				return _reject(animation_name + ": frames must not be empty")
			if not durations is Array or durations.size() != frames.size():
				return _reject(animation_name + ": each frame needs a duration")
			for duration: Variant in durations:
				if not _is_number(duration) or not is_finite(float(duration)) or float(duration) <= 0.0:
					return _reject(animation_name + ": durations must be finite and greater than zero")
			if not spec.get("loop") is bool or spec["loop"] != (animation_name == "idle"):
				return _reject(animation_name + ": only idle must loop; other animations must play once")
			if animation_name == "attack":
				var hit_frame: Variant = spec.get("hit_frame")
				if not _is_number(hit_frame) or not is_finite(float(hit_frame)) or float(hit_frame) != floor(float(hit_frame)) or int(hit_frame) < 0 or int(hit_frame) >= frames.size():
					return _reject("attack: hit_frame must identify a valid frame")
			for path: Variant in frames:
				if not path is String or path.is_empty() or not ResourceLoader.exists(path):
					return _reject(animation_name + ": missing texture " + str(path))
				if not texture_cache.has(path):
					var texture: Resource = ResourceLoader.load(path, "Texture2D", ResourceLoader.CACHE_MODE_IGNORE)
					if not texture is Texture2D or texture.get_width() <= 0 or texture.get_height() <= 0:
						return _reject(animation_name + ": invalid texture " + str(path))
					texture_cache[path] = texture
			animation_states[animation_name] = spec.duplicate(true)
	configured = true
	set_animation("idle")
	return ""

func _is_number(value: Variant) -> bool:
	return value is int or value is float

func set_animation(animation_name: String) -> bool:
	if not configured or not animation_states.has(animation_name):
		error_message = "Cannot play animation: " + animation_name
		return false
	_state = animation_name
	error_message = ""
	clock = 0.0
	animation_elapsed = 0.0
	frame_index = 0
	_finished = false
	_hit_sent = false
	queue_redraw()
	return true

func animation_duration(animation_name: String) -> float:
	var duration: float = 0.0
	for value: Variant in animation_states.get(animation_name, {}).get("durations", []):
		duration += float(value)
	return duration

func hit_time(animation_name: String = "attack") -> float:
	var spec: Dictionary = animation_states.get(animation_name, {})
	if not spec.has("hit_frame"):
		return -1.0
	var result: float = 0.0
	for i: int in range(int(spec["hit_frame"])):
		result += float(spec["durations"][i])
	return result

func is_animation_finished() -> bool:
	return _finished

func facing_multiplier() -> float:
	var natural: float = -1.0 if appearance.get("default_facing", "right") == "left" else 1.0
	return (-1.0 if facing < 0.0 else 1.0) * natural

func advance_animation(delta: float) -> void:
	if not configured or not is_finite(delta) or delta <= 0.0 or not is_finite(playback_speed) or playback_speed <= 0.0:
		return
	if _finished:
		return
	var spec: Dictionary = animation_states[state]
	var duration: float = animation_duration(state)
	clock += delta * playback_speed
	animation_elapsed = fmod(clock, duration) if spec["loop"] else minf(clock, duration)
	var elapsed: float = animation_elapsed
	var durations: Array = spec["durations"]
	frame_index = 0
	while frame_index < durations.size() - 1 and elapsed >= float(durations[frame_index]):
		elapsed -= float(durations[frame_index])
		frame_index += 1
	var should_hit: bool = not _hit_sent and spec.has("hit_frame") and clock >= hit_time(state)
	if should_hit:
		_hit_sent = true
	var should_finish: bool = not spec["loop"] and clock >= duration
	_finished = should_finish
	queue_redraw()
	# Both transitions can occur during one long frame, but each signal fires once.
	var completed_state: String = state
	if should_hit:
		animation_hit.emit(completed_state)
	if should_finish:
		animation_completed.emit(completed_state)

func _process(delta: float) -> void:
	advance_animation(delta)

func _draw() -> void:
	if not configured:
		return
	var color := Color(appearance.get("color", "79cdd4"))
	var origin := Vector2(size.x * 0.5, size.y - 12)
	draw_set_transform(origin)
	paint_ellipse(Vector2.ZERO, Vector2(58, 12), Color(0.0, 0.0, 0.0, 0.3))
	if selected or active:
		var ring := PackedVector2Array()
		for i: int in range(49):
			var angle: float = i * TAU / 48.0
			ring.append(Vector2(cos(angle) * 59.0,sin(angle) * 11.0 - 2.0))
		draw_polyline(ring,Color("f6d99b") if selected else color,3.0,true)
	if renderer == "sprite":
		var frames: Array = animation_states[state]["frames"]
		var texture: Texture2D = texture_cache[frames[frame_index]]
		var extent: Vector2 = texture.get_size() * float(appearance.get("scale", 1.0))
		var anchor: Array = appearance.get("anchor", [0.5, 1.0])
		draw_set_transform(origin, 0.0, Vector2(facing_multiplier(), 1.0))
		var tint: Color = Color(1.5,1.5,1.5) if state == "hurt" and animation_elapsed < 0.07 else Color.WHITE
		draw_texture_rect(texture, Rect2(-extent * Vector2(anchor[0], anchor[1]), extent), false,tint)
		return
	var lean: float = 12.0 if state == "attack" else 0.0
	var bob: float = sin(clock * 2.5) * 2.5 if state == "idle" else 0.0
	var rotation: float = -1.25 if state == "down" else 0.0
	draw_set_transform(origin + Vector2(lean * facing, bob), rotation, Vector2(facing_multiplier(), 1) * float(appearance.get("scale", 1.0)))
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
