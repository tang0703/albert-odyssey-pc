extends SceneTree
const Recorder = preload("res://qa_recorder.gd")
var checks: int = 0

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message)
		quit(1)
		assert(value, message)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var recorder := Recorder.new()
	check(recorder.configure("user://qa-test", "soak", 15.0, 600.0, Vector2i(3840, 2160)).is_empty(), "valid steady soak")
	recorder.started_usec = 0
	recorder.last_usec = 0
	recorder._record_clock(14000000)
	check(recorder.frames.is_empty() and recorder.measured_start_usec == -1, "warmup frame intervals excluded")
	recorder._record_clock(15001000)
	check(recorder.measured_start_usec == 15001000 and recorder.frames.is_empty(), "transition frame crossing warmup excluded")
	recorder._record_clock(15017667)
	recorder._record_clock(15034334)
	recorder._record_clock(15194334)
	check(recorder.frames.size() == 3 and is_equal_approx(recorder.frames[0], 16.667), "measured wall intervals retained")
	check(recorder.spikes_ms.size() == 1 and is_equal_approx(recorder.spikes_ms[0]["frame_ms"], 160.0), "spikes retain timing and duration")
	check(is_equal_approx(recorder.spikes_ms[0]["seconds"], 15.194334) and is_equal_approx(recorder.spikes_ms[0]["measured_seconds"], 0.193334), "spike timestamps distinguish warmup and measured clocks")
	recorder.rendered_size = Vector2i(3840, 2160)
	recorder.surface_verified = true
	recorder.startup_ms = 420.0
	recorder.measured_start_actions = 5
	recorder.measured_start_battles = 1
	var report: Dictionary = recorder.make_report(615001000, 999, 100, 2.0)
	check(is_equal_approx(report["seconds"], 615.001) and is_equal_approx(report["measured_seconds"], 600.0), "600 measured seconds do not include warmup")
	check(report["steady_measurement"] and not report["readback_during_measurement"], "steady report excludes screenshot work")
	check(report["size"] == [3840, 2160] and report["startup_ms"] == 420.0, "report actual surface and separate startup")
	check(report["p95_ms"] == 160.0 and report["max_ms"] == 160.0 and is_equal_approx(report["mean_ms"], 193.334 / 3.0), "correct sample mean and nearest-rank percentile")
	check(report["measured_actions"] == 994 and report["measured_battles"] == 99, "warmup activity excluded from measured counters")
	recorder._record_metrics(615.001)
	check(recorder.samples[0].has("static_bytes") and recorder.samples[0].has("video_bytes") and recorder.samples[0].has("nodes") and recorder.samples[0]["phase"] == "measured", "resource counters sampled independently of screenshots")
	check(recorder.configure("user://qa-test", "capture", 15.0, 0.0, Vector2i.ZERO).is_empty() and recorder.mode == "screenshot", "capture alias accepted")
	check(recorder.requested_seconds == 4.0 and recorder.warmup_seconds == 2.0 and recorder.frames.is_empty(), "separate screenshot process reset")
	recorder.screenshot_saved = true
	report = recorder.make_report(recorder.started_usec, 0, 0, 1.0)
	check(not report["steady_measurement"] and report["readback_during_measurement"], "screenshots never claim steady performance")
	check(not recorder.configure("user://qa-test", "invalid", 15.0, 600.0, Vector2i.ZERO).is_empty(), "unknown mode rejected")
	check(not recorder.configure("user://qa-test", "soak", 0.0, 600.0, Vector2i.ZERO).is_empty(), "soak must leave a readback warmup")
	check(not recorder.configure("user://qa-test", "soak", 15.0, 0.0, Vector2i.ZERO).is_empty(), "soak duration required")
	check(not recorder.configure("user://qa-test", "soak", NAN, 600.0, Vector2i.ZERO).is_empty(), "nonfinite timing rejected")
	check(not recorder.configure("user://qa-test", "soak", 15.0, 600.0, Vector2i(3840, 0)).is_empty(), "partial target dimensions rejected")
	var ui := Control.new()
	ui.name = "NodeInventoryFixture"
	root.add_child(ui)
	var permanent := Control.new()
	permanent.name = "Permanent"
	ui.add_child(permanent)
	var popup := Label.new()
	popup.name = "Damage"
	popup.add_to_group("popups")
	ui.add_child(popup)
	var popup_child := Control.new()
	popup_child.name = "TransientChild"
	popup.add_child(popup_child)
	var impact := Control.new()
	impact.name = "Impact"
	impact.add_to_group("impacts")
	ui.add_child(impact)
	var inventory: Dictionary = recorder._node_inventory(ui)
	check(inventory["ui_nodes"] == 5 and inventory["ui_persistent_nodes"] == 2, "UI node inventory distinguishes permanent nodes from effects")
	check(inventory["transient_nodes"] == 3 and inventory["transient_groups"] == {"popups": 1, "impacts": 1}, "transient descendants inherit classification")
	check(inventory["persistent_nodes"] == inventory["tree_nodes"] - 3, "global scene-tree counts reconcile")
	var permanent_entries: Array = inventory["persistent_inventory"]
	check(permanent_entries.any(func(entry: Dictionary) -> bool: return entry["path"].ends_with("/Permanent") and entry["class"] == "Control"), "diagnostics include stable paths and classes")
	ui.remove_child(popup)
	popup.free()
	ui.remove_child(impact)
	impact.free()
	var without_effects: Dictionary = recorder._node_inventory(ui)
	check(without_effects["persistent_inventory"] == permanent_entries and without_effects["transient_nodes"] == 0, "finished effects do not change persistent inventory")
	var internal := Label.new()
	internal.name = "InternalTooltip"
	ui.add_child(internal, false, Node.INTERNAL_MODE_BACK)
	var with_internal: Dictionary = recorder._node_inventory(ui)
	check(with_internal["persistent_nodes"] == without_effects["persistent_nodes"] + 1, "internal engine-like nodes are visible to diagnosis")
	ui.free()
	print("BATTLE QA RECORDER: %d checks passed" % checks)
	quit()
