extends SceneTree

func _initialize() -> void:
	call_deferred("run_test")

func run_test() -> void:
	var scene: PackedScene = load("res://main.tscn")
	var ui: Control = scene.instantiate()
	root.add_child(ui)
	await process_frame
	var checks: Dictionary = {}
	checks["real_records_loaded"] = ui.records.size() == 137
	checks["real_textures_loaded"] = ui.package.get("textures", []).size() == 253
	checks["playability_gate_closed"] = ui.package.get("playable", true) == false
	var before: String = ui.text_view.text
	ui.advance_page(1)
	checks["next_page_changes_text"] = ui.selected_page == 1 and ui.text_view.text != before
	ui.advance_page(-1)
	checks["previous_page_restores_text"] = ui.text_view.text == before
	ui.advance_page(-1)
	checks["page_lower_bound"] = ui.selected_page == 0
	ui.advance_page(999)
	checks["page_upper_bound"] = ui.selected_page == 5
	checks["history_tracks_visited_pages"] = ui.history.size() == 3
	var success: bool = true
	for value: bool in checks.values():
		success = success and value
	var file: FileAccess = FileAccess.open("res://reports/workbench-tests.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(checks, "\t"))
	file.close()
	print(JSON.stringify(checks))
	quit(0 if success else 1)
