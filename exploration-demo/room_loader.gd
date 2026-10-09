extends RefCounted
const Common = preload("res://package_loader.gd")
const Camera = preload("res://room_camera_core.gd")
const Movement = preload("res://room_movement_core.gd")
const Decorations = preload("res://room_decoration_core.gd")
const DEPENDENCIES: Dictionary = {"scene":"bf837ef145c4ac413f6cb383c70d6a1d7e1e6d2544300719e3add645830e7fbc",
	"character":"ccc35c6e98a0a95cf517a555f338b3147dd307c1e60d3a284ffdded76f2bfd21",
	"character-hd":"00f009e7eded1ab6a3a5fb8b4c621ab03c705b43b701822eb62fb601718e511c"}

static func default_directory() -> String:
	return ProjectSettings.globalize_path("res://generated/room") if OS.has_feature("editor") else OS.get_executable_path().get_base_dir().path_join("room")

static func image_names() -> Array[String]:
	var names: Array[String] = ["background.png","foreground.png","decoration-6-46.png"]
	for n: int in range(16,32): names.append("decoration-7-%02d.png" % n)
	return names

static func load_bundle(directory: String, flags: PackedByteArray) -> Dictionary:
	var pin: Variant = Common.read_json("res://room-pin.json")
	if not pin is Dictionary or pin.get("schema") != "ao_pc_room_bundle_pin_v1" or pin.get("dependencies") != DEPENDENCIES:
		return Common.rejected("缺少核准室內擴展包識別。")
	var path: String = directory.path_join("package.json")
	if FileAccess.get_sha256(path) != pin.get("manifest_sha256",""): return Common.rejected("室內資料包缺失或雜湊不符。")
	var manifest: Variant = Common.read_json(path)
	if not manifest is Dictionary or manifest.get("schema") != "ao_pc_room_bundle_v1" or manifest.get("dependencies") != DEPENDENCIES or manifest.get("source_local_only") != true:
		return Common.rejected("室內資料版本或來源綁定不符。")
	for name: String in DEPENDENCIES:
		if FileAccess.get_sha256(directory.get_base_dir().path_join(name).path_join("package.json")) != DEPENDENCIES[name]: return Common.rejected("室內包依賴版本不符："+name)
	var names: Array[String] = image_names()
	names.append("room.json")
	var expected := PackedStringArray(names + ["package.json"])
	expected.sort()
	var actual: PackedStringArray = DirAccess.get_files_at(directory)
	actual.sort()
	if actual != expected or not DirAccess.get_directories_at(directory).is_empty() or not manifest.get("files") is Dictionary or manifest.files.size() != names.size(): return Common.rejected("室內包包含未核准檔案或缺檔。")
	for name: String in names:
		var identity: Variant = manifest.files.get(name)
		var raw: PackedByteArray = FileAccess.get_file_as_bytes(directory.path_join(name))
		if not identity is Dictionary or raw.size() != identity.get("bytes") or FileAccess.get_sha256(directory.path_join(name)) != identity.get("sha256"): return Common.rejected("室內資源雜湊不符："+name)
	var data: Variant = Common.read_json(directory.path_join("room.json"))
	if not data is Dictionary or not Movement._keys_match(data,["schema","movement_profile","camera_profile","initial_cameras","boundaries","traces","visuals","reference_sha256","visuals_sha256"]) or data.schema != "ao_pc_room_scene_v1": return Common.rejected("室內必要欄位不完整。")
	var movement := Movement.new()
	var configured: Dictionary = movement.configure_room(data.movement_profile,flags,data.boundaries)
	if not configured.get("ok",false): return configured
	var camera := Camera.new()
	configured = camera.configure(data.camera_profile)
	if not configured.get("ok",false): return configured
	if not data.initial_cameras is Array or data.initial_cameras.size() != 2: return Common.rejected("缺少初始鏡頭。")
	for state: Variant in data.initial_cameras:
		if not state is Dictionary or not Camera.validate_state(state).is_empty(): return Common.rejected("初始鏡頭無效。")
	var visuals: Variant = data.visuals
	if not visuals is Dictionary or visuals.get("schema") != "ao_room_visuals_v1" or visuals.get("atlas_origin") != [512,1536] or visuals.get("atlas_dimensions") != [448,256] or visuals.get("viewport") != [320,224] or visuals.get("delays") != {"actor":3,"camera":3,"decorations":3} or not visuals.get("decorations") is Array or visuals.decorations.size() != 17: return Common.rejected("圖層或演出時序未經核准。")
	var decorations := Decorations.new()
	configured = decorations.configure(visuals.programs)
	if not configured.get("ok",false): return configured
	if not data.traces is Array or data.traces.size() != 5: return Common.rejected("缺少正式室內路線。")
	var textures: Dictionary = {}
	for name: String in image_names():
		var image := Image.new()
		if image.load(directory.path_join(name)) != OK or image.get_format() != Image.FORMAT_RGBA8: return Common.rejected("室內圖片無法解碼："+name)
		var dims: Variant = manifest.files[name].get("dimensions")
		if not dims is Array or dims.size() != 2 or image.get_size() != Vector2i(int(dims[0]),int(dims[1])): return Common.rejected("室內圖片尺寸不符。")
		textures[name] = ImageTexture.create_from_image(image)
	var frames: Dictionary = {}
	for row: Variant in visuals.decorations:
		if not row is Dictionary or not textures.has(row.get("file","")) or row.get("slot") not in [6,7] or row.get("sprite_priority") != 3 or row.get("command_priority") != 255: return Common.rejected("裝飾物外觀記錄無效。")
		var key: String = "%d:%d" % [row.slot,row.image_index]
		if frames.has(key): return Common.rejected("裝飾物影格重複。")
		var entry: Dictionary = row.duplicate(true)
		entry.texture = textures[row.file]
		entry.kind = "prop"
		frames[key] = entry
	for slot: int in [6,7]:
		for image: int in ([46] if slot == 6 else range(16,32)):
			if not frames.has("%d:%d" % [slot,image]): return Common.rejected("缺少必要裝飾物影格。")
	return {"ok":true,"error":"","data":data,"textures":textures,"frames":frames,"preloaded":true,"manifest_sha256":pin.manifest_sha256}
