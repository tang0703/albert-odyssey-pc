extends SceneTree
const Loader = preload("res://landing25d_loader.gd")
const Common = preload("res://package_loader.gd")
var errors: Array[String] = []
func _initialize() -> void: call_deferred("run")
func check(value: bool,label: String) -> void:
	if not value: errors.append(label); push_error(label)
func run() -> void:
	var source: String = Loader.default_directory()
	var base: String = ProjectSettings.globalize_path("res://../reports/enhanced25d-landing/negative-loader-"+str(Time.get_ticks_usec()))
	var target: String = base.path_join("enhanced25d-landing")
	DirAccess.make_dir_recursive_absolute(target)
	var pin: Dictionary = Common.read_json("res://landing25d-pin.json")
	for name: String in pin.dependencies:
		DirAccess.make_dir_recursive_absolute(base.path_join(name))
		DirAccess.copy_absolute(source.get_base_dir().path_join(name).path_join("package.json"),base.path_join(name).path_join("package.json"))
	for name: String in DirAccess.get_files_at(source): DirAccess.copy_absolute(source.path_join(name),target.path_join(name))
	check(Loader.load_bundle(target).ok,"Valid closed bundle loads")
	DirAccess.remove_absolute(target.path_join("laia-up.png"))
	check(not Loader.load_bundle(target).ok,"Missing required atlas rejected")
	DirAccess.copy_absolute(source.path_join("laia-up.png"),target.path_join("laia-up.png"))
	var changed := FileAccess.open(target.path_join("laia-up.png"),FileAccess.WRITE);changed.store_string("invalid atlas");changed.close()
	check(not Loader.load_bundle(target).ok,"Changed atlas rejected")
	DirAccess.copy_absolute(source.path_join("laia-up.png"),target.path_join("laia-up.png"))
	var extra := FileAccess.open(target.path_join("unapproved.gd"),FileAccess.WRITE);extra.store_string("extends Node");extra.close()
	check(not Loader.load_bundle(target).ok,"Unapproved script rejected")
	DirAccess.remove_absolute(target.path_join("unapproved.gd"))
	var dependency := FileAccess.open(base.path_join("room/package.json"),FileAccess.WRITE);dependency.store_string("{}");dependency.close()
	check(not Loader.load_bundle(target).ok,"Changed old source dependency rejected")
	var result: Dictionary={"passed":errors.is_empty(),"checks":5,"failures":errors,"performance_tested":false}
	var report := FileAccess.open("res://../reports/enhanced25d-landing/loader.json",FileAccess.WRITE);report.store_string(JSON.stringify(result,"\t"));report.close()
	print(JSON.stringify(result));quit(0 if errors.is_empty() else 1)
