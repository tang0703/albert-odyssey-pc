extends SceneTree
## Hardware-only atlas/standalone equivalence; art acceptance remains separate.
## -- --art-directory=ABS --art-manifest-sha256=SHA --report=ABS.json
const SpriteLayer = preload("res://character_layer.gd")
const PriorityShader = preload("res://character_priority.gdshader")
const BACKGROUND := Color8(17, 29, 53)
# Atlas UVs have a different floating-point scale than standalone texture UVs.
# Permit at most one RGBA8 code value after LINEAR filtering, while always
# recording exact inequality counts and hashes. Spatial foreground stays exact.
const LINEAR_CHANNEL_TOLERANCE: int = 1

var arguments: Dictionary = {}
var failures: Array[String] = []
var cases: Array[Dictionary] = []
var sources: Dictionary = {}
var total_pixels: int = 0

func _initialize() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--") and "=" in argument:
			var split: int = argument.find("=")
			arguments[argument.substr(2, split - 2)] = argument.substr(split + 1)
	if DisplayServer.get_name() == "headless":
		push_error("HD atlas equivalence requires an actual GPU; no headless acceptance.")
		quit(2)
		return
	call_deferred("_run")

func _hash(raw: PackedByteArray) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(raw)
	return context.finish().hex_encode()

func _load_png(directory: String, name: String, identity: Dictionary, dimensions: Vector2i) -> Image:
	if name.is_absolute_path() or ".." in name.split("/") or "\\" in name:
		failures.append("Unsafe art path: " + name)
		return null
	var path: String = directory.path_join(name)
	var raw: PackedByteArray = FileAccess.get_file_as_bytes(path)
	if raw.size() != int(identity.get("bytes", -1)) or _hash(raw) != identity.get("sha256", ""):
		failures.append("Art payload hash/size mismatch: " + name)
		return null
	sources[path] = _hash(raw)
	var image := Image.new()
	if image.load_png_from_buffer(raw) != OK or image.get_size() != dimensions or image.get_format() != Image.FORMAT_RGBA8:
		failures.append("Invalid RGBA art dimensions: " + name)
		return null
	return image

func _foreground(size: Vector2i) -> Image:
	# Nonuniform map-coordinate colors expose wrong spatial UVs, not only alpha.
	var image := Image.create(size.x, size.y, false, Image.FORMAT_RGBA8)
	image.fill(Color.TRANSPARENT)
	for y: int in range(size.y):
		for x: int in range(size.x):
			if (x / 11 + y / 13) % 3 != 0:
				image.set_pixel(x, y, Color8(130 + x % 90, 35 + y % 120, 17 + (x + y) % 70))
	return image

func _render(texture: Texture2D, rectangle: Rect2, foreground: Image, shader_enabled: bool) -> Image:
	var viewport := SubViewport.new()
	viewport.size = foreground.get_size()
	viewport.disable_3d = true
	viewport.transparent_bg = false
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_LINEAR
	root.add_child(viewport)
	var background: Image = foreground.duplicate()
	for y: int in range(background.get_height()):
		for x: int in range(background.get_width()):
			if background.get_pixel(x, y).a == 0.0: background.set_pixel(x, y, BACKGROUND)
	var background_layer := SpriteLayer.new()
	viewport.add_child(background_layer)
	background_layer.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	background_layer.show_sprite(ImageTexture.create_from_image(background), Rect2(Vector2.ZERO, Vector2(viewport.size)), null, 0)
	var material: ShaderMaterial = null
	if shader_enabled:
		material = ShaderMaterial.new()
		material.shader = PriorityShader
		material.set_shader_parameter("source_foreground", ImageTexture.create_from_image(foreground))
		material.set_shader_parameter("canvas_size", Vector2(viewport.size))
	var layer := SpriteLayer.new()
	viewport.add_child(layer)
	layer.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	layer.show_sprite(texture, rectangle, material, 1)
	await process_frame
	await RenderingServer.frame_post_draw
	var result: Image = viewport.get_texture().get_image()
	result.convert(Image.FORMAT_RGBA8)
	viewport.queue_free()
	await process_frame
	return result

func _compare(reference: Image, actual: Image) -> Dictionary:
	var left: PackedByteArray = reference.get_data()
	var right: PackedByteArray = actual.get_data()
	var mismatches: int = 0
	var max_delta: int = 0
	var first: Array[Dictionary] = []
	for offset: int in range(0, left.size(), 4):
		var different: bool = false
		for channel: int in range(4):
			var delta: int = absi(int(left[offset + channel]) - int(right[offset + channel]))
			max_delta = maxi(max_delta, delta)
			different = different or delta != 0
		if different:
			mismatches += 1
			if first.size() < 8:
				first.append({"pixel": [(offset / 4) % reference.get_width(), (offset / 4) / reference.get_width()],
					"standalone_rgba": Array(left.slice(offset, offset + 4)), "atlas_rgba": Array(right.slice(offset, offset + 4))})
	total_pixels += reference.get_width() * reference.get_height()
	return {"passed": max_delta <= LINEAR_CHANNEL_TOLERANCE, "exact_equal": mismatches == 0,
		"mismatched_pixels": mismatches, "max_channel_delta": max_delta,
		"allowed_channel_delta": LINEAR_CHANNEL_TOLERANCE, "compared_pixels": reference.get_width() * reference.get_height(),
		"reference_rgba_sha256": _hash(left), "atlas_rgba_sha256": _hash(right), "first_mismatches": first}

func _spatial_checks(source: Image, rectangle: Rect2, foreground: Image, plain: Image, shaded: Image) -> Dictionary:
	var covered: int = 0
	var uncovered: int = 0
	var edge_samples: int = 0
	var mismatches: int = 0
	# The stage background already contains the same foreground color. When the
	# shader replaces sprite RGB with it, compositing must preserve that color
	# for ANY sprite alpha. No independent GPU alpha-rounding model is assumed.
	for y: int in range(floori(rectangle.position.y), ceili(rectangle.end.y)):
		for x: int in range(floori(rectangle.position.x), ceili(rectangle.end.x)):
			if x < 0 or y < 0 or x >= shaded.get_width() or y >= shaded.get_height(): continue
			var uv: Vector2 = (Vector2(x + 0.5, y + 0.5) - rectangle.position) / rectangle.size
			if uv.x < 0.0 or uv.y < 0.0 or uv.x >= 1.0 or uv.y >= 1.0: continue
			var coordinate: Vector2 = uv * Vector2(source.get_size()) - Vector2(0.5, 0.5)
			var min_alpha: float = 1.0
			var max_alpha: float = 0.0
			for oy: int in range(2):
				for ox: int in range(2):
					var alpha: float = source.get_pixel(clampi(floori(coordinate.x) + ox, 0, 511), clampi(floori(coordinate.y) + oy, 0, 511)).a
					min_alpha = minf(min_alpha, alpha)
					max_alpha = maxf(max_alpha, alpha)
			if max_alpha == 0.0: continue
			if min_alpha < 1.0: edge_samples += 1
			if foreground.get_pixel(x, y).a == 0.0:
				uncovered += 1
				if shaded.get_pixel(x, y).to_rgba32() != plain.get_pixel(x, y).to_rgba32(): mismatches += 1
			else:
				covered += 1
				if shaded.get_pixel(x, y).to_rgba32() != foreground.get_pixel(x, y).to_rgba32(): mismatches += 1
	return {"passed": mismatches == 0 and covered > 0 and uncovered > 0 and edge_samples > 0,
		"covered_pixels": covered, "uncovered_pixels": uncovered,
		"linear_edge_samples": edge_samples, "mismatched_pixels": mismatches,
		"scope": "Independent map-position foreground color at all covered body samples including partial alpha; uncovered pixels match unshaded reference."}

func _case(row: Dictionary, source: Image, atlas_image: Image, factor: float) -> void:
	var standalone: Texture2D = ImageTexture.create_from_image(source)
	var atlas := AtlasTexture.new()
	atlas.atlas = ImageTexture.create_from_image(atlas_image)
	atlas.region = Rect2(float(row.rect[0]), float(row.rect[1]), 512.0, 512.0)
	atlas.filter_clip = true
	var size := Vector2i(roundi(320.0 * factor), roundi(224.0 * factor))
	var foreground: Image = _foreground(size)
	var rectangle := Rect2(Vector2(137.33, 91.67) * factor, Vector2(512.0, 512.0) * float(row.display_scale) * factor)
	var plain: Image = await _render(standalone, rectangle, foreground, false)
	var atlas_plain: Image = await _render(atlas, rectangle, foreground, false)
	var shaded: Image = await _render(standalone, rectangle, foreground, true)
	var atlas_shaded: Image = await _render(atlas, rectangle, foreground, true)
	var plain_result: Dictionary = _compare(plain, atlas_plain)
	var shaded_result: Dictionary = _compare(shaded, atlas_shaded)
	var spatial: Dictionary = _spatial_checks(source, rectangle, foreground, plain, shaded)
	var passed: bool = plain_result.passed and shaded_result.passed and spatial.passed
	if not passed: failures.append("GPU atlas/spatial mismatch: %s scale %.2f" % [row.id, factor])
	cases.append({"id": row.id, "factor": factor, "atlas_cell": row.cell, "canvas": [size.x, size.y],
		"rect": [rectangle.position.x, rectangle.position.y, rectangle.size.x, rectangle.size.y],
		"texture_filter": "LINEAR", "atlas_filter_clip": true, "passed": passed,
		"unshaded_equivalence": plain_result, "priority_shader_equivalence": shaded_result, "spatial_uv": spatial})

func _run() -> void:
	root.min_size = Vector2i(1, 1)
	root.size = Vector2i(400, 280)
	root.title = "HD atlas GPU equivalence verification"
	var adapter: String = RenderingServer.get_video_adapter_name()
	if adapter.is_empty() or "llvmpipe" in adapter.to_lower() or "swiftshader" in adapter.to_lower(): failures.append("Actual hardware GPU identity is required")
	var directory: String = str(arguments.get("art-directory", ""))
	var manifest_path: String = directory.path_join("manifest.json")
	var raw: PackedByteArray = FileAccess.get_file_as_bytes(manifest_path)
	var art: Variant = JSON.parse_string(raw.get_string_from_utf8())
	if not directory.is_absolute_path() or _hash(raw) != arguments.get("art-manifest-sha256", "") or not art is Dictionary or art.get("schema") != "ao_character_hd_art_v1":
		failures.append("Explicit matching art directory and manifest hash are required")
	else:
		sources[manifest_path] = _hash(raw)
		var selections: Dictionary = {"down": 0, "left": 5, "right": 11, "up": 12}
		for direction: String in selections:
			var selected: Dictionary = {}
			for row: Dictionary in art.frames:
				if row.direction == direction and int(row.cell) == int(selections[direction]): selected = row
			if selected.is_empty():
				failures.append("Required real HD pose is missing: " + direction)
				continue
			var atlas_name: String = "atlases/" + direction + ".png"
			var source: Image = _load_png(directory, selected.file, art.files[selected.file], Vector2i(512, 512))
			var atlas: Image = _load_png(directory, atlas_name, art.files[atlas_name], Vector2i(2048, 2048))
			if source == null or atlas == null: continue
			var region := Rect2i(int(selected.rect[0]), int(selected.rect[1]), 512, 512)
			if atlas.get_region(region).get_data() != source.get_data():
				failures.append("Atlas pixels differ from the selected frame: " + direction)
				continue
			for factor: float in [1.0, 2.75]: await _case(selected, source, atlas, factor)
	for path: String in sources:
		if FileAccess.get_sha256(path) != sources[path]: failures.append("Input changed during GPU verification: " + path)
	var report: Dictionary = {"schema": "ao_character_hd_gpu_compositor_validation_v1", "passed": failures.is_empty() and cases.size() == 8,
		"headless": false, "display_server": DisplayServer.get_name(), "adapter": adapter,
		"rendering_method": RenderingServer.get_current_rendering_method(), "godot_version": Engine.get_version_info(),
		"cases": cases, "compared_pixels": total_pixels, "failures": failures, "source_file_sha256": sources,
		"art_review_status": art.get("review_status", "unknown") if art is Dictionary else "unknown",
		"scope": "GPU ImageTexture-versus-AtlasTexture and independent spatial UV checks, not final animation/art acceptance.",
		"inputs": {"shader_sha256": FileAccess.get_sha256("res://character_priority.gdshader"),
			"layer_sha256": FileAccess.get_sha256("res://character_layer.gd"), "harness_sha256": FileAccess.get_sha256("res://tests/test_character_hd_compositor.gd")}}
	var output: FileAccess = FileAccess.open(str(arguments.get("report", "")), FileAccess.WRITE)
	if output == null:
		push_error("Cannot write HD GPU report")
		quit(1)
		return
	output.store_string(JSON.stringify(report, "  ") + "\n")
	print(JSON.stringify({"passed": report.passed, "cases": cases.size(), "compared_pixels": total_pixels, "failures": failures}))
	quit(0 if report.passed else 1)
