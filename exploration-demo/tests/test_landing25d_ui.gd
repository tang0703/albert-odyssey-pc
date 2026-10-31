extends SceneTree
var failures: Array[String] = []
var checks: int = 0
var updates: int = 0
func _initialize() -> void: call_deferred("run")
func check(value: bool,message: String) -> void:
	checks += 1
	if not value: failures.append(message); push_error(message)
func tap(ui: Control,code: int) -> void:
	var e := InputEventKey.new(); e.physical_keycode=code; e.pressed=true; ui._input(e)
	e.pressed=false; ui._input(e)
func run() -> void:
	var ui: Control = load("res://landing25d_main.tscn").instantiate()
	ui.ui_test_mode=true; root.add_child(ui); await process_frame
	check(ui.startup_error.is_empty() and ui.enhanced_bundle.preloaded and ui.landing_art.preloaded,"All eleven packages load: "+ui.startup_error)
	if not failures.is_empty(): ui.queue_free(); await process_frame; finish(); return
	var snapshots: Array = []
	var checked_phases: Dictionary = {}
	for mode: String in ["enhanced25d","hd","original","marker"]:
		ui.change_appearance(mode)
		for route: int in 4:
			ui.select_route(route)
			var history: Array = []
			for n: int in 5000:
				ui.advance_update(); updates+=1
				var state: Dictionary = ui.event_core.transition_snapshot()
				var phase_key: String = ui.event_core.stage+"/"+str(ui.event_core.disabled)+"/"+str(ui.event_core.event_completed)
				if mode=="enhanced25d" and not checked_phases.has(phase_key):
					checked_phases[phase_key]=true
					var queued: Array=ui.event_queue.duplicate(true)
					var display: Dictionary=ui.shown_event.duplicate(true)
					for k: int in 4: tap(ui,KEY_F2)
					check(ui.event_core.transition_snapshot()==state and ui.event_queue==queued and ui.shown_event==display,"F2 preserves queued sample and fade at "+phase_key)
					ui.paused=true;ui.advance_time(0.5)
					check(ui.event_core.transition_snapshot()==state,"Pause preserves phase "+phase_key)
					ui.paused=false
				if int(ui.shown_event.get("scene",8))==7 and ui.shown_event.get("world_visible",false):
					var raw: PackedByteArray = str(ui.shown_event.arrival_actor).hex_decode()
					var chosen: Dictionary = ui.LaiaAnimation.select(raw,0.0)
					check(chosen.ok,"LAIA source pose selection "+JSON.stringify(chosen))
					if not chosen.ok: break
				if mode=="enhanced25d": history.append(state)
				else: check(n<snapshots[route].size() and state==snapshots[route][n],"Appearance state equality %s/%d/%d"%[mode,route,n])
				if ui.source_replay_completed or not ui.startup_error.is_empty(): break
			check(ui.source_replay_completed and ui.mismatch_count==0 and ui.startup_error.is_empty(),"Complete source route "+mode+str(route)+ui.startup_error)
			check(ui.event_core.event_completed and ui.event_core.scene_id==7 and ui.qa_identity().old_scene_hidden,"LAIA completed and source room removed")
			if mode=="enhanced25d":
				snapshots.append(history)
				check(ui.qa_identity().effective_appearance=="enhanced25d","New two-scene 2.5D policy")
		if not failures.is_empty(): break
	ui.change_mode(0); ui.change_appearance("enhanced25d"); ui.reset_state()
	check(ui.enhanced_room() and ui.appearance_select.selected==0,"Reset restores selected room style")
	var before: Dictionary = ui.event_core.transition_snapshot()
	for i: int in 4: tap(ui,KEY_F2)
	check(ui.selected_appearance=="enhanced25d" and before==ui.event_core.transition_snapshot(),"F2 cycle cannot mutate source state")
	ui.paused=false; tap(ui,KEY_SPACE); ui.advance_time(0.5)
	check(ui.paused and before==ui.event_core.transition_snapshot(),"Pause freezes state")
	var previous_update: int = ui.update_count
	tap(ui,KEY_PERIOD); check(ui.update_count==previous_update+1 and ui.startup_error.is_empty(),"Single step advances exactly one complete update, including stationary state")
	ui.paused=false; ui.clear_held_keys(); check(ui.paused,"Interactive focus loss pauses")
	ui.reset_state(); check(ui.event_core.story=="01" and ui.event_core.weapon==255 and ui.load_responses.is_empty(),"Complete reset clears equipment and responses")
	# The inherited natural flow handles delayed audio/text/load responses. No
	# state is assigned from a later sample, and no busy flag is bypassed.
	for mode: String in ["enhanced25d","hd","original","marker"]:
		ui.change_appearance(mode); ui.reset_state(); ui.qa_pc_mode=true; ui.paused=false
		for n: int in 2800:
			ui.advance_update()
			if ui.event_core.event_completed: break
		check(ui.event_core.event_completed and ui.event_core.weapon==27 and ui.startup_error.is_empty(),"Natural complete flow "+mode)
	var partitions: Array = []
	for fps: int in [30,60,120]:
		ui.reset_state(); ui.paused=false; ui.qa_pc_mode=true
		for n: int in fps*35: ui.advance_time(1.0/float(fps))
		partitions.append(ui.event_core.transition_snapshot())
	check(partitions[0]==partitions[1] and partitions[1]==partitions[2],"Synthetic time partition equality; no GPU FPS test")
	ui.queue_free(); await process_frame; finish()
func finish() -> void:
	var result: Dictionary={"schema":"ao_pc_landing25d_functional_v1","passed":failures.is_empty(),"checks":checks,"source_updates":updates,"performance_tested":false,"failures":failures}
	var file := FileAccess.open("res://../reports/enhanced25d-landing/functional.json",FileAccess.WRITE); file.store_string(JSON.stringify(result,"\t")); file.close()
	print(JSON.stringify(result)); quit(0 if failures.is_empty() else 1)
