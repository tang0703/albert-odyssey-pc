extends "res://character_main.gd"
## Room extension keeps the original three bundles byte-identical.
const RoomBundle = preload("res://room_loader.gd")
const RoomMovement = preload("res://room_movement_core.gd")
const RoomCamera = preload("res://room_camera_core.gd")
const RoomDecorations = preload("res://room_decoration_core.gd")
const RoomPriority = preload("res://room_priority.gdshader")
var room_bundle: Dictionary = {}
var room_camera: RefCounted
var room_decorations: RefCounted
var camera_states: Array = []
var decoration_states: Array = []
var displayed_decorations: Array = []
var room_queue: Array[Dictionary] = []

func _ready() -> void:
	var directory: String = RoomBundle.default_directory()
	var scene_directory: String = Bundle.default_directory()
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--room-package="): directory = arg.trim_prefix("--room-package=")
		if arg.begins_with("--scene-package="): scene_directory = arg.trim_prefix("--scene-package=")
	bundle_override = Bundle.load_bundle(scene_directory)
	if bundle_override.get("ok",false):
		room_bundle = RoomBundle.load_bundle(directory,bundle_override.flags)
		if room_bundle.get("ok",false):
			# Mutate an in-memory view only, never the existing package files.
			bundle_override = bundle_override.duplicate(true)
			bundle_override.profile = room_bundle.data.movement_profile.duplicate(true)
			bundle_override.traces = room_bundle.data.traces.duplicate(true)
			var labels: Dictionary = {"interior":"室內通路","contacts":"家具接觸與持續壓牆","perimeter":"外圍牆面","visual-west":"西側鏡頭與遮擋","visual-east":"東側鏡頭與遮擋"}
			for trace: Dictionary in bundle_override.traces: trace.label = labels[trace.id]
			room_camera = RoomCamera.new()
			room_camera.configure(room_bundle.data.camera_profile)
			room_decorations = RoomDecorations.new()
			room_decorations.configure(room_bundle.data.visuals.programs)
		else: startup_error = str(room_bundle.get("error","室內包遭拒。"))
	super._ready()
	if startup_error.is_empty():
		core = RoomMovement.new()
		var configured: Dictionary = core.configure_room(bundle.profile,bundle.flags,room_bundle.data.boundaries)
		if not configured.get("ok",false): startup_error = str(configured.error); paused = true
		priority_material.shader = RoomPriority
		priority_material.set_shader_parameter("source_foreground",room_bundle.textures["foreground.png"])
		get_window().title = "MAP001 同室內探索與鏡頭驗證"
		reset_state()
		refresh()

func workbench_title() -> String:
	return "MAP001  /  同室內探索"

func workbench_subtitle() -> String:
	return "原作鏡頭 · 來源碰撞 · 三種外觀"

func reset_state() -> void:
	if room_bundle.get("ok",false) and room_decorations != null:
		camera_states = room_bundle.data.initial_cameras.duplicate(true)
		decoration_states = room_decorations.initial_states()
		displayed_decorations = decoration_states.duplicate(true)
		room_queue.clear()
		var first: Dictionary = {"cameras":camera_states.duplicate(true),"decorations":decoration_states.duplicate(true)}
		for n: int in 3: room_queue.append(first.duplicate(true))
		if not bundle.is_empty(): bundle.data.camera = [int(camera_states[0].x)/16,int(camera_states[0].y)/16]
	super.reset_state()

func prepare_update_presentation(result: Dictionary) -> String:
	if not result.diagnostics.get("applied",false): return ""
	var animated: Dictionary = animator.step_after_movement(animation_state,result)
	if not animated.get("ok",false): return str(animated.get("error","動畫更新失敗。"))
	var incoming: Dictionary = result.state.duplicate(true)
	incoming.merge(animated.state,true)
	var next_actor: Dictionary = presentation_queue[0]
	for actor: Dictionary in [incoming,next_actor]:
		var original: Dictionary = CharacterBundle.lookup(character_bundle,actor)
		if not original.get("ok",false): return str(original.error)
		var error: String = validate_hd_interval(actor)
		if not error.is_empty(): return error
	var next_cameras: Array = []
	for state_value: Dictionary in camera_states:
		var moved: Dictionary = room_camera.step(state_value,{"x_word":result.state.x_word,"y_word":result.state.y_word})
		if not moved.get("ok",false): return str(moved.error)
		next_cameras.append(moved.state)
	var decorated: Dictionary = room_decorations.step(decoration_states)
	if not decorated.get("ok",false): return str(decorated.error)
	var next_display: Dictionary = room_queue[0]
	for list_value: Array in [decorated.states,next_display.decorations]:
		for n: int in 2:
			var key: String = "%d:%d" % [n+6,list_value[n].image]
			if not room_bundle.frames.has(key) or not room_bundle.frames[key].texture is Texture2D or not is_instance_valid(room_bundle.frames[key].texture): return "必要装飾物圖片缺失。"
	if replay_mode:
		var record: Dictionary = bundle.traces[route_index].updates[trace_cursor]
		if incoming != record.actor_expected: return "玩家動畫與原作軌跡不一致。"
		if record.camera_expected != null and next_cameras != record.camera_expected: return "鏡頭與原作軌跡不一致。"
	# Commit the complete logical/presentation update only after every check.
	animation_state = animated.state
	presentation_queue.append(incoming)
	displayed_actor = presentation_queue.pop_front()
	room_queue.append({"cameras":next_cameras.duplicate(true),"decorations":decorated.states.duplicate(true)})
	var shown: Dictionary = room_queue.pop_front()
	camera_states = next_cameras
	decoration_states = decorated.states
	displayed_decorations = shown.decorations
	bundle.data.camera = [int(shown.cameras[0].x)/16,int(shown.cameras[0].y)/16]
	presentation_updates += 1
	return ""

func presentation_order(actor: Dictionary, camera: Vector2) -> Dictionary:
	if not room_bundle.get("ok",false) or displayed_decorations.size() != 2 or camera.x < 512 or camera.x > 640 or camera.y < 1536 or camera.y > 1568: return {"ok":false,"error":"室內演出範圍或狀態無效。"}
	# Camera changes every object's bucket by the same integer offset. Preserve
	# the exact occupied-bucket rule, then append source priority-255 objects.
	var buckets: Dictionary = {}
	var entries: Array = character_bundle.props.duplicate()
	entries.append({"kind":"player","sprite_priority":2})
	for value: Dictionary in entries:
		var entry: Dictionary = value.duplicate()
		if entry.get("kind","") != "player": entry.kind = "prop"
		var y_raw: int = Movement.signed16(int(actor.y_word)) if entry.kind == "player" else int(entry.world_xy_raw[1])
		var bucket: int = Movement.divide16(y_raw-int(camera.y)*16)+256
		if bucket < 40 or bucket > 700: return {"ok":false,"error":"超出來源排序表範圍。"}
		while buckets.has(bucket) and bucket < 767: bucket += 1
		if buckets.has(bucket): return {"ok":false,"error":"來源排序表已滿。"}
		buckets[bucket] = entry
	var keys: Array = buckets.keys()
	keys.sort()
	var ordered: Array[Dictionary] = []
	for key: int in keys: ordered.append(buckets[key])
	for n: int in 2:
		var key: String = "%d:%d" % [n+6,displayed_decorations[n].image]
		if not room_bundle.frames.has(key): return {"ok":false,"error":"缺少裝飾物影格。"}
		ordered.append(room_bundle.frames[key])
	return {"ok":true,"entries":ordered}

func draw_background(canvas: Control, whole: Rect2) -> void:
	if not room_bundle.get("ok",false): return
	canvas.draw_texture_rect_region(room_bundle.textures["background.png"],whole,Rect2(source_camera()-Vector2(512,1536),Vector2(320,224)))

func sync_source_layers() -> void:
	if priority_material != null and not bundle.is_empty(): priority_material.set_shader_parameter("camera_offset",source_camera()-Vector2(512,1536))
	super.sync_source_layers()

func draw_map(canvas: Control) -> void:
	if not room_bundle.get("ok",false) or state.is_empty(): return
	if not show_overlay:
		draw_background(canvas,Rect2(Vector2.ZERO,canvas.size))
		if appearance_mode == "marker": draw_player(canvas,(world_position(state)-source_camera())*canvas.size.x/320.0,canvas.size.x/320.0)
		return
	super.draw_map(canvas)
	var zoom: float = canvas.size.x/320.0
	for boundary: Dictionary in room_bundle.data.boundaries:
		var bounds: Array = boundary.raw_bounds_inclusive
		var position := Vector2(float(bounds[0]),float(bounds[1]))/16.0-source_camera()
		var size := Vector2(float(bounds[2]-bounds[0]+16),float(bounds[3]-bounds[1]+16))/16.0
		canvas.draw_rect(Rect2(position*zoom,size*zoom),Color(1.0,0.5,0.2,0.7),false,maxf(1.0,zoom*0.3))

func refresh() -> void:
	super.refresh()
	if domain_label != null and room_bundle.get("ok",false):
		domain_label.text = "MAP001 同一室內 · 613 個已驗證查表格 · 原作鏡頭 · 出口為測試邊界"
		if not camera_states.is_empty(): position_label.text += "\n鏡頭 %.0f, %.0f　裝飾物同步播放" % [source_camera().x,source_camera().y]

func qa_identity() -> Dictionary:
	var identity: Dictionary = super.qa_identity()
	identity.schema = "ao_pc_room_ui_qa_v1"
	identity.room_manifest_sha256 = room_bundle.get("manifest_sha256","")
	identity.room_images_preloaded = room_bundle.get("preloaded",false)
	return identity
