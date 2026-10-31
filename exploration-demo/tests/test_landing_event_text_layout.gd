extends SceneTree
var failures: Array[String] = []
var cases: Array = []
func _initialize() -> void: call_deferred("run")
func run() -> void:
	for size: Vector2i in [Vector2i(1920,1080),Vector2i(2560,1440),Vector2i(3840,2160)]:
		root.size = size
		var ui: Control = load("res://landing_event_main.tscn").instantiate()
		ui.ui_test_mode = true; root.add_child(ui)
		await process_frame; await process_frame
		if not ui.startup_error.is_empty(): failures.append(ui.startup_error); ui.queue_free(); await process_frame; break
		ui.qa_pc_mode = true; ui.paused = false
		var seen: Dictionary = {}
		for n: int in 2400:
			ui.advance_update()
			if not ui.startup_error.is_empty(): failures.append(ui.startup_error); break
			if ui.dialogue.active and ui.landing_bundle.dialogues.has(ui.dialogue_id):
				var id: String = ui.dialogue_id+":"+str(ui.dialogue.page)
				if not seen.has(id):
					seen[id] = true
					await process_frame; await process_frame
					var expected: String = ui.landing_bundle.dialogues[ui.dialogue_id].pages[ui.dialogue.page].zh_tw
					var bounds: Rect2 = ui.dialogue_panel.get_global_rect()
					var valid: bool = ui.dialogue_text.text == expected and ui.map_canvas.get_global_rect().encloses(bounds) and bounds.encloses(ui.dialogue_text.get_global_rect()) and bounds.encloses(ui.continue_button.get_global_rect()) and ui.dialogue_text.get_visible_line_count() >= ui.dialogue_text.get_line_count()
					cases.append({"resolution":[size.x,size.y],"page":id,"passed":valid,"lines":ui.dialogue_text.get_line_count(),"visible_lines":ui.dialogue_text.get_visible_line_count()})
					if not valid: failures.append("Dialogue clipped or changed: "+str(size)+" "+id)
			if ui.event_core.event_completed: break
		if seen.size() != 8: failures.append("Did not naturally reach all eight pages: "+str(size))
		ui.queue_free(); await process_frame
	var report: Dictionary = {"passed":failures.is_empty(),"cases":cases,"failures":failures,"performance_tested":false,"scope":"Natural whole-page dialogue layout in three window sizes; actual rendered resolution screenshots are separate."}
	var file := FileAccess.open("res://../reports/landing-event/l4-text-layout.json",FileAccess.WRITE)
	file.store_string(JSON.stringify(report,"\t")); file.close()
	print(JSON.stringify(report)); quit(0 if failures.is_empty() else 1)
