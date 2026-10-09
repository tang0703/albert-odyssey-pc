extends SceneTree
const Loader = preload("res://character_loader.gd")
const AnimationCore = preload("res://character_animation_core.gd")
var failures: Array[String] = []
var checks: int = 0
var source_status: String = "not_run"

func check(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures.append(message)
		push_error(message)

func _initialize() -> void:
	var args: Dictionary = {}
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--") and "=" in argument:
			var position: int = argument.find("=")
			args[argument.substr(2,position-2)] = argument.substr(position+1)
	check(not Loader.load_verified("res://absent","bad","bad").ok,"Unknown trust pins refused")
	check(not Loader.lookup({},{}).ok,"Missing character package refused")
	check(Loader._hash_valid("a".repeat(64)) and not Loader._hash_valid("g".repeat(64)),"SHA256 hex alphabet is enforced")
	check(Loader.expected_frames().size() == 20,"Complete four-direction primary-pose contract")
	var ordering: Dictionary = Loader.draw_order({"ok":true,"props":Loader.expected_props()},{"y_word":27136})
	check(ordering.ok and ordering.entries[0].id=="object_1" and ordering.entries[1].id=="object_2" and ordering.entries[2].id=="object_3" and ordering.entries[3].kind=="player","Player is inserted after both furniture slots colliding in one bucket")
	check(ordering.placements[6].initial_bucket==416 and ordering.placements[6].assigned_bucket==418,"Occupied buckets advance to the next free slot")
	check(not Loader.draw_order({"ok":true,"props":Loader.expected_props()},{"y_word":0}).ok,"Unverified initial sorting bucket refused")
	check(not Loader.draw_order({"ok":true,"props":Loader.expected_props()},{"y_word":26016},Vector2(544,1537)).ok,"Unverified camera refused")
	if args.has("bundle"):
		source_status = "failed"
		var package: Dictionary = Loader.load_verified(args.bundle,args.get("manifest-sha256",""),args.get("scene-manifest-sha256",""))
		check(package.ok,"Load source-pinned character package: "+str(package.error))
		if package.ok:
			check(package.frames.size() == 20 and package.textures.size() == 20,"All character images preloaded")
			check(package.props.size()==6 and package.foreground_texture is Texture2D and package.foreground_pixels.size()==320*224*4,"Props and source foreground preloaded")
			check(package.presentation.actor_to_video_delay_updates == 3,"Source display delay remains explicit")
			for frame: Dictionary in Loader.expected_frames():
				var state: Dictionary = {"animation_index":frame.animation_index,"animation_cursor":frame.animation_cursor,
					"image_index":frame.image_index,"render_flags_word":1 if frame.baked_mirror_x else 0}
				var result: Dictionary = Loader.lookup(package,state)
				check(result.ok and result.texture is Texture2D and result.frame == frame,"Known source pose resolves: "+frame.file)
				state.render_flags_word ^= 1
				check(not Loader.lookup(package,state).ok,"Wrong mirror refused: "+frame.file)
			check(not Loader.lookup(package,{"animation_index":10,"animation_cursor":12,"image_index":5,"render_flags_word":0}).ok,"Terminator cannot resolve to fallback image")
			var initial: Dictionary = package.profile.initial_state
			var texture: Texture2D = package.textures["2:0"]
			package.textures["2:0"] = null
			check(not Loader.lookup(package,initial).ok,"A key with a null texture is refused")
			package.textures["2:0"] = package.foreground_texture
			check(not Loader.lookup(package,initial).ok,"A key with incorrect source dimensions is refused")
			package.textures["2:0"] = texture
			if failures.is_empty(): source_status="passed"
	var report: Dictionary = {"schema":"ao_pc_character_loader_tests_v1","passed":failures.is_empty(),"checks":checks,
		"source_package_status":source_status,"failures":failures}
	if args.has("report"):
		var file:=FileAccess.open(args.report,FileAccess.WRITE)
		if file == null:
			push_error("Cannot write loader test report")
			quit(1)
			return
		file.store_string(JSON.stringify(report,"  ")+"\n")
	print(JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
