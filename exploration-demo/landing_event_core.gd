extends "res://transition_core.gd"
## Bounded ninth-stage controller; old transfer entry and contracts unchanged.
## Canonical source contract is pinned after L1 and Python continuity checks.
const LANDING_EVENT_SHA: String = "4226836f9db95c244f7bfe6cbdd5a37fb49fecd9e482a66fc625533286269f32"
var landing_event_data: Dictionary = {}
var landing_instructions: Dictionary = {}
var landing_starts: Dictionary = {}
var event_slots: Dictionary = {}
var event_runs: int = 0
var event_completed: bool = false
var ambient_loops: int = 0
var event_commands: Array = []
var event_signals: Dictionary = {"text_active":false}

func configure_landing_event(data: Dictionary, transfer: Dictionary, old_data: Dictionary, movement_profile: Dictionary, flag_bytes: PackedByteArray, character: Dictionary, room: Dictionary) -> Dictionary:
	landing_event_data.clear(); landing_instructions.clear(); landing_starts.clear()
	if LANDING_EVENT_SHA.is_empty() or ActorAnimation._hash(JSON.stringify(data,"",true).to_utf8_buffer()) != LANDING_EVENT_SHA:
		return {"ok":false,"error":"Unapproved landing-event source contract"}
	var result: Dictionary = super.configure_transition(transfer,old_data,movement_profile,flag_bytes,character,room)
	if not result.ok: return result
	for name: String in data.programs:
		var rows: Array = data.programs[name]
		if rows.is_empty(): return {"ok":false,"error":"Empty required landing-event program"}
		landing_starts[name] = int(rows[0].offset)
		for row: Dictionary in rows:
			if landing_instructions.has(int(row.offset)): return {"ok":false,"error":"Duplicate event instruction"}
			landing_instructions[int(row.offset)] = row.duplicate(true)
	if landing_instructions.size() != 46: return {"ok":false,"error":"Incomplete landing-event programs"}
	landing_event_data = data.duplicate(true)
	reset()
	return {"ok":true}

func reset() -> void:
	super.reset()
	event_slots.clear(); event_runs = 0; event_completed = false; ambient_loops = 0; event_commands.clear()
	event_signals = {"text_active":false}

func event_state() -> Dictionary:
	# Reset generations are PC transport tokens, not source script state.
	var semantic_requests: Array = requests.duplicate(true)
	for request: Dictionary in semantic_requests: request.erase("generation")
	return {"story":story,"disabled":disabled,"weapon":weapon,"item_count":item_count,"attack":attack,
		"fixed":fixed_camera,"target":camera_target.duplicate() if camera_target != null else null,"speed":camera_speed,
		"slots":event_slots.duplicate(true),"runs":event_runs,"completed":event_completed,"ambient_loops":ambient_loops,
		"commands":event_commands.duplicate(true),"requests":semantic_requests}

func snapshot() -> Dictionary:
	var result: Dictionary = super.snapshot()
	result.landing_event = {"slots":event_slots.duplicate(true),"runs":event_runs,"completed":event_completed,
		"ambient_loops":ambient_loops,"commands":event_commands.duplicate(true),"arrival_actor":arrival_actor.hex_encode(),
		"objects":landing_objects.duplicate(true)}
	return result

func _restore(value: Dictionary) -> void:
	super._restore(value)
	if value.has("landing_event"):
		var state: Dictionary = value.landing_event
		event_slots = state.slots.duplicate(true); event_runs = int(state.runs); event_completed = bool(state.completed)
		ambient_loops = int(state.ambient_loops); event_commands = state.commands.duplicate(true)
		arrival_actor = str(state.arrival_actor).hex_decode(); landing_objects.assign(state.objects.duplicate(true))

func transition_snapshot() -> Dictionary:
	var result: Dictionary = super.transition_snapshot()
	result.event_state = event_state()
	return result

func legal_equipment_state() -> bool:
	if story != "0f": return super.legal_equipment_state()
	return scene_id == 7 and event_runs == 1 and ((weapon == 255 and attack == 10 and item_count == 1) or (weapon == 27 and attack == 15 and item_count == 0))

func equipment(action: String) -> Dictionary:
	if story != "0f": return super.equipment(action)
	if not landing_event_data.get("post_event_equipment_verified",false):
		return {"ok":false,"error":"Post-event equipment source gate has not passed"}
	if not legal_equipment_state() or disabled != 0 or stage != "landing" or not event_completed:
		return {"ok":false,"error":"Equipment unavailable during event or boundary"}
	if action not in ["equip","remove"]: return {"ok":false,"error":"Unknown equipment operation"}
	if action == "equip":
		if weapon == 27: return {"ok":true,"changed":false,"reason":"already_equipped"}
		weapon = 27; item_count -= 1; attack = 15
	else:
		if weapon == 255: return {"ok":true,"changed":false,"reason":"empty_slot"}
		weapon = 255; item_count += 1; attack = 10
	return {"ok":true,"changed":true,"state":snapshot()}

func scene_resources_ready(response_generation: int, request_id: String) -> Dictionary:
	var result: Dictionary = super.scene_resources_ready(response_generation,request_id)
	if result.get("accepted",false):
		for index: Variant in landing_event_data.landing_query_indices: verified[int(index)] = true
	return result

func _npc_decode(advance: bool, terminal: bool = false) -> bool:
	var selector: String = str(word(arrival_actor,0x36))
	if not landing_event_data.actor_program.sequences.has(selector): error = "Unknown event NPC animation"; return false
	var sequence: Array = landing_event_data.actor_program.sequences[selector]
	if advance:
		put(arrival_actor,0x30,word(arrival_actor,0x30)+1)
		if word(arrival_actor,0x30) >= word(arrival_actor,0x32):
			put(arrival_actor,0x30,0); put(arrival_actor,0x2c,word(arrival_actor,0x2c)+3)
			put(arrival_actor,6,word(arrival_actor,6)|0x80)
	var cursor: int = word(arrival_actor,0x2c)
	if cursor % 3 != 0 or cursor >= sequence.size(): error = "Invalid event NPC cursor"; return false
	if int(sequence[cursor]) == 0:
		put(arrival_actor,0x2c,0)
		if terminal:
			put(arrival_actor,6,word(arrival_actor,6)&0xfeff); return true
		put(arrival_actor,6,word(arrival_actor,6)|0x100); cursor = 0
	if cursor+2 >= sequence.size() or int(sequence[cursor+2]) not in [0,4]: error = "Unknown NPC frame effect"; return false
	var image: int = int(sequence[cursor+1])
	if not landing_event_data.actor_program.images.has(str(image)): error = "Missing NPC image pointer"; return false
	put(arrival_actor,0x32,int(sequence[cursor])); put(arrival_actor,0x34,image)
	put(arrival_actor,0x14,(word(arrival_actor,0x14)&0xfffe)|(1 if int(sequence[cursor+2])&4 else 0))
	put_long(arrival_actor,0x5c,int(landing_event_data.actor_program.images[str(image)]))
	return false

func _npc_forced(axis: int, target: int) -> bool:
	var position: int = word(arrival_actor,axis*2)
	var delta: int = Movement.signed16(target-position)
	var speed: int = Movement.SPEED_COMPONENTS[word(arrival_actor,0x24)][0]
	var heading: int = (4 if axis == 0 else 6) if delta < 0 else (0 if axis == 0 else 2)
	var amount: int = maxi(delta,-speed) if delta < 0 else mini(delta,speed)
	put(arrival_actor,0x26,heading); put(arrival_actor,0x18,amount if axis == 0 else 0); put(arrival_actor,0x1a,amount if axis == 1 else 0)
	put(arrival_actor,0x36,4+heading/2); _npc_decode(true); put(arrival_actor,axis*2,position+amount)
	var done: bool = (word(arrival_actor,axis*2)&0xfff0) == (target&0xfff0)
	if done: put(arrival_actor,6,word(arrival_actor,6)&0xfeff); put(arrival_actor,0x18+axis*2,0)
	return done

func _attach_landing(program: String, actor_id: int) -> void:
	var owner: String = "player" if actor_id == 0 else "laia"
	for entry: Dictionary in event_slots.values():
		if entry.active and entry.owner == owner: error = "Occupied event actor"; return
	for slot: int in range(1,32):
		var key: String = str(slot)
		if not event_slots.has(key) or not event_slots[key].active:
			event_slots[key] = _slot(int(landing_starts[program]),owner)
			var raw: PackedByteArray = player if actor_id == 0 else arrival_actor
			put(raw,6,word(raw,6)|4); put(raw,0x38,slot); return
	error = "No event actor slot available"

func _wait_landing(slot: Dictionary) -> bool:
	match int(slot.wait):
		0:
			var old: int = int(slot.arg); slot.arg = (old-1)&65535; return old == 0
		1,2: return _npc_forced(int(slot.wait)-1,int(slot.target))
		4: return _npc_decode(true,true)
		8: return not bool(event_signals.text_active)
		9: return not (word(arrival_actor,6)&4)
		11:
			var done: bool = not int(cameras[0].dx) and not int(cameras[0].dy)
			if done: fixed_camera = false; camera_speed = 128
			return done
		_: error = "Unknown landing-event wait"; return false

func _dispatch_landing(slot_id: int) -> void:
	var key: String = str(slot_id)
	if not event_slots.has(key) or not event_slots[key].active: return
	var slot: Dictionary = event_slots[key]
	if slot.wait != null:
		if _wait_landing(slot): slot.wait = null
		return
	for _budget: int in 32:
		if not landing_instructions.has(int(slot.pc)): error = "Unknown landing-event instruction"; return
		var instruction: Dictionary = landing_instructions[int(slot.pc)]
		event_commands.append([slot_id,int(slot.pc),int(instruction.opcode)])
		slot.pc = int(slot.pc)+int(instruction.span)
		var args: Dictionary = instruction.args
		match str(instruction.action):
			"end":
				slot.active = false
				if slot.owner != "root":
					var raw: PackedByteArray = player if slot.owner == "player" else arrival_actor
					put(raw,6,word(raw,6)&0xfffb)
					if slot.owner == "laia": put(raw,0x2a,2)
				return
			"branch_story":
				if story not in ["07","0f"]: error = "Illegal landing story branch"; return
				slot.pc = int(args.if_set if story == "0f" else args.if_clear)
			"set_story_bit":
				if story != "07": error = "Landing event already committed"; return
				story = "0f"
			"lock_control":
				disabled = 255; fade = 3; event_runs += 1
				put(player,0x2c,0); put(player,0x36,word(player,0x26))
			"unlock_control":
				disabled = 0; event_completed = true; requests.append({"type":"landing_event_completed"})
			"attach_actor": _attach_landing(str(args.program),int(args.actor_id))
			"wait_actor":
				if word(arrival_actor,6)&4: slot.wait = 9
			"camera_target": fixed_camera = true; camera_speed = int(args.speed_raw); camera_target = [int(args.x_raw),int(args.y_raw)]
			"camera_follow_player": fixed_camera = false
			"wait_camera": slot.wait = 11; slot.arg = 2
			"dialogue": requests.append({"type":"dialogue","id":str(args.id)}); slot.wait = 8
			"wait_updates": slot.wait = 0; slot.arg = int(args.count)
			"actor_pose":
				if slot.owner == "player": _pose(int(args.heading))
				else:
					for offset: int in [0x30,0x2c,0x18,0x1a]: put(arrival_actor,offset,0)
					put(arrival_actor,0x26,int(args.heading)); put(arrival_actor,0x36,int(args.heading)/2); _npc_decode(false)
				slot.wait = 0; slot.arg = 1
			"actor_speed": put(arrival_actor,0x24,int(args.index))
			"actor_move_axis":
				var axis: int = int(args.axis)
				var target: int = int(args.target_raw)
				if (word(arrival_actor,axis*2)&0xfff0) != (target&0xfff0):
					put(arrival_actor,0x2c,0); put(arrival_actor,0x30,0); slot.wait = axis+1; slot.target = target
					if _wait_landing(slot): slot.wait = null
					return
			"actor_animation":
				put(arrival_actor,0x36,int(args.index)); put(arrival_actor,0x30,0); put(arrival_actor,0x2c,0)
				put(arrival_actor,6,word(arrival_actor,6)&0xfeff); _npc_decode(false); slot.wait = 4
			"jump": slot.pc = int(args.target); ambient_loops += 1
			_: error = "Unknown landing-event operation"; return
		if not error.is_empty() or slot.wait != null: return
	error = "Landing-event instruction budget exhausted"

func _landing_camera(state: Dictionary) -> Dictionary:
	var result: Dictionary = state.duplicate(true)
	result.display_x = state.x; result.display_y = state.y; result.dx = 0; result.dy = 0
	for axis: int in 2:
		var key: String = "x" if axis == 0 else "y"
		var center: int = 0 if fixed_camera else (0xa80 if axis == 0 else 0x780)
		var margin: int = 0 if fixed_camera else 0x200
		var upper: int = Movement.signed16(int(state[key])+center+margin)
		var lower: int = Movement.signed16(int(state[key])+center-margin)
		var value: int = int(camera_target[axis]) if fixed_camera else Movement.signed16(word(player,axis*2))
		if value > upper:
			var delta: int = mini(camera_speed,Movement.signed16(value-upper))
			var proposed: int = Movement.signed16(int(state[key])+delta)
			if proposed > int(transition_data.camera_limits_raw[axis+2]): proposed = int(transition_data.camera_limits_raw[axis+2]); delta = 0
			result[key] = proposed; result["d"+key] = delta
		if value < lower:
			var delta: int = mini(camera_speed,Movement.signed16(lower-value))
			var proposed: int = Movement.signed16(int(result[key])-delta)
			if proposed < int(transition_data.camera_limits_raw[axis]): proposed = int(transition_data.camera_limits_raw[axis]); delta = 0
			result[key] = proposed; result["d"+key] = -delta
	return result

func _landing_tick(pad: int) -> void:
	put(player,6,word(player,6)&0xfffd); put(player,0x18,0); put(player,0x1a,0)
	if fade in [2,3] and disabled == 0:
		var move: Dictionary = project(player); Movement._input_gate(move,pad); _write_movement(move)
	var b: Array = landing_event_data.trigger.bounds_raw
	if stage == "landing" and word(player,0) >= int(b[0]) and word(player,0) <= int(b[2]) and word(player,2) >= int(b[1]) and word(player,2) <= int(b[3]):
		if not event_slots.has("0") or not event_slots["0"].active: event_slots["0"] = _slot(int(landing_starts.entry),"root")
	_dispatch_landing(0)
	if word(player,6)&4: _dispatch_landing(word(player,0x38))
	else: _free()
	if not error.is_empty() or diagnostics.get("reason") == "test_boundary": return
	var bounds: Array = landing_event_data.viewport_world
	var x: int = Movement.signed16(word(player,0))
	var y: int = Movement.signed16(word(player,2))
	if x < int(bounds[0])*16 or x >= int(bounds[2])*16 or y < int(bounds[1])*16 or y >= int(bounds[3])*16:
		diagnostics.reason = "test_boundary"; return
	if word(arrival_actor,6)&4: _dispatch_landing(word(arrival_actor,0x38))
	elif word(arrival_actor,0x2a) == 1: _npc_decode(true)
	for i: int in cameras.size(): cameras[i] = _landing_camera(cameras[i])
	for i: int in landing_objects.size(): _object_tick(landing_objects[i],transition_data.object_programs[i])

func step(pad: int, signals: Dictionary, pressed: int = 0) -> Dictionary:
	if landing_event_data.is_empty(): return {"ok":false,"error":"Landing-event source gate not configured"}
	if stage not in ["landing","boundary"]:
		event_commands.clear(); event_signals = signals.duplicate(true)
		return super.step(pad,signals,pressed)
	if not legal_equipment_state() or not error.is_empty(): return {"ok":false,"error":"Invalid landing-event state: "+error}
	if not [0,0x1000,0x2000,0x4000,0x8000,0x0200,0x0400].has(pad) or not signals.get("text_active") is bool:
		return {"ok":false,"error":"Invalid landing-event input"}
	if stage == "boundary": return {"ok":true,"applied":false,"state":snapshot()}
	event_commands.clear(); event_signals = signals.duplicate(true)
	commands.clear(); requests.clear(); diagnostics = {"applied":true}
	for contact: Dictionary in transition_data.contacts:
		if int(contact.get("script_offset",0)) == 0x2c17: continue
		var b: Array = contact.bounds_raw
		if word(player,0) >= int(b[0]) and word(player,0) <= int(b[2]) and word(player,2) >= int(b[1]) and word(player,2) <= int(b[3]):
			stage = "boundary"; requests = [{"type":"test_boundary","reason":contact.policy}]
			return {"ok":true,"applied":false,"reason":"test_boundary","state":snapshot()}
	var before: Dictionary = snapshot()
	var before_fade: int = fade
	_landing_tick(pad)
	if diagnostics.get("reason") == "test_boundary":
		_restore(before); fade = before_fade
		return {"ok":true,"applied":false,"reason":"test_boundary","state":snapshot()}
	if not error.is_empty(): return {"ok":false,"error":error}
	return {"ok":true,"applied":true,"state":snapshot()}
