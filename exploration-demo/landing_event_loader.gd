extends RefCounted
const Common = preload("res://package_loader.gd")
const Core = preload("res://landing_event_core.gd")
const ROUTES: Array[String] = ["equip","remove","reequip","edge-held"]

static func default_directory() -> String:
	return ProjectSettings.globalize_path("res://generated/landing-event") if OS.has_feature("editor") else OS.get_executable_path().get_base_dir().path_join("landing-event")

static func load_bundle(directory: String, transfer: Dictionary, old: Dictionary, movement: Dictionary, flags: PackedByteArray, character: Dictionary, room: Dictionary) -> Dictionary:
	var pin: Variant = Common.read_json("res://landing-event-pin.json")
	if not pin is Dictionary or pin.get("schema") != "ao_pc_landing_event_pin_v1" or pin.get("runtime_approved") != true: return Common.rejected("缺少落點事件核准識別。")
	if FileAccess.get_sha256(directory.path_join("package.json")) != pin.get("manifest_sha256",""): return Common.rejected("落點事件資料包缺失或遭修改。")
	var manifest: Variant = Common.read_json(directory.path_join("package.json"))
	if not manifest is Dictionary or manifest.get("schema") != "ao_pc_landing_event_bundle_v1" or manifest.get("dependencies") != pin.dependencies or manifest.get("source_local_only") != true or manifest.get("stage") != "source_verified" or manifest.get("performance_tested") != false: return Common.rejected("落點事件來源契約不符。")
	for name: String in pin.dependencies:
		if FileAccess.get_sha256(directory.get_base_dir().path_join(name).path_join("package.json")) != pin.dependencies[name]: return Common.rejected("舊資料包遭修改："+name)
	var names := PackedStringArray(["core.json","visuals.json","dialogue.json"])
	for image: int in [3,4,5,6,7,8]:
		for flip: int in ([0,1] if image in [3,4,5] else [0]): names.append("actor-50-%02d-%d.png" % [image,flip])
	for route: String in ROUTES: names.append("reference-"+route+".json")
	var expected := names.duplicate(); expected.append("package.json"); expected.sort()
	var actual := DirAccess.get_files_at(directory); actual.sort()
	if expected != actual or not DirAccess.get_directories_at(directory).is_empty() or not manifest.get("files") is Dictionary or manifest.files.size() != names.size(): return Common.rejected("落點事件包含未核准資源。")
	for name: String in names:
		var identity: Variant = manifest.files.get(name)
		if not identity is Dictionary or FileAccess.get_file_as_bytes(directory.path_join(name)).size() != identity.get("bytes") or FileAccess.get_sha256(directory.path_join(name)) != identity.get("sha256"): return Common.rejected("落點事件內容雜湊不符："+name)
	var data: Variant = Common.read_json(directory.path_join("core.json"))
	var visuals: Variant = Common.read_json(directory.path_join("visuals.json"))
	if not data is Dictionary or not visuals is Dictionary or visuals.get("schema") != "ao_pc_landing_event_visuals_v1": return Common.rejected("缺少落點契約。")
	var core := Core.new()
	var configured: Dictionary = core.configure_landing_event(data,transfer,old,movement,flags,character,room)
	if not configured.ok: return configured
	var dialogue_data: Variant = Common.read_json(directory.path_join("dialogue.json"))
	if not dialogue_data is Dictionary or dialogue_data.get("schema") != "ao_pc_landing_event_dialogue_v1" or not dialogue_data.get("records") is Dictionary:
		return Common.rejected("缺少落點事件文字契約。")
	var result: Dictionary = {"ok":true,"data":data,"visuals":visuals,"references":[],"textures":{},"frames":{},"manifest_sha256":pin.manifest_sha256,"preloaded":false,"dialogues":dialogue_data.records}
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
		result.frames["%d:%d" % [int(frame.image_index),int(bool(frame.flip_x))]] = frame
	for route: String in ROUTES:
		var reference: Variant = Common.read_json(directory.path_join("reference-"+route+".json"))
		if not reference is Dictionary or reference.get("schema") != "ao_pc_landing_event_reference_v1" or not reference.get("post_commit") is Array or reference.post_commit.is_empty(): return Common.rejected("落點事件來源重播缺失。")
		result.references.append(reference)
	result.preloaded = true
	return result
