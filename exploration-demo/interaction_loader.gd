extends RefCounted
const Common = preload("res://package_loader.gd")
const Character = preload("res://character_loader.gd")
const Previous = preload("res://event_loader.gd")
const Core = preload("res://interaction_core.gd")
const DEPENDENCIES: Dictionary = {"scene":"bf837ef145c4ac413f6cb383c70d6a1d7e1e6d2544300719e3add645830e7fbc","character":"ccc35c6e98a0a95cf517a555f338b3147dd307c1e60d3a284ffdded76f2bfd21","character-hd":"00f009e7eded1ab6a3a5fb8b4c621ab03c705b43b701822eb62fb601718e511c","room":"4f5871775e4ff5de364cb78ed6aab695bcca5e60b57be4977d01270c7ed3e8d2","event":"4c830604e9eaeadb0542df39f37355f7d37509f24940ed7cc8a210c012f04510"}
const ROUTES: Array[String] = ["direct","reminder-first","left-edge","right-edge","near-edge","wrong-facing","hold","rapid","left-inside","right-inside","near-inside","east-facing","west-facing"]

static func default_directory() -> String:
	return ProjectSettings.globalize_path("res://generated/interaction") if OS.has_feature("editor") else OS.get_executable_path().get_base_dir().path_join("interaction")

static func names() -> Array[String]:
	var result: Array[String] = ["core.json","sprites.json","cirrus-pickup.wav"]
	for n: int in range(35,39): result.append("pickup-%02d.png" % n)
	for n: int in [32,33,34,35,36,37,38,39,40,41,42,44]: result.append("spark-%02d.png" % n)
	for route: String in ROUTES: result.append("reference-"+route+".json")
	return result

static func load_bundle(directory: String, movement: Dictionary, flags: PackedByteArray, character: Dictionary, room: Dictionary) -> Dictionary:
	var pin: Variant = Common.read_json("res://interaction-pin.json")
	if not pin is Dictionary or pin.get("schema") != "ao_pc_interaction_bundle_pin_v1" or pin.get("dependencies") != DEPENDENCIES: return Common.rejected("缺少事件核准識別。")
	if FileAccess.get_sha256(directory.path_join("package.json")) != pin.get("manifest_sha256",""): return Common.rejected("事件包缺失或遭修改。")
	var manifest: Variant = Common.read_json(directory.path_join("package.json"))
	if not manifest is Dictionary or manifest.get("schema") != "ao_pc_interaction_bundle_v1" or manifest.get("dependencies") != DEPENDENCIES or manifest.get("source_local_only") != true: return Common.rejected("事件來源版本不符。")
	for name: String in DEPENDENCIES:
		if FileAccess.get_sha256(directory.get_base_dir().path_join(name).path_join("package.json")) != DEPENDENCIES[name]: return Common.rejected("事件依賴版本不符："+name)
	var expected := PackedStringArray(names()+["package.json"])
	expected.sort()
	var present: PackedStringArray = DirAccess.get_files_at(directory); present.sort()
	if expected != present or not DirAccess.get_directories_at(directory).is_empty() or not manifest.get("files") is Dictionary or manifest.files.size() != names().size(): return Common.rejected("事件包含未核准資源或缺檔。")
	for name: String in names():
		var identity: Variant = manifest.files.get(name)
		var raw: PackedByteArray = FileAccess.get_file_as_bytes(directory.path_join(name))
		if not identity is Dictionary or raw.size() != identity.get("bytes") or FileAccess.get_sha256(directory.path_join(name)) != identity.get("sha256"): return Common.rejected("事件資源雜湊不符："+name)
	var data: Variant = Common.read_json(directory.path_join("core.json"))
	if not data is Dictionary: return Common.rejected("缺少事件流程。")
	var core := Core.new()
	var configured: Dictionary = core.configure(data,movement,flags,character,room)
	if not configured.ok: return configured
	var sprite_data: Dictionary = Common.read_json(directory.path_join("sprites.json"))
	var sprites: Dictionary = {}
	for row: Dictionary in sprite_data.get("sprites",[]):
		var decoded: Dictionary = Character._decode_image(FileAccess.get_file_as_bytes(directory.path_join(row.file)),Vector2i(int(row.dimensions[0]),int(row.dimensions[1])))
		if not decoded.ok: return Common.rejected("必要事件圖像無法解碼。")
		var entry: Dictionary = row.duplicate(true)
		entry.texture = decoded.texture
		sprites[str(row.id)] = entry
	if sprites.size() != 16: return Common.rejected("互動必要姿勢缺失。")
	for n: int in range(35,39):
		if not sprites.has("pickup_%d" % n): return Common.rejected("缺少拾取姿勢。")
	for n: int in [32,33,34,35,36,37,38,39,40,41,42,44]:
		if not sprites.has("spark_%d" % n): return Common.rejected("缺少閃光影格。")
	var stream: AudioStreamWAV = AudioStreamWAV.load_from_file(directory.path_join("cirrus-pickup.wav"))
	if stream == null or stream.mix_rate != 22050 or stream.stereo or stream.format != AudioStreamWAV.FORMAT_16_BITS or stream.data.size() != 56292: return Common.rejected("原作短音訊格式不符。")
	var references: Array = []
	for route: String in ROUTES:
		var reference: Variant = Common.read_json(directory.path_join("reference-"+route+".json"))
		if not reference is Dictionary or reference.get("schema") != "ao_pc_interaction_reference_v1" or not reference.get("updates") is Array or reference.updates.is_empty(): return Common.rejected("事件重播資料缺失。")
		references.append(reference)
	var previous: Dictionary = Previous.load_bundle(directory.get_base_dir().path_join("event"),movement,flags,character,room)
	if not previous.ok: return previous
	sprites.merge(previous.sprites)
	return {"ok":true,"data":data,"sprites":sprites,"audio":previous.audio,"pickup_audio":stream,"references":references,"preloaded":true,"manifest_sha256":pin.manifest_sha256,"error":""}
