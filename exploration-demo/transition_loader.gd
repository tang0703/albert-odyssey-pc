extends RefCounted
const Common = preload("res://package_loader.gd")
const Core = preload("res://transition_core.gd")
const ROUTES: Array[String] = ["equip-stairs","remove-stairs","reequip-stairs","landing-corridor"]

static func default_directory() -> String:
	return ProjectSettings.globalize_path("res://generated/transition") if OS.has_feature("editor") else OS.get_executable_path().get_base_dir().path_join("transition")

static func load_bundle(directory: String, old: Dictionary, movement: Dictionary, flags: PackedByteArray, character: Dictionary, room: Dictionary) -> Dictionary:
	var pin: Variant = Common.read_json("res://transition-pin.json")
	if not pin is Dictionary or pin.get("schema") != "ao_pc_transition_pin_v1" or pin.get("runtime_approved") != true: return Common.rejected("缺少轉場核准識別。")
	if FileAccess.get_sha256(directory.path_join("package.json")) != pin.get("manifest_sha256",""): return Common.rejected("轉場資料包缺失或遭修改。")
	var manifest: Variant = Common.read_json(directory.path_join("package.json"))
	if not manifest is Dictionary or manifest.get("schema") != "ao_pc_transition_bundle_v2" or manifest.get("dependencies") != pin.dependencies or manifest.get("source_local_only") != true or manifest.get("stage") != "source_verified" or manifest.get("performance_tested") != false: return Common.rejected("轉場來源契約不符。")
	for name: String in pin.dependencies:
		if FileAccess.get_sha256(directory.get_base_dir().path_join(name).path_join("package.json")) != pin.dependencies[name]: return Common.rejected("舊資料包遭修改："+name)
	var names := PackedStringArray(["core.json","visuals.json","background.png","foreground.png","actor-1-03.png","object-0-00.png","object-2-01.png","object-3-00.png","object-4-00.png","object-5-01.png","object-6-02.png","object-7-02.png"])
	for i: int in 8: names.append("object-1-%02d.png" % i)
	for route: String in ROUTES: names.append("reference-"+route+".json")
	var expected := names.duplicate(); expected.append("package.json"); expected.sort()
	var actual := DirAccess.get_files_at(directory); actual.sort()
	if expected != actual or not DirAccess.get_directories_at(directory).is_empty() or not manifest.get("files") is Dictionary or manifest.files.size() != names.size(): return Common.rejected("轉場包含未核准資源。")
	for name: String in names:
		var identity: Variant = manifest.files.get(name)
		if not identity is Dictionary or FileAccess.get_file_as_bytes(directory.path_join(name)).size() != identity.get("bytes") or FileAccess.get_sha256(directory.path_join(name)) != identity.get("sha256"): return Common.rejected("轉場內容雜湊不符："+name)
	var data: Variant = Common.read_json(directory.path_join("core.json"))
	var visuals: Variant = Common.read_json(directory.path_join("visuals.json"))
	if not data is Dictionary or not visuals is Dictionary or visuals.get("schema") != "ao_pc_transition_visuals_v1": return Common.rejected("缺少落點契約。")
	var core := Core.new()
	var configured: Dictionary = core.configure_transition(data,old,movement,flags,character,room)
	if not configured.ok: return configured
	var result: Dictionary = {"ok":true,"data":data,"visuals":visuals,"references":[],"textures":{},"frames":{},"manifest_sha256":pin.manifest_sha256,"preloaded":false}
	for name: String in names:
		if not name.ends_with(".png"): continue
		var image := Image.new()
		if image.load(directory.path_join(name)) != OK or image.is_empty(): return Common.rejected("落點圖片無法解碼："+name)
		result.textures[name] = ImageTexture.create_from_image(image)
	for source: Dictionary in visuals.frames:
		var frame: Dictionary = source.duplicate(true)
		if not result.textures.has(frame.file): return Common.rejected("缺少落點必要影格。")
		frame.texture = result.textures[frame.file]
		if frame.texture.get_width() != int(frame.dimensions[0]) or frame.texture.get_height() != int(frame.dimensions[1]): return Common.rejected("落點圖片尺寸錯誤。")
		result.frames["%s:%d:%d" % [frame.source_kind,int(frame.slot),int(frame.image_index)]] = frame
	for route: String in ROUTES:
		var reference: Variant = Common.read_json(directory.path_join("reference-"+route+".json"))
		if not reference is Dictionary or reference.get("schema") != "ao_pc_transition_reference_v1" or not reference.get("post_commit") is Array or reference.post_commit.is_empty(): return Common.rejected("轉場來源重播缺失。")
		result.references.append(reference)
	result.preloaded = true
	return result
