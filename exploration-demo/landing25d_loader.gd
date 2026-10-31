extends RefCounted
const Common = preload("res://package_loader.gd")

static func default_directory() -> String:
	return ProjectSettings.globalize_path("res://generated/enhanced25d-landing") if OS.has_feature("editor") else OS.get_executable_path().get_base_dir().path_join("enhanced25d-landing")

static func load_bundle(directory: String) -> Dictionary:
	var pin: Variant = Common.read_json("res://landing25d-pin.json")
	if not pin is Dictionary or pin.get("schema") != "ao_pc_landing25d_pin_v1": return Common.rejected("缺少 2.5D 素材釘選。")
	if FileAccess.get_sha256(directory.path_join("package.json")) != pin.get("manifest_sha256", ""): return Common.rejected("2.5D 素材包缺失或遭修改。")
	var manifest: Variant = Common.read_json(directory.path_join("package.json"))
	if not manifest is Dictionary or manifest.get("schema") != "ao_pc_landing25d_bundle_v1" or manifest.get("dependencies") != pin.dependencies: return Common.rejected("2.5D 來源相依不符。")
	for name: String in pin.dependencies:
		if FileAccess.get_sha256(directory.get_base_dir().path_join(name).path_join("package.json")) != pin.dependencies[name]: return Common.rejected("舊來源包遭修改："+name)
	var expected := PackedStringArray(pin.files); expected.append("package.json"); expected.sort()
	var actual := DirAccess.get_files_at(directory); actual.sort()
	if expected != actual or not DirAccess.get_directories_at(directory).is_empty(): return Common.rejected("2.5D 包含缺失或未核准資源。")
	if not manifest.get("files") is Dictionary or manifest.files.size() != pin.files.size(): return Common.rejected("2.5D 素材清單不完整。")
	for name: String in pin.files:
		var identity: Variant = manifest.files.get(name)
		if not identity is Dictionary or FileAccess.get_sha256(directory.path_join(name)) != identity.get("sha256", "") or FileAccess.get_file_as_bytes(directory.path_join(name)).size() != identity.get("bytes", -1): return Common.rejected("2.5D 素材雜湊不符："+name)
	var data: Variant = Common.read_json(directory.path_join("appearance.json"))
	if not data is Dictionary or data.get("schema") != "ao_pc_landing25d_appearance_v1" or data.get("scene_id") != 7 or data.get("frames", []).size() != 52: return Common.rejected("2.5D 外觀契約不符。")
	if data.layout.origin != [512,1792] or data.layout.dimensions != [448,256] or data.phase.cycle_updates != 48: return Common.rejected("2.5D 投影或相位未核准。")
	var result: Dictionary = {"ok":true,"data":data,"textures":{},"frames":{},"preloaded":false,"manifest_sha256":pin.manifest_sha256}
	for name: String in data.textures:
		if not manifest.files.has(name): return Common.rejected("未列入清單的必要貼圖。")
		var image := Image.new()
		if image.load(directory.path_join(name)) != OK or image.is_empty(): return Common.rejected("2.5D 圖片解碼失敗："+name)
		var dimensions: Array = data.textures[name].dimensions
		if image.get_width() != dimensions[0] or image.get_height() != dimensions[1]: return Common.rejected("2.5D 圖片尺寸錯誤。")
		result.textures[name] = ImageTexture.create_from_image(image)
	for frame: Dictionary in data.frames:
		var key: String = str(frame.direction)+"/"+("idle" if int(frame.cell)==12 else "walk-%02d"%int(frame.cell))
		if result.frames.has(key) or int(frame.cell)<0 or int(frame.cell)>12 or not result.textures.has("laia-"+str(frame.direction)+".png"): return Common.rejected("2.5D 影格重複或遺漏。")
		result.frames[key] = frame
	for direction: String in ["down","left","right","up"]:
		for i: int in 13:
			if not result.frames.has(direction+"/"+("idle" if i==12 else "walk-%02d"%i)): return Common.rejected("2.5D 動作不完整。")
	result.preloaded = true
	return result
