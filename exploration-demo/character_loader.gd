extends RefCounted
## Only a separately pinned source package can supply original player images.
const Common = preload("res://package_loader.gd")
const Movement = preload("res://movement_core.gd")
const AnimationCore = preload("res://character_animation_core.gd")
const SCHEMA: String = "ao_pc_character_bundle_v1"
const SOURCES: Dictionary = {"PARTY0.PTY":"1f34fb2ddfc726be55348241fe51703b28d752615c8405c18950d95add2e9dcb",
	"MAP001.TWN":"8216f3dfd7ae8ca7fb8cee0129f7431de7f72939e75b22be1a74f030bf4535e9",
	"TWN.BIN":"fa6596ad52b4980328a495f887b1aced6b9bc41ce48e47ebfd9081c9b48e1be6"}
const DELAY: Dictionary = {"executed_actor_sample_lag":1,"executed_body_source_sample_lag":2,
	"executed_body_camera_sample_lag":0,"draw_to_presented_video_lag":1,"presented_body_source_sample_lag":3}
const SEED_SHA: String = "72d9fa56fbf525dbb71ae3a21d8e3aaa45f23b7711bfdce2b95d6c6472776b54"
const SCOPE: String = "Original player and six static props with source foreground; objects 6/7 and shadow omitted"
const SORTING: Dictionary = {"bucket_count":768,"initial_bucket_min":40,"initial_bucket_max":700,"bucket_bias":256,
	"divisor":16,"objects_before_actor":true,"collision":"next_free_bucket","priority_limit":256,
	"actor_slot":0,"actor_command_priority":10,"actor_sprite_priority":2,"actor_y_sorted":true}
const FOREGROUND_RULE: Dictionary = {"sprite_priority":2,"foreground_priority":3,"layers":[0,1],"equal_background_priority_winner":0}

static func expected_props() -> Array[Dictionary]:
	var world: Array = [[12800,27904],[10880,26368],[11424,27136],[12032,27136],[12032,27920],[12112,28096]]
	var anchors: Array = [[14,19],[24,40],[21,24],[21,24],[8,40],[8,32]]
	var dimensions: Array = [[24,24],[48,40],[32,24],[32,24],[16,24],[16,16]]
	var result: Array[Dictionary] = []
	for slot: int in 6:
		result.append({"id":"object_%d"%slot,"slot":slot,"file":"prop-%02d.png"%slot,"world_xy_raw":world[slot],
			"anchor":anchors[slot],"dimensions":dimensions[slot],"y_sorted":true,"command_priority":10,
			"sprite_priority":2 if slot<4 else 3,"render_flags":18 if slot<4 else 19})
	return result

static func default_directory() -> String:
	return OS.get_executable_path().get_base_dir().path_join("character") if not OS.has_feature("editor") else ProjectSettings.globalize_path("res://generated/character")

static func rejected(reason: String) -> Dictionary:
	return {"ok":false,"error":reason}

static func _hash_valid(value: Variant) -> bool:
	if not value is String or value.length() != 64: return false
	for index: int in 64:
		if not value.substr(index,1) in "0123456789abcdef": return false
	return true

static func expected_frames() -> Array[Dictionary]:
	var frames: Array[Dictionary] = []
	for direction: String in ["down","left","right","up"]:
		var heading: int = {"down":2,"left":4,"right":0,"up":6}[direction]
		for pose: int in range(-1,4):
			var moving: bool = pose >= 0
			var suffix: String = "walk-%02d" % pose if moving else "idle"
			var image_index: int = int({"down":5,"left":9,"right":9,"up":13}[direction]) + pose if moving else {"down":0,"left":1,"right":1,"up":2}[direction]
			frames.append({"id":"map001_player/"+direction+"/"+suffix,"direction":direction,"heading":heading,
				"action":"walk" if moving else "idle","primary_index":pose if moving else null,
				"animation_index":heading+(8 if moving else 0),"animation_cursor":pose*3 if moving else 0,
				"duration_updates":10 if moving else 1,"image_index":image_index,"baked_mirror_x":direction=="right",
				"anchor":[16,36 if direction=="up" and moving else 35],"dimensions":[32,40],"file":direction+"-"+suffix+".png"})
	return frames

static func load_bundle(directory: String, scene_manifest_sha256: String) -> Dictionary:
	var pin: Variant = Common.read_json("res://character-pin.json")
	if not pin is Dictionary or not Movement._keys_match(pin,["schema","manifest_sha256","scene_manifest_sha256"]) or pin.schema != "ao_pc_character_bundle_pin_v1":
		return rejected("缺少核准角色包識別，請先完成角色顯示驗證與建置。")
	if pin.scene_manifest_sha256 != scene_manifest_sha256:
		return rejected("角色包與已載入場景版本不同。")
	return load_verified(directory,str(pin.manifest_sha256),scene_manifest_sha256)

static func load_verified(directory: String, manifest_sha256: String, scene_manifest_sha256: String) -> Dictionary:
	# Explicit trusted pins support isolated verification. Runtime uses load_bundle.
	if not _hash_valid(manifest_sha256) or not _hash_valid(scene_manifest_sha256): return rejected("無效的角色或場景核准雜湊。")
	var manifest: String = directory.path_join("package.json")
	if not FileAccess.file_exists(manifest) or FileAccess.get_sha256(manifest) != manifest_sha256:
		return rejected("角色包不存在或已被修改。")
	var data: Variant = Common.read_json(manifest)
	if not data is Dictionary or not Movement._keys_match(data,["schema","character_id","source_local_only","scene_manifest_sha256","camera","viewport","files","source","presentation"]):
		return rejected("角色包欄位不完整或不受支援。")
	if data.schema != SCHEMA or data.character_id != "map001_player" or data.source_local_only != true or data.scene_manifest_sha256 != scene_manifest_sha256 or data.camera != [544,1536] or data.viewport != [320,224]:
		return rejected("角色識別、鏡頭或場景版本不符。")
	if not data.presentation is Dictionary or not Movement._keys_match(data.presentation,["state","delay_profile","scope"]) or data.presentation.state != "source_draw_and_visibility_verified" or data.presentation.delay_profile != DELAY or data.presentation.scope != SCOPE:
		return rejected("角色實際顯示時序或可見性尚未通過驗證。")
	var source: Variant = data.source
	if not source is Dictionary or not Movement._keys_match(source,["seed_sha256","source_files","reference_art_manifest_sha256","animation_validation_sha256","presentation_reports","capture_manifests","presentation_index_sha256","foreground_manifest_sha256","props_manifest_sha256","draw_order_validation_sha256","map_v1n_sha256"]):
		return rejected("缺少角色來源證據。")
	if source.seed_sha256 != SEED_SHA or source.source_files != SOURCES or not _hash_valid(source.reference_art_manifest_sha256) or not _hash_valid(source.animation_validation_sha256):
		return rejected("角色來源版本未經核准。")
	for key: String in ["presentation_index_sha256","foreground_manifest_sha256","props_manifest_sha256","draw_order_validation_sha256"]:
		if not _hash_valid(source[key]): return rejected("缺少來源圖層驗證識別。")
	if source.map_v1n_sha256 != "dcad16cc0fe4f843fbb3eba134adf264c66352ab590e4ace14381cd0b6fbf9a4": return rejected("未知的家具貼圖來源。")
	if not source.presentation_reports is Dictionary or not source.capture_manifests is Dictionary or source.presentation_reports.size() != 4 or source.capture_manifests.size() != 12:
		return rejected("缺少四條顯示路線或十二次原作採樣證據。")
	var seen: Dictionary = {}
	for route: String in ["cardinal","corners","open","release"]:
		if not _hash_valid(source.presentation_reports.get(route)): return rejected("顯示報告識別無效。")
		for letter: String in ["a","b","c"]:
			var capture: Variant = source.capture_manifests.get(route+"-"+letter)
			if not _hash_valid(capture) or seen.has(capture): return rejected("原作採樣識別無效或重複。")
			seen[capture]=true
	var rows: Array[Dictionary] = expected_frames()
	var payloads: Array[String] = ["profile.json","animation-bank.bin","image-table.bin","appearances.json","layers.json","nbg-priority-foreground.png"]
	for frame: Dictionary in rows: payloads.append(frame.file)
	for prop: Dictionary in expected_props(): payloads.append(prop.file)
	if not data.files is Dictionary or not Movement._keys_match(data.files,payloads): return rejected("角色檔案清單不完整。")
	var expected: PackedStringArray = PackedStringArray(payloads+["package.json"])
	expected.sort()
	var present: PackedStringArray = DirAccess.get_files_at(directory)
	present.sort()
	if present != expected or not DirAccess.get_directories_at(directory).is_empty(): return rejected("角色包內存在未核准或缺失檔案。")
	var raw: Dictionary = {}
	for name: String in payloads:
		var identity: Variant = data.files[name]
		if not identity is Dictionary or not Movement._keys_match(identity,["bytes","sha256"]) or not Movement.integer(identity.bytes) or identity.bytes <= 0 or not _hash_valid(identity.sha256):
			return rejected("角色檔案識別不完整："+name)
		raw[name]=FileAccess.get_file_as_bytes(directory.path_join(name))
		if raw[name].size() != identity.bytes or AnimationCore._hash(raw[name]) != identity.sha256:
			return rejected("角色檔案截斷或雜湊不符："+name)
	var profile: Variant = Common.normalize_integers(JSON.parse_string(raw["profile.json"].get_string_from_utf8()))
	var appearances: Variant = Common.normalize_integers(JSON.parse_string(raw["appearances.json"].get_string_from_utf8()))
	if not profile is Dictionary or not appearances is Dictionary or appearances != {"schema":"ao_pc_character_appearances_v1","character_id":"map001_player","frames":rows}:
		return rejected("動畫設定、腳底錨點或方向映射不受支援。")
	var core := AnimationCore.new()
	var configured: Dictionary = core.configure(profile,raw["animation-bank.bin"],raw["image-table.bin"])
	if not configured.ok: return rejected("動畫來源設定遭拒："+str(configured.error))
	var layers: Variant = Common.normalize_integers(JSON.parse_string(raw["layers.json"].get_string_from_utf8()))
	if not layers is Dictionary or not Movement._keys_match(layers,["schema","foreground","props","sorting","omitted_object_slots","shadow_omitted"]):
		return rejected("來源圖層設定不完整。")
	if layers.schema != "ao_pc_character_layers_v1" or layers.props != expected_props() or layers.sorting != SORTING or layers.omitted_object_slots != [6,7] or layers.shadow_omitted != true:
		return rejected("家具或深度排序設定未經核准。")
	if not layers.foreground is Dictionary or not Movement._keys_match(layers.foreground,["file","dimensions","rule","rgba_sha256"]) or layers.foreground.file != "nbg-priority-foreground.png" or layers.foreground.dimensions != [320,224] or layers.foreground.rule != FOREGROUND_RULE or not _hash_valid(layers.foreground.rgba_sha256):
		return rejected("來源背景優先度資料未經核准。")
	var frames: Dictionary = {}
	var textures: Dictionary = {}
	var images: Dictionary = {}
	var pixels: Dictionary = {}
	for frame: Dictionary in rows:
		var decoded: Dictionary = _decode_image(raw[frame.file],Vector2i(32,40))
		if not decoded.ok:
			return rejected("原作姿勢圖片格式或尺寸不符："+frame.file)
		var key: String = "%d:%d" % [frame.animation_index,frame.animation_cursor]
		frames[key]=frame.duplicate(true)
		textures[key]=decoded.texture
		images[key]=decoded.image
		pixels[key]=decoded.pixels
	var props: Array[Dictionary] = []
	for prop: Dictionary in layers.props:
		var decoded: Dictionary = _decode_image(raw[prop.file],Vector2i(prop.dimensions[0],prop.dimensions[1]))
		if not decoded.ok: return rejected("家具PNG格式或透明度不符："+prop.file)
		var loaded: Dictionary = prop.duplicate(true)
		loaded.merge({"texture":decoded.texture,"image":decoded.image,"pixels":decoded.pixels})
		props.append(loaded)
	var foreground: Dictionary = _decode_image(raw["nbg-priority-foreground.png"],Vector2i(320,224))
	if not foreground.ok or AnimationCore._hash(foreground.pixels) != layers.foreground.rgba_sha256:
		return rejected("來源前景PNG像素或透明度不符。")
	var presentation: Dictionary = data.presentation.duplicate(true)
	presentation.actor_to_video_delay_updates = int(presentation.delay_profile.presented_body_source_sample_lag)
	return {"ok":true,"error":"","data":data,"profile":profile,"animation_bank":raw["animation-bank.bin"],
		"image_table":raw["image-table.bin"],"frames":frames,"textures":textures,"presentation":presentation,
		"images":images,"pixels":pixels,"props":props,"layers":layers,"foreground_texture":foreground.texture,
		"foreground_image":foreground.image,"foreground_pixels":foreground.pixels}

static func _decode_image(raw: PackedByteArray, dimensions: Vector2i) -> Dictionary:
	var image := Image.new()
	if image.load_png_from_buffer(raw) != OK or image.get_size() != dimensions or image.get_format() != Image.FORMAT_RGBA8:
		return rejected("Invalid source PNG")
	var pixels: PackedByteArray = image.get_data()
	for index: int in range(3,pixels.size(),4):
		if pixels[index] != 0 and pixels[index] != 255: return rejected("Original source alpha must be binary")
	return {"ok":true,"error":"","image":image,"texture":ImageTexture.create_from_image(image),"pixels":pixels}

static func draw_order(bundle: Dictionary, displayed_actor: Dictionary, camera: Vector2 = Vector2(544,1536)) -> Dictionary:
	if not bundle.get("ok",false) or not bundle.get("props") is Array or bundle.props.size()!=6 or camera != Vector2(544,1536):
		return rejected("場景家具或固定鏡頭未就緒。")
	if not displayed_actor.has("y_word") or not Movement.integer(displayed_actor.y_word) or displayed_actor.y_word<0 or displayed_actor.y_word>65535:
		return rejected("角色原始Y座標無效。")
	var buckets: Dictionary = {}
	var entries: Array[Dictionary] = []
	for prop: Dictionary in bundle.props:
		var entry: Dictionary = prop.duplicate()
		entry.kind="prop"
		entries.append(entry)
	entries.append({"kind":"player","sprite_priority":2})
	var placements: Array[Dictionary] = []
	for index: int in entries.size():
		var entry: Dictionary = entries[index]
		var y_raw: int = int(entry.world_xy_raw[1]) if entry.kind=="prop" else Movement.signed16(int(displayed_actor.y_word))
		var initial_bucket: int = Movement.divide16(y_raw-int(camera.y)*16)+256
		if initial_bucket<40 or initial_bucket>700: return rejected("超出原作深度排序測試範圍。")
		var bucket: int = initial_bucket
		while bucket<767 and buckets.has(bucket): bucket+=1
		if buckets.has(bucket): return rejected("原作深度排序表已滿。")
		buckets[bucket]=entry
		placements.append({"kind":entry.kind,"slot":index if index<6 else 0,"initial_bucket":initial_bucket,"assigned_bucket":bucket})
	var ordered: Array[Dictionary] = []
	var keys: Array = buckets.keys()
	keys.sort()
	for key: int in keys: ordered.append(buckets[key])
	return {"ok":true,"error":"","entries":ordered,"placements":placements}

static func lookup(bundle: Dictionary, state: Dictionary) -> Dictionary:
	if not bundle.get("ok",false) or not bundle.get("frames") is Dictionary or not bundle.get("textures") is Dictionary:
		return rejected("角色包尚未載入。")
	for key: String in ["animation_index","animation_cursor","image_index","render_flags_word"]:
		if not state.has(key) or not Movement.integer(state[key]) or state[key] < 0 or state[key] > 65535: return rejected("角色動畫狀態不完整。")
	var key: String = "%d:%d" % [state.animation_index,state.animation_cursor]
	if not bundle.frames.has(key) or not bundle.textures.has(key): return rejected("未核准的動畫姿勢。")
	if not bundle.frames[key] is Dictionary or not bundle.textures[key] is Texture2D or not is_instance_valid(bundle.textures[key]):
		return rejected("必要角色貼圖不存在或已失效。")
	if bundle.textures[key].get_width()!=32 or bundle.textures[key].get_height()!=40:
		return rejected("角色貼圖尺寸與核准來源不符。")
	var frame: Dictionary = bundle.frames[key]
	if int(state.image_index) != int(frame.image_index) or bool(int(state.render_flags_word)&1) != frame.baked_mirror_x:
		return rejected("圖片索引或鏡射與核准姿勢不一致。")
	return {"ok":true,"error":"","frame":frame.duplicate(true),"texture":bundle.textures[key]}
