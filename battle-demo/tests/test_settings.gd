extends SceneTree
var failed: bool = false
var checks: int = 0

func check(condition: bool, description: String) -> void:
	checks += 1
	if not condition:
		failed = true
		push_error(description)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var path: String = "user://battle_demo_settings.cfg"
	var existed: bool = FileAccess.file_exists(path)
	var original: PackedByteArray = FileAccess.get_file_as_bytes(path) if existed else PackedByteArray()
	var ui: Control = load("res://main.tscn").instantiate()
	ui.ui_test_mode = true
	root.add_child(ui)
	await process_frame
	ui.volume = 0.15
	ui.speed = 2.0
	ui.resolution_index = 1
	ui.save_settings()
	check(FileAccess.file_exists(path),"settings file written")
	ui.queue_free()
	await process_frame
	# A fresh scene reads the saved settings through its startup path.
	var fresh: Control = load("res://main.tscn").instantiate()
	fresh.ui_test_mode = true
	root.add_child(fresh)
	await process_frame
	check(is_equal_approx(fresh.volume,0.15),"volume persisted")
	check(fresh.speed == 2.0 and fresh.speed_button.text.contains("2"),"speed persisted and displayed")
	check(fresh.resolution_index == 1 and root.size == Vector2i(2560,1440),"resolution persisted")
	var saved: PackedByteArray = FileAccess.get_file_as_bytes(path)
	fresh.qa = true
	fresh.volume = 0.8
	fresh.save_settings()
	check(FileAccess.get_file_as_bytes(path) == saved,"QA does not overwrite preferences")
	fresh.queue_free()
	await process_frame
	if existed:
		var file := FileAccess.open(path,FileAccess.WRITE)
		file.store_buffer(original); file.close()
	else:
		DirAccess.remove_absolute(path)
	print("BATTLE SETTINGS: %d checks%s" % [checks," failed" if failed else " passed"])
	quit(1 if failed else 0)
