extends SceneTree
## Deterministic assembly of approved imagegen atlases; does not redraw artwork.
const PROJECT := "res://"
const ATLAS_DIR := "res://art/atlases/round2/"
const OUTPUT_DIR := "res://battle-demo/assets/round2/"
const FRAME_SIZE := 512
const CELL_SIZE := 320
const FOOT_Y := 448
const STATES: Array[String] = ["idle", "attack", "hurt", "down"]
const COUNTS: Array[int] = [4, 6, 2, 4]
const DURATIONS: Dictionary = {
	"idle": [0.22, 0.22, 0.22, 0.22],
	"attack": [0.10, 0.12, 0.12, 0.10, 0.12, 0.14],
	"hurt": [0.14, 0.18],
	"down": [0.13, 0.16, 0.18, 0.30],
}
const CHARACTERS: Array[Dictionary] = [
	{"id": "pike", "slot": "guardian", "display_name": "派克", "default_facing": "left", "scale": 0.52},
	{"id": "weredog", "slot": "scout", "display_name": "WEREDOG", "default_facing": "right", "scale": 0.50},
]
var issues: Array[String] = []

func _initialize() -> void:
	call_deferred("build")

func alpha_bounds(image: Image, threshold: float) -> Rect2i:
	var minimum := Vector2i(image.get_width(), image.get_height())
	var maximum := Vector2i(-1, -1)
	for y: int in range(image.get_height()):
		for x: int in range(image.get_width()):
			if image.get_pixel(x, y).a > threshold:
				minimum.x = mini(minimum.x, x)
				minimum.y = mini(minimum.y, y)
				maximum.x = maxi(maximum.x, x)
				maximum.y = maxi(maximum.y, y)
	if maximum.x < 0:
		return Rect2i()
	return Rect2i(minimum, maximum - minimum + Vector2i.ONE)

func array_rect(rect: Rect2i) -> Array[int]:
	return [rect.position.x, rect.position.y, rect.size.x, rect.size.y]

func write_json(path: String, data: Variant) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		issues.append("Cannot write " + path)
		return
	file.store_string(JSON.stringify(data, "\t") + "\n")
	file.close()

func build() -> void:
	var write_config: bool = "--write-config" in OS.get_cmdline_user_args()
	var manifest: Dictionary = {"schema": "battle_assets_v1", "assets": []}
	var report: Dictionary = {"schema": "battle_art_assembly_v1", "cell_size": CELL_SIZE, "frame_size": FRAME_SIZE, "uniform_resize": 1.6, "foot_y": FOOT_Y, "alpha_alignment_threshold": 0.5, "characters": []}
	var appearances: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://battle-demo/data/appearances.json"))
	for character: Dictionary in CHARACTERS:
		var id: String = character["id"]
		var atlas_path: String = ATLAS_DIR + id + "-atlas.png"
		var atlas := Image.load_from_file(atlas_path)
		if atlas == null or atlas.get_size() != Vector2i(1254, 1254):
			issues.append("Expected approved 1254x1254 atlas: " + atlas_path)
			continue
		var original_size: Vector2i = atlas.get_size()
		atlas.convert(Image.FORMAT_RGBA8)
		# Normalize the entire generated grid once. All frames receive exactly the
		# same 1280/1254 factor before the fixed 320-to-512 cell enlargement.
		atlas.resize(1280, 1280, Image.INTERPOLATE_LANCZOS)
		var output: String = OUTPUT_DIR + id + "/"
		DirAccess.make_dir_recursive_absolute(output)
		var stats: Dictionary = {"id": id, "source_sha256": FileAccess.get_sha256(atlas_path), "source_size": [original_size.x, original_size.y], "normalized_atlas_size": [1280, 1280], "atlas_resize_factor": 1280.0 / 1254.0, "frames": []}
		var states: Dictionary = {}
		var atlas_index: int = 0
		for state_index: int in range(STATES.size()):
			var state_name: String = STATES[state_index]
			var paths: Array[String] = []
			for frame_index: int in range(COUNTS[state_index]):
				var rect := Rect2i((atlas_index % 4) * CELL_SIZE, (atlas_index / 4) * CELL_SIZE, CELL_SIZE, CELL_SIZE)
				var cell: Image = atlas.get_region(rect)
				var source_bounds := alpha_bounds(cell, 0.5)
				if source_bounds.size.x < 40 or source_bounds.size.y < 40:
					issues.append("Empty or tiny source frame: " + id + " " + str(atlas_index))
					continue
				cell.resize(FRAME_SIZE, FRAME_SIZE, Image.INTERPOLATE_LANCZOS)
				var resized_bounds := alpha_bounds(cell, 0.5)
				var y_shift: int = FOOT_Y - (resized_bounds.end.y - 1)
				var output_image := Image.create(FRAME_SIZE, FRAME_SIZE, false, Image.FORMAT_RGBA8)
				output_image.fill(Color.TRANSPARENT)
				output_image.blit_rect(cell, Rect2i(0, 0, FRAME_SIZE, FRAME_SIZE), Vector2i(0, y_shift))
				var bounds := alpha_bounds(output_image, 0.5)
				var low_alpha_bounds := alpha_bounds(output_image, 0.02)
				if bounds.end.y - 1 != FOOT_Y:
					issues.append("Foot alignment mismatch: " + id + " " + str(atlas_index))
				if low_alpha_bounds.position.x <= 0 or low_alpha_bounds.position.y <= 0 or low_alpha_bounds.end.x >= FRAME_SIZE or low_alpha_bounds.end.y >= FRAME_SIZE:
					issues.append("Nontransparent image boundary: " + id + " " + str(atlas_index))
				var file_name: String = "%s-%02d.png" % [state_name, frame_index]
				var path: String = output + file_name
				if output_image.save_png(path) != OK:
					issues.append("Cannot save " + path)
				var asset_path: String = "assets/round2/" + id + "/" + file_name
				paths.append("res://" + asset_path)
				manifest["assets"].append({"path": asset_path, "sha256": FileAccess.get_sha256(path), "role": "sprite", "character": id})
				stats["frames"].append({"state": state_name, "index": frame_index, "atlas_index": atlas_index, "source_rect": array_rect(rect), "source_alpha_bounds": array_rect(source_bounds), "output_alpha_bounds": array_rect(bounds), "low_alpha_bounds": array_rect(low_alpha_bounds), "y_translation": y_shift, "sha256": FileAccess.get_sha256(path)})
				atlas_index += 1
			states[state_name] = {"frames": paths, "durations": DURATIONS[state_name], "loop": state_name == "idle"}
			if state_name == "attack":
				states[state_name]["hit_frame"] = 3
		report["characters"].append(stats)
		var appearance: Dictionary = appearances[character["slot"]]
		appearance["renderer"] = "sprite"
		appearance["display_name"] = character["display_name"]
		appearance["default_facing"] = character["default_facing"]
		appearance["scale"] = character["scale"]
		appearance["anchor"] = [0.5, 0.875]
		appearance["states"] = states
	for slot: String in ["mage", "healer", "armor", "enemy_mage"]:
		appearances[slot]["renderer"] = "procedural"
		appearances[slot]["default_facing"] = "right"
	report["issues"] = issues
	report["passed"] = issues.is_empty() and manifest["assets"].size() == 32
	DirAccess.make_dir_recursive_absolute("res://reports")
	write_json("res://reports/battle-art-assembly.json", report)
	if not report["passed"]:
		for issue: String in issues:
			push_error(issue)
		quit(1)
		return
	if write_config:
		write_json("res://battle-demo/data/appearances.json", appearances)
		write_json("res://battle-demo/data/asset-manifest.json", manifest)
	else:
		write_json("res://reports/battle-appearances-candidate.json", appearances)
		write_json("res://reports/battle-asset-manifest-candidate.json", manifest)
	print("BATTLE ART: 32 RGBA frames built, 512x512, fixed scale 1.6, foot y448; config=" + str(write_config))
	quit(0 if issues.is_empty() else 1)
