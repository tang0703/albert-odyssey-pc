extends SceneTree
## Short render inspection, driven only by normal semantic inputs. No timings.
var output: String=""
var target:=Vector2i(1920,1080)
var seen: Dictionary={}
func _initialize() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--output="): output=arg.trim_prefix("--output=")
		if arg.begins_with("--size="):
			var s:=arg.trim_prefix("--size=").split("x");target=Vector2i(int(s[0]),int(s[1]))
	call_deferred("run")
func run() -> void:
	if output.is_empty(): quit(1);return
	DirAccess.make_dir_recursive_absolute(output)
	var ui: Control=load("res://landing25d_main.tscn").instantiate()
	ui.ui_test_mode=true;ui.qa_target=target;root.add_child(ui)
	await process_frame;await process_frame
	if not ui.startup_error.is_empty(): push_error(ui.startup_error);quit(1);return
	ui.qa_pc_mode=true;ui.paused=false
	for n: int in 2500:
		ui.advance_update()
		if not ui.startup_error.is_empty(): push_error(ui.startup_error);quit(1);return
		var key: String=""
		if ui.event_core.stage=="fade_out" and ui.event_core.rgb[0]<-50: key="fade-out"
		if int(ui.shown_event.get("scene",8))==7 and ui.shown_event.get("world_visible",false):
			var raw: PackedByteArray=str(ui.shown_event.arrival_actor).hex_decode()
			var selector: int=ui.TransferCore.word(raw,0x36)
			if ui.event_core.stage=="fade_in" and ui.event_core.rgb[0]>-180: key="fade-in"
			elif selector==6 and not ui.event_core.event_completed: key="laia-return"
			elif selector==7: key="laia-up-action"
			elif ui.event_core.event_completed: key="control-restored"
		if not key.is_empty() and not seen.has(key):
			ui.paused=true;ui.refresh()
			await process_frame;await process_frame;await RenderingServer.frame_post_draw
			var image:=root.get_texture().get_image()
			if image.get_size()!=target or image.save_png(output.path_join(key+".png"))!=OK: push_error("Phase screenshot failed");quit(1);return
			seen[key]={"update":ui.update_count,"scene":ui.event_core.scene_id,"stage":ui.event_core.stage,"identity":ui.qa_identity(),"size":[target.x,target.y]}
			ui.paused=false
		if seen.size()==5: break
	var passed: bool=seen.size()==5 and ui.startup_error.is_empty()
	var file:=FileAccess.open(output.path_join("phases.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed":passed,"performance_tested":false,"natural_inputs":true,"captures":seen},"\t"));file.close()
	ui.queue_free();await process_frame;quit(0 if passed else 1)
