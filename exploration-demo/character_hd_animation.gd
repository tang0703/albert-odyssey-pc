extends RefCounted
## A pure appearance selector. It never owns a clock or writes source state.
const Movement = preload("res://movement_core.gd")
const SourceAnimation = preload("res://character_animation_core.gd")
const DIRECTIONS: Dictionary = {0:"right",2:"down",4:"left",6:"up"}
const IDLE_IMAGES: Dictionary = {0:1,2:0,4:1,6:2}
const WALK_IMAGES: Dictionary = {0:9,2:5,4:9,6:13}

static func reject(reason: String) -> Dictionary:
	return {"ok":false,"error":reason}

static func select(state: Dictionary, render_phase: float = 0.0) -> Dictionary:
	if not is_finite(render_phase) or render_phase<0.0 or render_phase>=1.0:
		return reject("HD render phase must be in [0,1); pause must retain the phase.")
	for key: String in SourceAnimation.FIELDS:
		if not state.has(key) or not Movement.integer(state[key]) or state[key]<0 or state[key]>(1 << (int(SourceAnimation.FIELDS[key][1])*8))-1:
			return reject("Invalid source animation field: "+key)
	if int(state.animation_root)!=SourceAnimation.ANIMATION_ROOT or int(state.image_table_root)!=SourceAnimation.IMAGE_TABLE_ROOT or int(state.flags_word)!=9 or (int(state.status_word)&~(2|0x200))!=0x8180:
		return reject("Unsupported source actor configuration.")
	var heading: int = int(state.heading)
	if not DIRECTIONS.has(heading): return reject("HD supports only the four verified source directions.")
	var moving: bool = bool(int(state.status_word)&2)
	var cursor: int = int(state.animation_cursor)
	var timer: int = int(state.animation_timer)
	if int(state.animation_index)!=heading+(8 if moving else 0) or timer>9 or bool(int(state.render_flags_word)&1)!=(heading==0):
		return reject("Source heading, selection or mirrored direction is inconsistent.")
	var primary: int = -1
	var phase: int = -1
	var walk: int = -1
	if moving:
		if cursor not in [0,3,6,9] or int(state.animation_duration)!=10:
			return reject("Walking must use four original ten-update intervals.")
		primary=cursor/3
		if int(state.image_index)!=int(WALK_IMAGES[heading])+primary: return reject("Walking source image differs from the original primary pose.")
		phase=int(floor((float(timer)+render_phase)*3.0/10.0))
		walk=primary*3+phase
	else:
		# The first stopped update may retain timer 1..9. Source idle still wins.
		if cursor!=0 or int(state.animation_duration)!=1 or int(state.image_index)!=int(IDLE_IMAGES[heading]):
			return reject("Idle source cache is inconsistent.")
	var direction: String = DIRECTIONS[heading]
	var suffix: String = "walk-%02d"%walk if moving else "idle"
	return {"ok":true,"error":"","direction":direction,"action":"walk" if moving else "idle",
		"primary_index":primary,"subframe_index":phase,"walk_index":walk,
		"frame_id":"map001_player_hd/"+direction+"/"+suffix,
		"source_animation_index":int(state.animation_index),"source_animation_cursor":cursor,"source_animation_timer":timer,
		"render_phase":render_phase}
