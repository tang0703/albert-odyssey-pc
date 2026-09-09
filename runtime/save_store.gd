class_name PcSaveStore
extends RefCounted
## Local PC state only; no emulator save-state compatibility.

static func valid_state(value: Variant) -> bool:
	if not value is Dictionary:
		return false
	var state: Dictionary = value
	if not (state.get("schema", "") == "ao_pc_save_v1"
		and state.get("scene", null) is String
		and not str(state["scene"]).is_empty()
		and state.get("player", null) is Dictionary
		and state.get("party", null) is Array
		and state.get("flags", null) is Dictionary
		and state.get("safe_boundary", null) is bool and state["safe_boundary"]):
		return false
	for coordinate: String in ["x", "y"]:
		var number: Variant = state["player"].get(coordinate, null)
		if not (number is int or number is float) or not is_finite(float(number)):
			return false
	for flag: Variant in state["flags"]:
		if not flag is String or not state["flags"][flag] is bool:
			return false
	return true

static func save_file(path: String, state: Dictionary) -> Error:
	if not valid_state(state):
		return ERR_INVALID_DATA
	var parent: String = path.get_base_dir()
	var result: Error = DirAccess.make_dir_recursive_absolute(parent)
	if result != OK:
		return result
	var temp: String = path + ".tmp"
	var file: FileAccess = FileAccess.open(temp, FileAccess.WRITE)
	if file == null:
		return FileAccess.get_open_error()
	file.store_string(JSON.stringify(state, "\t"))
	file.flush()
	file.close()
	# Keep the old file if staging failed to round-trip.
	if load_file(temp).is_empty():
		return ERR_FILE_CORRUPT
	var backup: String = path + ".bak"
	if FileAccess.file_exists(path):
		if FileAccess.file_exists(backup):
			result = DirAccess.remove_absolute(backup)
			if result != OK:
				return result
		result = DirAccess.rename_absolute(path, backup)
		if result != OK:
			return result
	result = DirAccess.rename_absolute(temp, path)
	if result != OK and FileAccess.file_exists(backup):
		DirAccess.rename_absolute(backup, path)
	return result

static func load_file(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(path)) != OK:
		return {}
	var data: Variant = parser.data
	return data if valid_state(data) else {}
