extends RefCounted
const Common = preload("res://package_loader.gd")
const Previous = preload("res://interaction_loader.gd")
const Core = preload("res://equipment_core.gd")
const ROUTES: Array[String] = ["equip-stairs","remove-stairs","reequip-stairs","unowned","cancel-owned","hold-equip","cancel-selection"]
static func default_directory() -> String:
	return ProjectSettings.globalize_path("res://generated/equipment") if OS.has_feature("editor") else OS.get_executable_path().get_base_dir().path_join("equipment")
static func load_bundle(directory: String, movement: Dictionary, flags: PackedByteArray, character: Dictionary, room: Dictionary) -> Dictionary:
	var pin: Variant = Common.read_json("res://equipment-pin.json")
	var dependencies: Dictionary = Previous.DEPENDENCIES.duplicate(true)
	dependencies.interaction = "365489c2f1c59410f26babb2e461c3dd2d25fb597d65306c4788aca01ff6a71e"
	if not pin is Dictionary or pin.get("schema") != "ao_pc_equipment_pin_v1" or pin.get("dependencies") != dependencies: return Common.rejected("缺少裝備核准識別。")
	if FileAccess.get_sha256(directory.path_join("package.json")) != pin.get("manifest_sha256",""): return Common.rejected("裝備資料包缺失或遭修改。")
	var manifest: Variant = Common.read_json(directory.path_join("package.json"))
	if not manifest is Dictionary or manifest.get("schema") != "ao_pc_equipment_bundle_v1" or manifest.get("dependencies") != dependencies or manifest.get("source_local_only") != true: return Common.rejected("裝備來源不符。")
	for name: String in dependencies:
		if FileAccess.get_sha256(directory.get_base_dir().path_join(name).path_join("package.json")) != dependencies[name]: return Common.rejected("舊資料包遭修改："+name)
	var names := PackedStringArray(["core.json"])
	for route: String in ROUTES: names.append("reference-"+route+".json")
	var expected := names.duplicate(); expected.append("package.json"); expected.sort()
	var actual := DirAccess.get_files_at(directory); actual.sort()
	if expected != actual or not DirAccess.get_directories_at(directory).is_empty() or not manifest.get("files") is Dictionary or manifest.files.size() != names.size(): return Common.rejected("裝備包含未核准資源。")
	for name: String in names:
		var identity: Variant = manifest.files.get(name)
		if not identity is Dictionary or FileAccess.get_file_as_bytes(directory.path_join(name)).size() != identity.get("bytes") or FileAccess.get_sha256(directory.path_join(name)) != identity.get("sha256"): return Common.rejected("裝備內容雜湊不符："+name)
	var data: Variant = Common.read_json(directory.path_join("core.json"))
	if not data is Dictionary: return Common.rejected("缺少裝備契約。")
	var core := Core.new()
	var configured: Dictionary = core.configure(data,movement,flags,character,room)
	if not configured.ok: return configured
	var loaded: Dictionary = Previous.load_bundle(directory.get_base_dir().path_join("interaction"),movement,flags,character,room)
	if not loaded.ok: return loaded
	loaded.data = data; loaded.references = []; loaded.manifest_sha256 = pin.manifest_sha256
	for route: String in ROUTES:
		var reference: Variant = Common.read_json(directory.path_join("reference-"+route+".json"))
		if not reference is Dictionary or reference.get("schema") != "ao_pc_equipment_reference_v1" or not reference.get("updates") is Array or reference.updates.is_empty(): return Common.rejected("裝備來源重播缺失。")
		if reference.terminal != null:
			reference.updates.append({"equipment":[],"input":{"pad":reference.terminal.pad,"pressed":0,"resource_loaded":0,"resource_playing":0,"text_active":false},"expected":reference.terminal.expected})
		loaded.references.append(reference)
	return loaded
