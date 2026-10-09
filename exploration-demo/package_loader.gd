extends RefCounted
## Original-derived local files are separate from the executable's resource pack.
## The compiled distribution carries a manifest pin; edited local data is refused.
const Movement = preload("res://movement_core.gd")
const PAYLOADS: Array[String] = ["flags.bin", "nbg0.png", "nbg1.png", "profile.json", "traces.json"]
const ROUTES: Array[String] = ["cardinal", "corners", "open", "release"]

static func default_directory() -> String:
	if OS.has_feature("standalone"):
		return OS.get_executable_path().get_base_dir().path_join("scene")
	return ProjectSettings.globalize_path("res://generated/scene")

static func rejected(reason: String) -> Dictionary:
	return {"ok": false, "error": reason}

static func read_json(path: String) -> Variant:
	if not FileAccess.file_exists(path):
		return null
	return normalize_integers(JSON.parse_string(FileAccess.get_file_as_string(path)))

static func normalize_integers(value: Variant) -> Variant:
	# Godot's JSON parser emits floats. Keep fractional values unmodified so
	# validation rejects them; normalize exact integers for deep state comparison.
	if typeof(value) == TYPE_FLOAT and Movement.integer(value):
		return int(value)
	if value is Array:
		var array: Array = []
		for item: Variant in value:
			array.append(normalize_integers(item))
		return array
	if value is Dictionary:
		var dictionary: Dictionary = {}
		for key: Variant in value:
			dictionary[key] = normalize_integers(value[key])
		return dictionary
	return value

static func load_bundle(directory: String) -> Dictionary:
	var pin: Variant = read_json("res://bundle-pin.json")
	if not pin is Dictionary or pin.get("schema") != "ao_pc_exploration_bundle_pin_v1":
		return rejected("缺少核准資料包識別。請先執行 exploration_bundle.py build。")
	var manifest_path: String = directory.path_join("package.json")
	if not FileAccess.file_exists(manifest_path) or FileAccess.get_sha256(manifest_path) != pin.get("manifest_sha256", ""):
		return rejected("資料包缺失或內容已變更，無法啟動行走驗證。")
	var data: Variant = read_json(manifest_path)
	if not data is Dictionary or data.get("schema") != "ao_pc_exploration_bundle_v1":
		return rejected("未知場景資料格式。")
	if data.get("camera") != [544, 1536] or data.get("viewport") != [320, 224] or data.get("source_local_only") != true:
		return rejected("場景鏡頭、尺寸或來源標記未通過驗證。")
	var files: Variant = data.get("files")
	if not files is Dictionary or files.size() != PAYLOADS.size():
		return rejected("資料包缺少必要檔案清單。")
	var present: PackedStringArray = DirAccess.get_files_at(directory)
	present.sort()
	var expected: PackedStringArray = PackedStringArray(PAYLOADS + ["package.json"])
	expected.sort()
	if present != expected or not DirAccess.get_directories_at(directory).is_empty():
		return rejected("資料包含有未核准檔案，或必要檔案不完整。")
	for name: String in PAYLOADS:
		var identity: Variant = files.get(name)
		var path: String = directory.path_join(name)
		if not identity is Dictionary or not FileAccess.file_exists(path):
			return rejected("必要資料缺失：" + name)
		var raw: PackedByteArray = FileAccess.get_file_as_bytes(path)
		if raw.size() != identity.get("bytes") or FileAccess.get_sha256(path) != identity.get("sha256"):
			return rejected("資料截斷或來源雜湊不符：" + name)
	var profile: Variant = read_json(directory.path_join("profile.json"))
	var traces: Variant = read_json(directory.path_join("traces.json"))
	var flags: PackedByteArray = FileAccess.get_file_as_bytes(directory.path_join("flags.bin"))
	if not profile is Dictionary or not traces is Array or traces.size() != ROUTES.size():
		return rejected("缺少已驗證的玩家設定或四組軌跡。")
	var core := Movement.new()
	var configured: Dictionary = core.configure(profile, flags)
	if not configured.get("ok", false):
		return rejected("移動設定遭拒：" + str(configured.get("error", "unknown")))
	var seen: Array[String] = []
	for trace: Variant in traces:
		if not trace is Dictionary or trace.get("id") not in ROUTES or trace.get("id") in seen:
			return rejected("軌跡識別重複或不受支援。")
		seen.append(str(trace["id"]))
		if trace.get("initial_state") != core.initial_state() or not trace.get("updates") is Array or trace["updates"].is_empty():
			return rejected("軌跡起點或更新序列未通過驗證。")
		var state: Dictionary = core.initial_state()
		var frame: int = 0
		for update: Variant in trace["updates"]:
			frame += 1
			if not update is Dictionary or update.get("frame") != frame:
				return rejected("軌跡更新序號不連續。")
			var result: Dictionary = core.step_game_input(state, int(update.get("game_pad_word", -1)))
			if not result.get("ok", false) or result.get("state") != update.get("expected") or not result.get("diagnostics", {}).get("applied", false):
				return rejected("Godot 與核准原作軌跡不一致：" + str(trace["id"]) + "/" + str(frame))
			state = result["state"]
	var textures: Array[Texture2D] = []
	for name: String in ["nbg0.png", "nbg1.png"]:
		var decoded := Image.new()
		if decoded.load(directory.path_join(name)) != OK or decoded.get_size() != Vector2i(320, 224):
			return rejected("背景圖片無法解碼或尺寸不符：" + name)
		textures.append(ImageTexture.create_from_image(decoded))
	return {"ok": true, "error": "", "data": data, "profile": profile,
		"flags": flags, "textures": textures, "traces": traces}
