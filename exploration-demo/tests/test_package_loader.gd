extends SceneTree
const Bundle = preload("res://package_loader.gd")
var failures: Array[String] = []
var checks: int = 0
var directory: String

func check(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures.append(label)
		push_error(label)

func put(name: String, content: PackedByteArray) -> void:
	var file := FileAccess.open(directory.path_join(name), FileAccess.WRITE)
	check(file != null, "Can create isolated test input")
	if file != null:
		file.store_buffer(content)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var source: String = Bundle.default_directory()
	var loaded: Dictionary = Bundle.load_bundle(source)
	check(loaded.ok, "Real approved bundle loads and its full trace suite agrees")
	if not loaded.ok:
		print(loaded.error)
		quit(1)
		return
	check(loaded.textures.size() == 2 and loaded.traces.size() == 4, "Source layers and all four trajectories loaded")
	directory = ProjectSettings.globalize_path("res://generated/loader-test-" + str(Time.get_ticks_usec()))
	check(DirAccess.make_dir_recursive_absolute(directory) == OK, "Isolated test directory created")
	var names: PackedStringArray = DirAccess.get_files_at(source)
	for name: String in names:
		put(name, FileAccess.get_file_as_bytes(source.path_join(name)))
	check(Bundle.load_bundle(directory).ok, "Complete portable copy has no dependency on source RAM")
	put("extra.bin", PackedByteArray([1]))
	check(not Bundle.load_bundle(directory).ok, "Unlisted file rejected")
	DirAccess.remove_absolute(directory.path_join("extra.bin"))
	put(".unexpected", PackedByteArray([1]))
	check(not Bundle.load_bundle(directory).ok, "Hidden unlisted file rejected")
	DirAccess.remove_absolute(directory.path_join(".unexpected"))
	for name: String in ["flags.bin", "nbg0.png", "profile.json", "traces.json"]:
		DirAccess.remove_absolute(directory.path_join(name))
		check(not Bundle.load_bundle(directory).ok, "Missing required file rejected: " + name)
		put(name, PackedByteArray([0]))
		check(not Bundle.load_bundle(directory).ok, "Truncated required file rejected: " + name)
		put(name, FileAccess.get_file_as_bytes(source.path_join(name)))
	put("package.json", "{}".to_utf8_buffer())
	check(not Bundle.load_bundle(directory).ok, "Edited manifest cannot grant itself approval")
	for name: String in names:
		DirAccess.remove_absolute(directory.path_join(name))
	DirAccess.remove_absolute(directory)
	print(JSON.stringify({"schema": "ao_pc_loader_tests_v1", "checks": checks, "failures": failures, "passed": failures.is_empty()}))
	quit(0 if failures.is_empty() else 1)
