extends SceneTree
const HD = preload("res://character_hd_animation.gd")
const HDLoader = preload("res://character_hd_loader.gd")
const Original = preload("res://character_animation_core.gd")
const Movement = preload("res://movement_core.gd")
const Common = preload("res://package_loader.gd")
var checks: int = 0
var failures: Array[String] = []
var arguments: Dictionary = {}
var source_updates: int = 0

func check(value: bool, message: String) -> void:
	checks+=1
	if not value:
		failures.append(message)
		push_error(message)

func state(heading: int, primary: int, timer: int, moving: bool = true) -> Dictionary:
	var result: Dictionary = {}
	for key: String in Original.FIELDS: result[key]=0
	result.merge({"heading":heading,"status_word":0x8182 if moving else 0x8180,"flags_word":9,
		"animation_root":Original.ANIMATION_ROOT,"image_table_root":Original.IMAGE_TABLE_ROOT,
		"animation_index":heading+(8 if moving else 0),"animation_cursor":primary*3 if moving else 0,
		"animation_timer":timer,"animation_duration":10 if moving else 1,"render_flags_word":1 if heading==0 else 0,
		"image_index":int(HD.WALK_IMAGES[heading])+primary if moving else int(HD.IDLE_IMAGES[heading])},true)
	return result

func _initialize() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--") and "=" in arg:
			var equal: int = arg.find("=")
			arguments[arg.substr(2,equal-2)]=arg.substr(equal+1)
	for heading: int in [0,2,4,6]:
		for primary: int in 4:
			var counts: Array[int] = [0,0,0]
			for timer: int in 10:
				var input: Dictionary = state(heading,primary,timer)
				var before: Dictionary = input.duplicate(true)
				var selected: Dictionary = HD.select(input)
				check(selected.ok and selected.walk_index==primary*3+int(floor(timer*3.0/10.0)),"Discrete HD phase matches original primary interval")
				counts[selected.subframe_index]+=1
				check(input==before,"HD never writes original state")
			check(counts==[4,3,3],"Ten original updates partition into 4/3/3 integer observations")
			for boundary: Array in [[3,1.0/3.0-0.000001,0],[3,1.0/3.0+0.000001,1],[6,2.0/3.0-0.000001,1],[6,2.0/3.0+0.000001,2]]:
				check(HD.select(state(heading,primary,boundary[0]),boundary[1]).subframe_index==boundary[2],"Fractional phase changes at exact thirds")
		for timer: int in 10:
			check(HD.select(state(heading,0,timer,false),0.999).action=="idle","Stop with preserved old timer selects only idle")
	var frozen: Dictionary = state(2,2,6)
	var frozen_selection: Dictionary = HD.select(frozen,0.75)
	for repeat_index: int in 100:
		check(HD.select(frozen,0.75)==frozen_selection,"Paused render phase remains frozen")
	for heading: int in [0,4,6]:
		check(HD.select(state(heading,2,6),0.75).walk_index==8,"Turn preserves source primary/timer phase")
	for fps: int in [30,60,120]:
		# Same absolute source time reached through different render partitions.
		for second_frame: int in range(fps*2):
			var time: float = float(second_frame)/float(fps)
			var source_time: float = time*float(Movement.TICK_DENOMINATOR)/float(Movement.TICK_NUMERATOR)
			var tick: int = int(floor(source_time))
			var phase: float = source_time-tick
			var selected: Dictionary = HD.select(state(2,(tick%40)/10,tick%10),phase)
			check(selected.ok and selected.walk_index==int(floor(fmod(source_time,40.0)*3.0/10.0)),"30/60/120 render partition has no independent HD clock")
	for phase: float in [-0.1,1.0,INF,NAN]: check(not HD.select(frozen,phase).ok,"Invalid render phase rejected")
	check(not HD.select({}).ok,"Missing state rejected")
	check(not HDLoader.load_verified("missing","bad","bad","bad").ok,"HD loader requires trusted pins")
	check(not HDLoader.lookup({},{}).ok,"No HD placeholder for missing package")
	check(not HDLoader.validate_appearances({}).ok,"Incomplete HD appearances rejected")
	for pair: Array in [["heading",1],["animation_timer",10],["animation_cursor",2],["animation_duration",1],["image_index",99],["animation_root",0],["render_flags_word",1]]:
		var bad: Dictionary = frozen.duplicate(true)
		bad[pair[0]]=pair[1]
		check(not HD.select(bad).ok,"Invalid source cache refused: "+str(pair[0]))
	if arguments.has("fixtures"): source_checks()
	if arguments.has("hd-fixture"): loader_checks()
	var result: Dictionary = {"schema":"ao_pc_character_hd_core_tests_v1","passed":failures.is_empty(),"checks":checks,
		"source_updates":source_updates,"source_comparison_status":"passed" if source_updates>0 and failures.is_empty() else "not_run",
		"actual_hd_assets":"not_run","failures":failures}
	if arguments.has("report"):
		var file: FileAccess = FileAccess.open(arguments.report,FileAccess.WRITE)
		if file!=null: file.store_string(JSON.stringify(result,"\t")+"\n")
	print(JSON.stringify(result))
	quit(0 if failures.is_empty() else 1)

func loader_checks() -> void:
	var directory: String = arguments["hd-fixture"]
	var bundle: Dictionary = HDLoader.load_verified(directory,FileAccess.get_sha256(directory.path_join("package.json")),"a".repeat(64),"b".repeat(64))
	if not bundle.ok:
		check(false,"Synthetic loader fixture failed: "+str(bundle.error))
		return
	check(bundle.preloaded and bundle.frames.size()==52 and bundle.atlases.size()==4,"All HD atlas textures preload before play")
	for heading: int in [0,2,4,6]:
		for primary: int in 4:
			for timer: int in [0,4,7]:
				var selection: Dictionary = HD.select(state(heading,primary,timer))
				var found: Dictionary = HDLoader.lookup(bundle,selection)
				check(found.ok and found.texture is AtlasTexture and found.frame.anchor==found.frame.actor_anchor,"Each HD frame resolves to a preloaded atlas and actor origin")
		check(HDLoader.lookup(bundle,HD.select(state(heading,0,0,false))).ok,"All four idles preload")
	var key: String = "map001_player_hd/down/idle"
	var selected: Dictionary = HD.select(state(2,0,0,false))
	bundle.textures[key]=null
	check(not HDLoader.lookup(bundle,selected).ok,"Missing loaded texture refuses rather than falling back")
	var value: Variant = Common.read_json(directory.path_join("appearances.json"))
	for pair: Array in [["actor_anchor",[256,700]],["ground_anchor",[0,0]],["display_scale",0],["cell",true],["rect",[0,0,511,512]]]:
		var bad: Dictionary = value.duplicate(true)
		bad.frames[0][pair[0]]=pair[1]
		check(not HDLoader.validate_appearances(bad).ok,"HD geometry fault rejected: "+str(pair[0]))

func source_checks() -> void:
	var fixture: Variant = Common.read_json(arguments.fixtures)
	var bundle: Dictionary = Common.load_bundle(Common.default_directory())
	if not fixture is Dictionary or not bundle.get("ok",false):
		check(false,"Source fixture and verified scene are required")
		return
	var character_dir: String = ProjectSettings.globalize_path("res://generated/character")
	var original := Original.new()
	var movement := Movement.new()
	check(original.configure(fixture.profile,FileAccess.get_file_as_bytes(character_dir.path_join("animation-bank.bin")),FileAccess.get_file_as_bytes(character_dir.path_join("image-table.bin"))).ok,"Original source model configures")
	check(movement.configure(bundle.profile,bundle.flags).ok,"Unchanged movement model configures")
	for trace: Dictionary in fixture.traces:
		var position: Dictionary = movement.initial_state()
		var animated: Dictionary = original.initial_state()
		for row: Dictionary in trace.updates:
			var moved: Dictionary = movement.step_game_input(position,int(row.game_pad_word))
			var advanced: Dictionary = original.step_after_movement(animated,moved)
			if not moved.ok or not advanced.ok:
				check(false,"Source trace must apply without injected later state")
				return
			var snapshot: Dictionary = moved.state.duplicate(true)
			var cache: Dictionary = advanced.state.duplicate(true)
			for phase: float in [0.0,0.25,0.5,0.75,0.999]: check(HD.select(advanced.state,phase).ok,"HD accepts observed source stop/start/turn phase")
			check(moved.state==snapshot and advanced.state==cache,"HD selection leaves movement and animation bit-identical")
			for key: String in Movement.FIELDS: check(int(moved.state[key])==int(row.expected[key]),"HD/original source movement equals recorded state")
			position=moved.state
			animated=advanced.state
			source_updates+=1
