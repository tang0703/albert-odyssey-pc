extends SceneTree
const Fighter = preload("res://fighter.gd")
var checks: int = 0
var hit_count: int = 0
var completed_count: int = 0
var fixture_path: String = "user://animation-unit-texture.tres"

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message)
		quit(1)
		assert(value, message)

func sprite_definition() -> Dictionary:
	var result: Dictionary = {"renderer": "sprite", "anchor": [0.25, 0.9], "scale": 0.5, "default_facing": "left", "states": {}}
	for state: String in ["idle", "attack", "hurt", "down"]:
		result["states"][state] = {"frames": [fixture_path, fixture_path, fixture_path], "durations": [0.1, 0.2, 0.3], "loop": state == "idle"}
	result["states"]["attack"]["hit_frame"] = 1
	return result

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var texture := GradientTexture2D.new()
	texture.gradient = Gradient.new()
	texture.width = 8
	texture.height = 12
	check(ResourceSaver.save(texture, fixture_path) == OK, "synthetic fixture saved in user data")
	var fighter := Fighter.new()
	fighter.set_process(false)
	check(fighter.configure(sprite_definition()).is_empty(), "sprite definition accepted")
	check(fighter.texture_cache.size() == 1 and fighter.configured, "all frames preloaded once per fighter")
	check(is_equal_approx(fighter.animation_duration("attack"), 0.6) and is_equal_approx(fighter.hit_time(), 0.1), "authored durations and hit point")
	fighter.advance_animation(0.15)
	check(fighter.frame_index == 1, "variable frame duration")
	fighter.advance_animation(0.5)
	check(fighter.frame_index == 0 and not fighter.is_animation_finished(), "idle loops with remainder")
	fighter.set_animation("attack")
	check(fighter.frame_index == 0 and fighter.animation_elapsed == 0.0, "state transition restarts at first frame")
	fighter.animation_hit.connect(func(_name: String) -> void: hit_count += 1)
	fighter.animation_completed.connect(func(_name: String) -> void: completed_count += 1)
	fighter.advance_animation(0.09)
	check(hit_count == 0, "attack has not hit early")
	fighter.advance_animation(0.02)
	check(hit_count == 1 and completed_count == 0, "attack hits exactly on authored frame")
	fighter.advance_animation(1.0)
	fighter.advance_animation(1.0)
	check(hit_count == 1 and completed_count == 1 and fighter.frame_index == 2, "single hit and completion even with large deltas")
	fighter.set_animation("attack")
	fighter.advance_animation(0.2)
	fighter.set_animation("attack")
	check(fighter.frame_index == 0 and fighter.animation_elapsed == 0.0, "restarting same attack resets its clock")
	fighter.set_animation("hurt")
	fighter.advance_animation(2.0)
	check(fighter.frame_index == 2 and fighter.is_animation_finished(), "hurt plays once")
	fighter.set_animation("down")
	fighter.advance_animation(2.0)
	fighter.advance_animation(20.0)
	check(fighter.frame_index == 2 and is_equal_approx(fighter.animation_elapsed, 0.6), "down holds last frame indefinitely")
	fighter.set_animation("attack")
	fighter.playback_speed = 0.0
	fighter.advance_animation(10.0)
	check(fighter.animation_elapsed == 0.0, "paused animation cannot advance")
	fighter.playback_speed = 2.0
	fighter.advance_animation(0.16)
	check(fighter.frame_index == 2 and is_equal_approx(fighter.animation_elapsed, 0.32), "double speed only affects animation time")
	fighter.facing = 1.0
	check(fighter.facing_multiplier() == -1.0, "left-authored art mirrors to face right")
	fighter.facing = -1.0
	check(fighter.facing_multiplier() == 1.0, "left-authored art stays unchanged facing left")
	var cache_before: Texture2D = fighter.texture_cache[fixture_path]
	root.add_child(fighter)
	await process_frame
	check(fighter.texture_cache[fixture_path] == cache_before, "draw and tree entry do not reload textures")
	var second := Fighter.new()
	check(second.configure(sprite_definition()).is_empty(), "second fighter configured")
	check(second.texture_cache[fixture_path] != cache_before, "textures have per-fighter lifetime without a global cache")
	fighter.set_animation("attack")
	fighter.playback_speed = 1.0
	second.set_animation("attack")
	fighter.advance_animation(0.37)
	for _step: int in range(37):
		second.advance_animation(0.01)
	check(fighter.frame_index == second.frame_index and is_equal_approx(fighter.animation_elapsed, second.animation_elapsed), "animation state independent of delta partition")
	var before_invalid_delta: float = fighter.animation_elapsed
	fighter.advance_animation(-1.0)
	fighter.advance_animation(NAN)
	check(fighter.animation_elapsed == before_invalid_delta, "negative and nonfinite deltas cannot mutate playback")
	second.free()
	var same_definition: Dictionary = sprite_definition()
	for mutation: String in ["missing", "empty", "duration_count", "zero", "nonfinite", "loop", "hit", "path", "anchor", "scale", "facing", "implicit_sprite"]:
		var bad: Dictionary = same_definition.duplicate(true)
		match mutation:
			"missing": bad["states"].erase("down")
			"empty": bad["states"]["hurt"]["frames"] = []
			"duration_count": bad["states"]["idle"]["durations"] = [0.1]
			"zero": bad["states"]["idle"]["durations"][0] = 0.0
			"nonfinite": bad["states"]["attack"]["durations"][0] = NAN
			"loop": bad["states"]["down"]["loop"] = true
			"hit": bad["states"]["attack"]["hit_frame"] = 3
			"path": bad["states"]["attack"]["frames"][0] = "res://does-not-exist.png"
			"anchor": bad["anchor"] = [0.5, 2.0]
			"scale": bad["scale"] = -1.0
			"facing": bad["default_facing"] = "up"
			"implicit_sprite": bad.erase("renderer")
		check(not fighter.configure(bad).is_empty() and not fighter.configured and fighter.texture_cache.is_empty(), "reject invalid " + mutation + " without fallback")
	check(fighter.configure({"renderer": "procedural", "shape": "shield"}).is_empty(), "explicit procedural mode accepted")
	check(fighter.texture_cache.is_empty() and fighter.renderer == "procedural", "procedural mode needs no textures")
	check(fighter.configure({"states": {"idle": [], "attack": [], "hurt": [], "down": []}}).is_empty(), "legacy empty placeholders remain compatible")
	fighter.state = "attack"
	fighter.advance_animation(1.0)
	check(fighter.is_animation_finished(), "legacy state setter follows bounded animation")
	check(not fighter.set_animation("unknown"), "unknown playback state rejected")
	fighter.free()
	DirAccess.remove_absolute(fixture_path)
	print("BATTLE ANIMATION: %d checks passed" % checks)
	quit()
