extends "res://equipment_core.gd"
## New bounded transfer controller. The old equipment entry remains unchanged.
const TRANSITION_SHA: String = "c8036f8ff0d0c1a20a1459c1718c4681ff3e1244583fb679a254ddde90fdd4fa"
var transition_data: Dictionary = {}
var original_verified: Dictionary = {}
var stage: String = "original_room"
var scene_id: int = 8
var generation: int = 0
var fade: int = 2
var rgb: Array[int] = [0,0,0]
var pending_load: Dictionary = {}
var landing_objects: Array[PackedByteArray] = []
var arrival_actor: PackedByteArray = PackedByteArray()

func configure_transition(data: Dictionary, old_data: Dictionary, movement_profile: Dictionary, flag_bytes: PackedByteArray, character: Dictionary, room: Dictionary) -> Dictionary:
	transition_data.clear()
	if ActorAnimation._hash(JSON.stringify(data,"",true).to_utf8_buffer()) != TRANSITION_SHA:
		return {"ok":false,"error":"Unapproved transition source contract"}
	var result: Dictionary = super.configure(old_data,movement_profile,flag_bytes,character,room)
	if not result.ok: return result
	original_verified = verified.duplicate(true)
	transition_data = data.duplicate(true)
	reset()
	return {"ok":true}

func reset() -> void:
	super.reset()
	generation += 1; stage = "original_room"; scene_id = 8; fade = 2; rgb = [0,0,0]
	pending_load.clear(); landing_objects.clear(); arrival_actor.clear()
	if not original_verified.is_empty(): verified = original_verified.duplicate(true)

func transition_snapshot() -> Dictionary:
	var objects: Array[String] = []
	for raw: PackedByteArray in landing_objects: objects.append(raw.hex_encode())
	return {"scene":scene_id,"stage":stage,"fade":fade,"rgb":rgb.duplicate(),"player":player.hex_encode(),
		"cameras":cameras.duplicate(true),"objects":objects,"arrival_actor":null if arrival_actor.is_empty() else arrival_actor.hex_encode()}

func _fade_tick() -> void:
	var complete: bool = true
	for value: int in rgb:
		if value != (-255 if fade == 1 else 0): complete = false
	var direction: int = -8 if fade == 1 else 8
	for i: int in 3: rgb[i] = clampi(rgb[i]+direction,-255,0)
	if complete: fade = 2

func _old_transfer_tick() -> void:
	_free()
	var target: Array = [Movement.signed16(word(player,0)),Movement.signed16(word(player,2))]
	for i: int in cameras.size(): cameras[i] = _camera(cameras[i],target)

func _landing_camera(state: Dictionary) -> Dictionary:
	var result: Dictionary = state.duplicate(true)
	result.display_x = state.x; result.display_y = state.y; result.dx = 0; result.dy = 0
	for axis: int in 2:
		var key: String = "x" if axis == 0 else "y"
		var center: int = 0xa80 if axis == 0 else 0x780
		var upper: int = Movement.signed16(int(state[key])+center+0x200)
		var lower: int = Movement.signed16(int(state[key])+center-0x200)
		var minimum: int = int(transition_data.camera_limits_raw[axis])
		var maximum: int = int(transition_data.camera_limits_raw[axis+2])
		var value: int = Movement.signed16(word(player,axis*2))
		if value > upper:
			var delta: int = mini(128,Movement.signed16(value-upper))
			var proposed: int = Movement.signed16(int(state[key])+delta)
			if proposed > maximum: proposed = maximum; delta = 0
			result[key] = proposed; result["d"+key] = delta
		if value < lower:
			var delta: int = mini(128,Movement.signed16(lower-value))
			var proposed: int = Movement.signed16(int(result[key])-delta)
			if proposed < minimum: proposed = minimum; delta = 0
			result[key] = proposed; result["d"+key] = -delta
	return result

func _object_tick(raw: PackedByteArray, program: Dictionary) -> void:
	var sequence: Array = program.sequence
	var cursor: int = word(raw,0x1c)
	var timer: int = word(raw,0x1e)
	if cursor % 3 != 0 or cursor >= sequence.size()-1 or timer > int(sequence[cursor]):
		error = "Invalid landing object animation"; return
	if timer >= int(sequence[cursor]):
		timer = 0; cursor += 3; put(raw,0xa,word(raw,0xa)|0x80)
	timer += 1
	if int(sequence[cursor]) == 0: cursor = 0; put(raw,0xa,word(raw,0xa)|0x100)
	if int(sequence[cursor+2]) != 0: error = "Unknown landing animation effect"; return
	put(raw,0x1c,cursor); put(raw,0x1e,timer); put(raw,0x20,int(sequence[cursor])); put(raw,0x22,int(sequence[cursor+1]))
	put_long(raw,0x30,int(program.images[str(int(sequence[cursor+1]))]))

func _landing_tick(pad: int) -> void:
	put(player,6,word(player,6)&0xfffd); put(player,0x18,0); put(player,0x1a,0)
	if fade == 2:
		var move: Dictionary = project(player); Movement._input_gate(move,pad); _write_movement(move)
	_free()
	if not error.is_empty() or diagnostics.get("reason") == "test_boundary": return
	var bounds: Array = transition_data.viewport_world
	var x: int = Movement.signed16(word(player,0))
	var y: int = Movement.signed16(word(player,2))
	if x < int(bounds[0])*16 or x >= int(bounds[2])*16 or y < int(bounds[1])*16 or y >= int(bounds[3])*16:
		diagnostics.reason = "test_boundary"; return
	for i: int in cameras.size(): cameras[i] = _landing_camera(cameras[i])
	# Source actor 50's approved single-pose program loops every update.
	put(arrival_actor,6,word(arrival_actor,6)|0x180)
	put(arrival_actor,0x2c,0); put(arrival_actor,0x30,0)
	for i: int in landing_objects.size(): _object_tick(landing_objects[i],transition_data.object_programs[i])

func scene_resources_ready(response_generation: int, request_id: String) -> Dictionary:
	if response_generation != generation or stage != "loading" or pending_load != {"generation":response_generation,"id":request_id}:
		return {"ok":true,"accepted":false}
	player = str(transition_data.player_initializer).hex_decode()
	cameras = [transition_data.camera_initializer.duplicate(true),transition_data.camera_initializer.duplicate(true)]
	landing_objects.clear()
	for value: String in transition_data.object_initializers: landing_objects.append(value.hex_decode())
	arrival_actor = str(transition_data.actor_initializer).hex_decode()
	root = null; child = null; spark = null; spark_child = null; effect = null; effect_xy = null
	temporary_coordinates.clear(); decor = PackedByteArray(); decor.resize(60); ambient = PackedByteArray(); ambient.resize(60)
	fixed_camera = false; camera_target = null; camera_speed = 128; disabled = 0; transition_pending = false
	verified.clear()
	for index: Variant in transition_data.landing_query_indices: verified[int(index)] = true
	scene_id = 7; fade = 0; stage = "arrival_first_update"; pending_load.clear()
	commands = transition_data.initialization.duplicate(true)
	requests = [{"type":"scene_initialized","generation":generation,"scene":7},{"type":"retain_source_music","id":30}]
	return {"ok":true,"accepted":true}

func step(pad: int, signals: Dictionary, pressed: int = 0) -> Dictionary:
	if transition_data.is_empty() or not error.is_empty(): return {"ok":false,"error":"Transition core not configured: "+error}
	if not [0,0x1000,0x2000,0x4000,0x8000,0x0200,0x0400].has(pad): return {"ok":false,"error":"Invalid transfer input"}
	if stage == "original_room":
		var result: Dictionary = super.step(pad,signals,pressed)
		if not result.ok: return result
		if transition_pending:
			stage = "fade_out"; fade = 1; disabled = 255
			requests.append({"type":"transition_begin","generation":generation,"destination":7})
			_old_transfer_tick()
			result.state = snapshot()
		return result
	commands.clear(); requests.clear(); diagnostics = {"applied":true}
	if stage in ["loading","boundary"]: return {"ok":true,"applied":false,"state":snapshot()}
	var before: Dictionary = snapshot()
	var before_stage: String = stage
	var before_rgb: Array[int] = rgb.duplicate()
	var before_fade: int = fade
	if stage == "fade_out":
		_fade_tick()
		if fade == 2:
			stage = "loading"; pending_load = {"generation":generation,"id":"map001_scene7_resources"}
			requests = [{"type":"load_scene","generation":generation,"id":"map001_scene7_resources"}]
			return {"ok":true,"applied":true,"state":snapshot()}
		put(player,6,word(player,6)&0xfffd); put(player,0x18,0); put(player,0x1a,0)
		_old_transfer_tick()
	elif stage == "arrival_first_update":
		stage = "fade_in"; _landing_tick(pad)
	else:
		if stage == "fade_in":
			_fade_tick()
			if fade == 2:
				stage = "landing"; requests = [{"type":"control_restored","generation":generation}]
		elif stage != "landing": return {"ok":false,"error":"Unknown transfer stage"}
		for contact: Dictionary in transition_data.contacts:
			var b: Array = contact.bounds_raw
			if word(player,0) >= int(b[0]) and word(player,0) <= int(b[2]) and word(player,2) >= int(b[1]) and word(player,2) <= int(b[3]):
				stage = "boundary"; requests = [{"type":"test_boundary","reason":contact.policy}]
				return {"ok":true,"applied":false,"reason":"test_boundary","state":snapshot()}
		_landing_tick(pad)
	if diagnostics.get("reason") == "test_boundary":
		_restore(before); stage = before_stage; rgb = before_rgb; fade = before_fade
		return {"ok":true,"applied":false,"reason":"test_boundary","state":snapshot()}
	if not error.is_empty(): return {"ok":false,"error":error}
	return {"ok":true,"applied":true,"state":snapshot()}

func equipment(action: String) -> Dictionary:
	if stage not in ["original_room","landing"]: return {"ok":false,"error":"Equipment disabled during transfer"}
	return super.equipment(action)
