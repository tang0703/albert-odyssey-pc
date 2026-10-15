extends RefCounted
## Bounded, named PC instructions. No nodes, rendering, audio, files or clocks.
## Device acknowledgements are inputs; all world/event state rolls forward.
const Movement = preload("res://movement_core.gd")
const ActorAnimation = preload("res://character_animation_core.gd")
const Decorations = preload("res://room_decoration_core.gd")
const RoomMovement = preload("res://room_movement_core.gd")
const PROGRAMS_SHA: String = "51ce587f24b7b1e4cc9702b3e48b19274247df835138a7493fa2f2498bb18d1f"
const ACTIONS: Array[String] = ["end","require_story_branch","lock_control","unlock_control","attach_player","wait_player","expression","player_pose","camera_target","camera_follow_player","wait_camera","load_audio","wait_audio_loaded","play_audio","wait_audio_started","attach_cirrus","cirrus_animation","wait_updates","source_text_layout","dialogue","player_speed","player_move_axis"]
var initial: Dictionary = {}
var instructions: Dictionary = {}
var starts: Dictionary = {}
var animation: RefCounted
var flags: PackedByteArray
var verified: Dictionary = {}
var boundaries: Array = []
var decoration_programs: Array = []
var expressions: Dictionary = {}
var cirrus_sequence: Array = []
var player: PackedByteArray
var decor: PackedByteArray
var ambient: PackedByteArray
var cameras: Array = []
var effect: Variant = null
var effect_xy: Variant = null
var root: Variant = null
var child: Variant = null
var disabled: int = 0
var fixed_camera: bool = false
var camera_target: Variant = null
var camera_speed: int = 128
var runs: int = 0
var update: int = 0
var story: String = "01"
var commands: Array = []
var requests: Array = []
var error: String = ""
var diagnostics: Dictionary = {}

static func word(raw: PackedByteArray, offset: int) -> int:
	return int(raw[offset]) * 256 + int(raw[offset+1])

static func put(raw: PackedByteArray, offset: int, value: int) -> void:
	raw[offset] = (value >> 8) & 255
	raw[offset+1] = value & 255

static func put_long(raw: PackedByteArray, offset: int, value: int) -> void:
	put(raw,offset,value >> 16)
	put(raw,offset+2,value)

static func project(raw: PackedByteArray) -> Dictionary:
	var fields: Dictionary = Movement.FIELDS.duplicate(true)
	fields.merge(ActorAnimation.FIELDS,true)
	var result: Dictionary = {}
	for key: String in fields:
		var offset: int = fields[key][0]
		var count: int = fields[key][1]
		var value: int = 0
		for i: int in count: value = (value << 8) | raw[offset+i]
		result[key] = value
	return result

func configure(data: Dictionary, movement_profile: Dictionary, flag_bytes: PackedByteArray, character: Dictionary, room: Dictionary) -> Dictionary:
	initial.clear(); instructions.clear(); starts.clear(); verified.clear()
	error = ""
	if data.get("schema") != "ao_pc_event_core_v1" or not data.get("contract") is Dictionary or not data.get("initial_state") is Dictionary:
		return {"ok":false,"error":"Missing event core contract"}
	var contract: Dictionary = data.contract
	if contract.get("schema") != "ao_pc_cirrus_source_contract_v1" or not contract.get("programs") is Dictionary or contract.programs.size() != 5:
		return {"ok":false,"error":"Unknown event instruction contract"}
	if ActorAnimation._hash(JSON.stringify(contract.programs,"",true).to_utf8_buffer()) != PROGRAMS_SHA:
		return {"ok":false,"error":"Unapproved converted instructions or operands"}
	var checker := RoomMovement.new()
	var checked: Dictionary = checker.configure_room(movement_profile,flag_bytes,room.boundaries)
	if not checked.ok: return checked
	animation = ActorAnimation.new()
	checked = animation.configure(character.profile,character.animation_bank,character.image_table)
	if not checked.ok: return checked
	var decoration_checker := Decorations.new()
	checked = decoration_checker.configure(room.visuals.programs)
	if not checked.ok: return checked
	for name: String in contract.programs:
		var rows: Variant = contract.programs[name]
		if not rows is Array or rows.is_empty(): return {"ok":false,"error":"Empty required event program"}
		for row: Variant in rows:
			if not row is Dictionary or not ACTIONS.has(str(row.get("action"))) or not row.get("args") is Dictionary or not row.get("source") is Dictionary:
				return {"ok":false,"error":"Unknown PC event instruction"}
			var origin: Dictionary = row.source
			if not Movement.integer(origin.get("offset")) or not Movement.integer(origin.get("span")) or int(origin.span) <= 0 or instructions.has(int(origin.offset)):
				return {"ok":false,"error":"Invalid PC instruction identity"}
			instructions[int(origin.offset)] = row.duplicate(true)
		starts[name] = int(rows[0].source.offset)
	if instructions.size() != 35 or not starts.has_all(["entry","main","expression","retreat","cirrus"]):
		return {"ok":false,"error":"Incomplete Cirrus program"}
	initial = data.initial_state.duplicate(true)
	if str(initial.get("player","")).hex_decode().size() != 112 or str(initial.get("decor","")).hex_decode().size() != 60 or str(initial.get("ambient","")).hex_decode().size() != 60 or initial.get("story") != "01":
		initial.clear()
		return {"ok":false,"error":"Invalid event seed"}
	flags = flag_bytes.duplicate()
	for index: Variant in movement_profile.verified_query_indices: verified[int(index)] = true
	boundaries = room.boundaries.duplicate(true)
	decoration_programs = room.visuals.programs.duplicate(true)
	expressions = contract.expression_sequences.duplicate(true)
	cirrus_sequence = contract.cirrus_sequence.duplicate()
	reset()
	return {"ok":true,"error":""}

func reset() -> void:
	if initial.is_empty(): return
	_restore(initial)
	error = ""; diagnostics = {}

func _restore(value: Dictionary) -> void:
	player = str(value.player).hex_decode(); decor = str(value.decor).hex_decode(); ambient = str(value.ambient).hex_decode()
	cameras = value.cameras.duplicate(true)
	effect = value.effect.duplicate(true) if value.effect != null else null
	effect_xy = value.effect_xy.duplicate() if value.effect_xy != null else null
	root = value.root.duplicate(true) if value.root != null else null
	child = value.child.duplicate(true) if value.child != null else null
	disabled = int(value.disabled); fixed_camera = bool(value.fixed_camera)
	camera_target = value.camera_target.duplicate() if value.camera_target != null else null
	camera_speed = int(value.camera_speed); runs = int(value.runs); update = int(value.update)
	story = str(value.story); commands = value.commands.duplicate(true); requests = value.requests.duplicate(true)

func snapshot() -> Dictionary:
	return {"player":player.hex_encode(),"decor":decor.hex_encode(),"ambient":ambient.hex_encode(),
		"effect":effect.duplicate(true) if effect != null else null,"effect_xy":effect_xy.duplicate() if effect_xy != null else null,
		"cameras":cameras.duplicate(true),"disabled":disabled,"fixed_camera":fixed_camera,
		"camera_target":camera_target.duplicate() if camera_target != null else null,"camera_speed":camera_speed,
		"root":root.duplicate(true) if root != null else null,"child":child.duplicate(true) if child != null else null,
		"runs":runs,"story":story,"commands":commands.duplicate(true),"requests":requests.duplicate(true),"update":update}

func _decode(advance: bool) -> void:
	if advance:
		put(player,0x30,word(player,0x30)+1)
		if word(player,0x30) >= word(player,0x32):
			put(player,0x30,0); put(player,0x2c,word(player,0x2c)+3); put(player,6,word(player,6)|0x80)
	var record: Array[int] = animation._record(word(player,0x36),word(player,0x2c))
	if record.is_empty(): error = "Unknown player animation record"; return
	if record[0] == 0:
		put(player,0x2c,0); put(player,6,word(player,6)|0x100)
		record = animation._record(word(player,0x36),0)
	put(player,0x32,record[0]); put(player,0x34,record[1])
	put(player,0x14,(word(player,0x14)&0xfffe) | (1 if record[2]&4 else 0))
	put_long(player,0x5c,ActorAnimation._u32(animation._images,record[1]*4))

func _pose(heading: int) -> void:
	for offset: int in [0x30,0x2c,0x18,0x1a]: put(player,offset,0)
	put(player,0x26,heading); put(player,0x36,heading); _decode(false)

func _forced(axis: int, target: int) -> bool:
	var position: int = word(player,axis*2)
	var delta: int = Movement.signed16(target-position)
	var speed: int = Movement.SPEED_COMPONENTS[word(player,0x24)][0]
	var heading: int = (4 if axis == 0 else 6) if delta < 0 else (0 if axis == 0 else 2)
	var amount: int = maxi(delta,-speed) if delta < 0 else mini(delta,speed)
	put(player,0x26,heading); put(player,0x18,amount if axis == 0 else 0); put(player,0x1a,amount if axis == 1 else 0)
	put(player,0x36,8+heading); _decode(true); put(player,axis*2,position+amount)
	var done: bool = (word(player,axis*2)&0xfff0) == (target&0xfff0)
	if done: put(player,6,word(player,6)&0xfeff); put(player,0x18+axis*2,0)
	return done

func _write_movement(state: Dictionary) -> void:
	for key: String in Movement.FIELDS:
		var field: Array = Movement.FIELDS[key]
		if int(field[1]) == 1: player[int(field[0])] = int(state[key])
		else: put(player,int(field[0]),int(state[key]))

func _free() -> void:
	if disabled != 255:
		if word(player,6)&2:
			var move: Dictionary = project(player)
			Movement._velocity(move); _write_movement(move)
		else: put(player,0x2c,0); put(player,0x36,word(player,0x26))
		put(player,0x18,word(player,0x18)+word(player,0x1e)); put(player,0x1a,word(player,0x1a)+word(player,0x20))
		put(player,0x1e,0); put(player,0x20,0)
	_decode(true)
	if not error.is_empty(): return
	var result: Dictionary = Movement._collision_step(project(player),flags)
	if not result.ok: error = result.error; return
	diagnostics = result.diagnostics
	for lookup: Dictionary in diagnostics.lookups:
		if not verified.has(int(lookup.index)): diagnostics.reason = "test_boundary"; return
	_write_movement(result.state)

func _camera(state: Dictionary, target: Array) -> Dictionary:
	var result: Dictionary = state.duplicate(true)
	result.display_x = state.x; result.display_y = state.y; result.dx = 0; result.dy = 0
	for axis: int in 2:
		var key: String = "x" if axis == 0 else "y"
		var center: int = 0 if fixed_camera else (0xa80 if axis == 0 else 0x780)
		var margin: int = 0 if fixed_camera else 0x200
		var upper: int = Movement.signed16(int(state[key])+center+margin)
		var lower: int = Movement.signed16(int(state[key])+center-margin)
		var minimum: int = 8192 if axis == 0 else 24576
		var maximum: int = 10240 if axis == 0 else 25088
		var value: int = int(target[axis])
		if value > upper:
			var delta: int = mini(camera_speed,Movement.signed16(value-upper))
			var proposed: int = Movement.signed16(int(state[key])+delta)
			if proposed > maximum: proposed = maximum; delta = 0
			result[key] = proposed; result["d"+key] = delta
		if value < lower:
			var delta: int = mini(camera_speed,Movement.signed16(lower-value))
			var proposed: int = Movement.signed16(int(result[key])-delta)
			if proposed < minimum: proposed = minimum; delta = 0
			result[key] = proposed; result["d"+key] = -delta
	return result

func _effect_step() -> void:
	if effect == null or effect.ended: error = "Inactive expression wait"; return
	if int(effect.phase) == 4:
		effect.counter = (int(effect.counter)-1)&65535
		if effect.counter == 0: effect.phase = 5
		return
	effect.animation = 0 if int(effect.phase) == 0 else (1 if int(effect.phase) == 5 else 9)
	effect.timer = (int(effect.timer)+1)&65535
	if int(effect.timer) >= int(effect.duration):
		effect.timer = 0; effect.cursor = int(effect.cursor)+3; effect.flags = int(effect.flags)|0x80
	var sequence: Array = expressions[str(effect.animation)]
	if int(effect.cursor)/3 == sequence.size(): effect.cursor = 0; effect.flags = int(effect.flags)|0x100
	var record: Array = sequence[int(effect.cursor)/3]
	effect.duration = int(record[0]); effect.image = int(record[1])
	if int(effect.flags)&0x100:
		effect.flags = int(effect.flags)&0xfeff
		var ending: bool = int(effect.phase) == 5
		if not ending: effect.phase = int(effect.phase)+1
		effect.animation = 9 if int(effect.phase) == 1 else 1
		effect.timer = 0; effect.cursor = 0; effect.duration = int(expressions[str(effect.animation)][0][0])
		if ending: effect.flags = 0; effect.ended = true

func _decor_tick(raw: PackedByteArray, index: int, event_animation: bool) -> bool:
	var program: Dictionary = decoration_programs[index]
	var sequence: PackedByteArray = PackedByteArray(cirrus_sequence) if event_animation else str(program.sequence_hex).hex_decode()
	var cursor: int = word(raw,0x1c)
	var timer: int = word(raw,0x1e)
	if event_animation: timer = (timer+1)&65535
	if timer >= word(raw,0x20):
		timer = 0; cursor += 3; put(raw,0xa,word(raw,0xa)|0x80)
	if not event_animation: timer += 1
	put(raw,0x1e,timer)
	var ended: bool = sequence[cursor] == 0
	if ended:
		put(raw,0xa,word(raw,0xa)|0x100)
		if not event_animation: cursor = 0
	if not ended or not event_animation:
		put(raw,0x1c,cursor); put(raw,0x20,sequence[cursor]); put(raw,0x22,sequence[cursor+1])
	put(raw,0x14,word(raw,0x14)&0xfffe)
	put_long(raw,0x30,int(program.image_pointers[word(raw,0x22)]))
	return ended

func _wait(slot: Dictionary, signals: Dictionary) -> bool:
	match int(slot.wait):
		0:
			var old: int = int(slot.arg); slot.arg = (old-1)&65535; return old == 0
		1,2: return _forced(int(slot.wait)-1,int(slot.target))
		8: return not bool(signals.text_active)
		9: return not (word(player,6)&4)
		11:
			var done: bool = not int(cameras[0].dx) and not int(cameras[0].dy)
			if done and int(slot.arg) == 2: fixed_camera = false; camera_speed = 128
			return done
		15:
			if int(signals.resource_loaded) == 1 or int(slot.arg) > 300: return true
			slot.arg = int(slot.arg)+1; return false
		16:
			put(decor,6,0); put(decor,8,0)
			var done: bool = _decor_tick(decor,0,true)
			if done: put(decor,10,word(decor,10)&0xfeff); put(decor,0x1a,0)
			return done
		19: return bool(signals.resource_playing)
		23:
			_effect_step()
			return effect != null and bool(effect.ended)
		_: error = "Unknown event wait"; return false

func _attach(program: String, owner: String) -> void:
	if child != null and child.active: error = "Occupied event child slot"; return
	child = _slot(int(starts[program]),owner)
	if owner == "actor": put(player,6,word(player,6)|4)
	else: put(decor,10,word(decor,10)|4); put(decor,0x26,1)

static func _slot(pc: int, owner: String) -> Dictionary:
	return {"pc":pc,"owner":owner,"wait":null,"arg":0,"target":0,"active":true}

func _dispatch(slot: Variant, signals: Dictionary) -> void:
	if slot == null or not slot.active or not error.is_empty(): return
	if slot.wait != null:
		if _wait(slot,signals): slot.wait = null
		return
	for unused: int in 32:
		if not instructions.has(int(slot.pc)): error = "Unknown PC instruction cursor"; return
		var row: Dictionary = instructions[int(slot.pc)]
		var args: Dictionary = row.args
		commands.append([slot.owner,int(slot.pc),int(row.source.opcode)])
		slot.pc = int(slot.pc)+int(row.source.span)
		match str(row.action):
			"end":
				slot.active = false
				if slot.owner == "actor": put(player,6,word(player,6)&0xfffb)
				elif slot.owner == "decoration": put(decor,10,word(decor,10)&0xfffb)
				return
			"require_story_branch":
				if story != "01": error = "Unverified story branch"; return
				slot.pc = int(starts[str(args.next_program)])
			"lock_control": disabled = 255; put(player,0x2c,0); put(player,0x36,word(player,0x26))
			"unlock_control": disabled = 0
			"attach_player": _attach(str(args.program),"actor")
			"wait_player":
				if word(player,6)&4: slot.wait = 9
			"expression":
				effect = {"phase":0,"counter":int(args.hold_updates),"animation":0,"cursor":0,"timer":0,"duration":5,"image":0,"flags":0x8000,"ended":false}
				effect_xy = [word(player,0),word(player,2)]; slot.wait = 23
			"player_pose": _pose(int(args.heading)); slot.wait = 0; slot.arg = 1
			"camera_target": camera_target = [int(args.x_raw),int(args.y_raw)]; camera_speed = int(args.speed_raw); fixed_camera = true
			"camera_follow_player": fixed_camera = false
			"wait_camera": slot.wait = 11; slot.arg = 2 if args.restore_speed else 0
			"load_audio": requests.append({"type":"load_original_resource","id":"IVENT041.AIF"})
			"wait_audio_loaded": slot.wait = 15; slot.arg = 0
			"play_audio": requests.append({"type":"play_original_resource","id":"IVENT041.AIF"})
			"wait_audio_started": slot.wait = 19
			"attach_cirrus": _attach(str(args.program),"decoration")
			"cirrus_animation":
				put(decor,0x24,int(args.index)); put(decor,0x1e,0); put(decor,0x1c,0); put(decor,0x20,8); put(decor,0x22,46)
				put(decor,0x14,word(decor,0x14)&0xfffe); put(decor,10,word(decor,10)&0xfeff)
				put_long(decor,0x30,int(decoration_programs[0].image_pointers[46])); slot.wait = 16
			"wait_updates": slot.wait = 0; slot.arg = int(args.count)
			"source_text_layout": requests.append({"type":"source_text_layout","y":int(args.y)})
			"dialogue": requests.append({"type":"dialogue","id":str(args.id)}); slot.wait = 8
			"player_speed": put(player,0x24,int(args.index))
			"player_move_axis":
				var axis: int = int(args.axis); var target: int = int(args.target_raw)
				if (word(player,axis*2)&0xfff0) != (target&0xfff0):
					put(player,0x2c,0); put(player,0x30,0); slot.wait = axis+1; slot.target = target
					if _wait(slot,signals): slot.wait = null
					return
			_: error = "Unknown PC action: " + str(row.action); return
		if slot.wait != null or not error.is_empty(): return
	error = "Event instruction budget exhausted"

func _contact(id: String) -> bool:
	for boundary: Dictionary in boundaries:
		if boundary.id != id: continue
		var limits: Array = boundary.raw_bounds_inclusive
		return word(player,0) >= int(limits[0]) and word(player,0) <= int(limits[2]) and word(player,2) >= int(limits[1]) and word(player,2) <= int(limits[3])
	return false

func step(pad: int, signals: Dictionary) -> Dictionary:
	if initial.is_empty() or not error.is_empty(): return {"ok":false,"error":"Event core is not ready: "+error}
	if not [0,0x1000,0x2000,0x4000,0x8000,0x0200].has(pad) or not Movement._keys_match(signals,["resource_loaded","resource_playing","text_active"]):
		return {"ok":false,"error":"Invalid event input/device acknowledgement"}
	if not Movement.integer(signals.resource_loaded) or int(signals.resource_loaded) not in [0,1] or not Movement.integer(signals.resource_playing) or int(signals.resource_playing) < 0 or int(signals.resource_playing) > 255 or not signals.text_active is bool:
		return {"ok":false,"error":"Invalid device acknowledgement type or range"}
	var before: Dictionary = snapshot()
	update += 1; commands.clear(); requests.clear(); diagnostics = {"applied":true}
	put(player,6,word(player,6)&0xfffd); put(player,0x18,0); put(player,0x1a,0)
	if disabled != 255 and not (word(player,6)&4):
		var move: Dictionary = project(player); Movement._input_gate(move,pad); _write_movement(move)
	if _contact("stair_scene_boundary"):
		_restore(before); return {"ok":true,"applied":false,"reason":"test_boundary"}
	if (root == null or not root.active) and _contact("stair_script_boundary"):
		root = _slot(int(starts.entry),"root"); runs += 1
	_dispatch(root,signals)
	if word(player,6)&4: _dispatch(child,signals)
	else: _free()
	var target: Array = camera_target if fixed_camera else [Movement.signed16(word(player,0)),Movement.signed16(word(player,2))]
	for i: int in cameras.size(): cameras[i] = _camera(cameras[i],target)
	if word(decor,10)&4: _dispatch(child,signals)
	elif word(decor,0x1a): _decor_tick(decor,0,false)
	_decor_tick(ambient,1,false)
	if not error.is_empty():
		_restore(before); return {"ok":false,"error":error}
	if diagnostics.get("reason") == "test_boundary" or _contact("stair_scene_boundary"):
		_restore(before); return {"ok":true,"applied":false,"reason":"test_boundary"}
	return {"ok":true,"applied":true,"state":snapshot(),"error":""}
