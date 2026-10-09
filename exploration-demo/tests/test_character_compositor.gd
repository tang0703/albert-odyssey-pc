extends SceneTree
## Real Compatibility/GPU readback. Headless discovery explicitly skips.
## -- --report=ABSOLUTE.json [--fixtures=ABSOLUTE.json]
const SpriteLayer = preload("res://character_layer.gd")
const PriorityShader = preload("res://character_priority.gdshader")

var arguments: Dictionary = {}
var failures: Array[String] = []
var case_reports: Array[Dictionary] = []
var total_pixels: int = 0
var source_files: Dictionary = {}
var source_fixture_status: String = "not_run"

func _initialize() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--") and "=" in argument:
			var split: int = argument.find("=")
			arguments[argument.substr(2, split - 2)] = argument.substr(split + 1)
	if DisplayServer.get_name() == "headless":
		print("SKIP_REAL_GPU_REQUIRED: character compositor has not been GPU validated in this invocation")
		quit(0)
		return
	call_deferred("_run")

func _solid(width: int, height: int, color: Color) -> Image:
	var image: Image = Image.create(width, height, false, Image.FORMAT_RGBA8)
	image.fill(color)
	return image

func _synthetic() -> Array[Dictionary]:
	var size: Vector2i = Vector2i(9, 7)
	var foreground: Image = _solid(size.x, size.y, Color.TRANSPARENT)
	var background: Image = _solid(size.x, size.y, Color8(16, 32, 64))
	for y: int in range(size.y):
		for x: int in range(size.x):
			if (x + 2 * y) % 3 != 0:
				var color: Color = Color8(190 + x * 3, 34 + y * 5, 17 + x + y)
				foreground.set_pixel(x, y, color)
				background.set_pixel(x, y, color)
	var low: Image = _solid(4, 3, Color.TRANSPARENT)
	var high: Image = _solid(4, 3, Color.TRANSPARENT)
	for y: int in range(3):
		for x: int in range(4):
			low.set_pixel(x, y, Color8(19 + x * 13, 120 + y * 17, 40 + x * 11))
			high.set_pixel(x, y, Color8(33 + y * 23, 44 + x * 11, 180 + y * 17))
	# Sprite-alpha holes must not erase an earlier writer, even where foreground
	# is opaque. Independent foreground-alpha holes must show the low sprite.
	low.set_pixel(1, 1, Color.TRANSPARENT)
	high.set_pixel(2, 1, Color.TRANSPARENT)
	var result: Array[Dictionary] = []
	for shifted: bool in [false, true]:
		for low_last: bool in [false, true]:
			var high_rect: Rect2i = Rect2i(2, 2, 4, 3) if shifted else Rect2i(2, 1, 4, 3)
			var layers: Array[Dictionary] = [
				{"image": low, "rect": Rect2i(2, 1, 4, 3), "priority": 2, "order": 2 if low_last else 1},
				{"image": high, "rect": high_rect, "priority": 3, "order": 1 if low_last else 2}]
			layers.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a.order < b.order)
			var test: Dictionary = {"id": "synthetic_%s_%s" % ["shifted" if shifted else "same_rect", "low_last" if low_last else "high_last"],
				"size": size, "background": background, "foreground": foreground, "layers": layers,
				"expected": _cpu_expected(background, foreground, layers), "scales": [1, 2, 7],
				"scope": "independent synthetic CPU composition, binary alpha, map-local shader coordinates"}
			for mode: String in ["canvas_transform", "scaled_rectangles"]:
				var variant: Dictionary = test.duplicate()
				variant.id += "_" + mode
				variant.geometry_scale_mode = mode
				result.append(variant)
	return result

func _integer(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) == floor(float(value))

func _image(path: Variant) -> Image:
	if not path is String or not String(path).is_absolute_path() or not FileAccess.file_exists(path):
		failures.append("Source fixture image path must exist and be absolute: " + str(path))
		return null
	var image: Image = Image.load_from_file(path)
	if image == null or image.is_empty():
		failures.append("Invalid fixture image: " + path)
		return null
	image.convert(Image.FORMAT_RGBA8)
	source_files[path] = FileAccess.get_sha256(path)
	return image

func _binary_alpha(image: Image) -> bool:
	var data: PackedByteArray = image.get_data()
	for offset: int in range(3, data.size(), 4):
		if data[offset] != 0 and data[offset] != 255: return false
	return true

func _source_cases(path: String) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var parser: JSON = JSON.new()
	if not path.is_absolute_path() or parser.parse(FileAccess.get_file_as_string(path)) != OK or not parser.data is Dictionary:
		failures.append("Invalid source fixture JSON")
		return result
	var fixture: Dictionary = parser.data
	source_files[path] = FileAccess.get_sha256(path)
	if fixture.get("schema") != "ao_character_compositor_fixtures_v1" or not fixture.get("cases") is Array or fixture.cases.is_empty():
		failures.append("Source fixtures require the declared schema and nonempty cases")
		return result
	for item: Variant in fixture.cases:
		if not item is Dictionary:
			failures.append("Source case is not an object")
			continue
		var entry: Dictionary = item
		var initial_errors: int = failures.size()
		if not entry.get("id") is String or not entry.get("canvas_size") is Array or entry.canvas_size.size() != 2:
			failures.append("Invalid source case ID or canvas size")
			continue
		if not _integer(entry.canvas_size[0]) or not _integer(entry.canvas_size[1]):
			failures.append("Nonintegral canvas size")
			continue
		var size: Vector2i = Vector2i(entry.canvas_size[0], entry.canvas_size[1])
		if size.x < 1 or size.y < 1 or size.x > 1024 or size.y > 1024:
			failures.append("Source canvas size outside supported bounds")
			continue
		var background: Image = _image(entry.background_png) if entry.has("background_png") else _solid(size.x, size.y, Color.BLACK)
		var foreground: Image = _image(entry.get("foreground_png"))
		var expected: Image = _image(entry.get("expected_png"))
		var mask: Image = _image(entry.get("compare_mask_png"))
		if background == null or foreground == null or expected == null or mask == null: continue
		if background.get_size() != size or foreground.get_size() != size or expected.get_size() != size or mask.get_size() != size:
			failures.append("Fixture image dimensions disagree with canvas")
			continue
		if not _binary_alpha(foreground) or not _binary_alpha(mask):
			failures.append("Source foreground and comparison mask must use binary alpha")
			continue
		if not entry.get("layers") is Array or entry.layers.is_empty() or not entry.get("scales") is Array or entry.scales.is_empty():
			failures.append("Source case needs layers and scale factors")
			continue
		var layers: Array[Dictionary] = []
		var orders: Array[int] = []
		for value: Variant in entry.layers:
			if not value is Dictionary:
				failures.append("Invalid source sprite record")
				continue
			var layer: Dictionary = value
			if not layer.get("rect") is Array or layer.rect.size() != 4 or not _integer(layer.get("priority")) or not _integer(layer.get("order")):
				failures.append("Invalid source layer geometry or priority fields")
				continue
			var valid_rect: bool = true
			for coordinate: Variant in layer.rect:
				if not _integer(coordinate): valid_rect = false
			if not valid_rect or layer.rect[2] <= 0 or layer.rect[3] <= 0 or not int(layer.priority) in [2, 3] or int(layer.order) < 1 or int(layer.order) > 4095 or int(layer.order) in orders:
				failures.append("Unverified source sprite bounds, priority, or duplicate order")
				continue
			var image: Image = _image(layer.get("texture_png"))
			if image == null: continue
			if not _binary_alpha(image):
				failures.append("Source sprite must have binary alpha")
				continue
			orders.append(int(layer.order))
			layers.append({"image": image, "rect": Rect2i(layer.rect[0], layer.rect[1], layer.rect[2], layer.rect[3]),
				"priority": int(layer.priority), "order": int(layer.order)})
		for scale_value: Variant in entry.scales:
			if not _integer(scale_value) or scale_value < 1 or scale_value > 12:
				failures.append("Source scale factor must be an integer between 1 and 12")
		if initial_errors != failures.size(): continue
		layers.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a.order < b.order)
		result.append({"id": entry.id, "size": size, "background": background, "foreground": foreground,
			"expected": expected, "mask": mask, "layers": layers, "scales": entry.scales,
			"geometry_scale_mode": "scaled_rectangles", "source": entry,
			"scope": "source fixture expected PNG only inside its declared comparison mask; no full-scene claim"})
	return result

func _cpu_expected(background: Image, foreground: Image, layers: Array[Dictionary]) -> Image:
	# Pixel loop intentionally independent of CanvasItem geometry and shader UVs.
	var expected: Image = background.duplicate()
	for layer: Dictionary in layers:
		var source: Image = layer.image
		var rect: Rect2i = layer.rect
		for y: int in range(rect.position.y, rect.end.y):
			for x: int in range(rect.position.x, rect.end.x):
				if x < 0 or y < 0 or x >= expected.get_width() or y >= expected.get_height(): continue
				var tx: int = int(floor(float(x - rect.position.x) * source.get_width() / rect.size.x))
				var ty: int = int(floor(float(y - rect.position.y) * source.get_height() / rect.size.y))
				var color: Color = source.get_pixel(tx, ty)
				if color.a == 0.0: continue
				if layer.priority == 2 and foreground.get_pixel(x, y).a > 0.5:
					var front: Color = foreground.get_pixel(x, y)
					color = Color(front.r, front.g, front.b, color.a)
				expected.set_pixel(x, y, color)
	return expected

func _render_case(test: Dictionary, factor: int) -> void:
	var viewport: SubViewport = SubViewport.new()
	viewport.size = test.size * factor
	viewport.disable_3d = true
	viewport.transparent_bg = false
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_NEAREST
	root.add_child(viewport)
	var stage: Node2D = Node2D.new()
	var rectangle_scale: int = factor if test.get("geometry_scale_mode") == "scaled_rectangles" else 1
	stage.scale = Vector2.ONE if rectangle_scale != 1 else Vector2(factor, factor)
	stage.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	viewport.add_child(stage)
	var background = SpriteLayer.new()
	stage.add_child(background)
	background.show_sprite(ImageTexture.create_from_image(test.background), Rect2(Vector2.ZERO, Vector2(test.size * rectangle_scale)), null, 0)
	var material: ShaderMaterial = ShaderMaterial.new()
	material.shader = PriorityShader
	material.set_shader_parameter("source_foreground", ImageTexture.create_from_image(test.foreground))
	material.set_shader_parameter("canvas_size", Vector2(test.size * rectangle_scale))
	for layer: Dictionary in test.layers:
		var sprite = SpriteLayer.new()
		stage.add_child(sprite)
		var rectangle: Rect2 = Rect2(Vector2(layer.rect.position * rectangle_scale), Vector2(layer.rect.size * rectangle_scale))
		sprite.show_sprite(ImageTexture.create_from_image(layer.image), rectangle, material if layer.priority == 2 else null, layer.order)
	await process_frame
	await RenderingServer.frame_post_draw
	var actual: Image = viewport.get_texture().get_image()
	actual.convert(Image.FORMAT_RGBA8)
	var expected: Image = test.expected
	var mask: Image = test.get("mask")
	var mismatches: int = 0
	var compared: int = 0
	var first: Array[Dictionary] = []
	for y: int in range(actual.get_height()):
		for x: int in range(actual.get_width()):
			var sx: int = int(x / factor)
			var sy: int = int(y / factor)
			if mask != null and mask.get_pixel(sx, sy).a == 0.0: continue
			compared += 1
			var wanted: int = expected.get_pixel(sx, sy).to_rgba32()
			var got: int = actual.get_pixel(x, y).to_rgba32()
			if wanted != got:
				mismatches += 1
				if first.size() < 12:
					first.append({"pixel": [x, y], "source_pixel": [sx, sy], "expected_rgba32": wanted, "actual_rgba32": got})
	var passed: bool = mismatches == 0 and compared > 0 and actual.get_size() == test.size * factor
	if not passed: failures.append("%s at %dx: %d pixel mismatches" % [test.id, factor, mismatches])
	total_pixels += compared
	case_reports.append({"id": test.id, "scale": factor, "size": [actual.get_width(), actual.get_height()],
		"passed": passed, "compared_pixels": compared, "mismatches": mismatches, "first_mismatches": first,
		"readback_rgba_sha256": _digest(actual.get_data()), "expected_base_rgba_sha256": _digest(expected.get_data()),
		"scope": test.scope, "source": test.get("source", {}), "geometry_scale_mode": test.get("geometry_scale_mode")})
	viewport.queue_free()
	await process_frame

func _digest(bytes: PackedByteArray) -> String:
	var hash: HashingContext = HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return hash.finish().hex_encode()

func _run() -> void:
	root.min_size = Vector2i(1, 1)
	root.size = Vector2i(400, 280)
	root.title = "Character compositor GPU pixel verification"
	var adapter: String = RenderingServer.get_video_adapter_name()
	if adapter.is_empty() or "llvmpipe" in adapter.to_lower() or "swiftshader" in adapter.to_lower():
		failures.append("Hardware GPU identity unavailable or software renderer detected")
	for test: Dictionary in _synthetic():
		for factor: int in test.scales:
			await _render_case(test, factor)
	if arguments.has("fixtures"):
		var previous_errors: int = failures.size()
		var source_cases: Array[Dictionary] = _source_cases(arguments.fixtures)
		for test: Dictionary in source_cases:
			for factor: int in test.scales:
				await _render_case(test, factor)
		if source_cases.is_empty(): failures.append("No valid source cases were executed")
		source_fixture_status = "passed" if previous_errors == failures.size() else "failed"
	var report: Dictionary = {"schema": "ao_character_gpu_compositor_validation_v1", "passed": failures.is_empty(),
		"display_server": DisplayServer.get_name(), "adapter": adapter,
		"adapter_vendor": RenderingServer.get_video_adapter_vendor(),
		"rendering_method": RenderingServer.get_current_rendering_method(),
		"godot_version": Engine.get_version_info(), "cases": case_reports, "compared_pixels": total_pixels,
		"failures": failures, "source_fixture_status": source_fixture_status, "source_file_sha256": source_files, "headless": false,
		"inputs": {"shader_sha256": FileAccess.get_sha256("res://character_priority.gdshader"),
			"layer_sha256": FileAccess.get_sha256("res://character_layer.gd"), "harness_sha256": FileAccess.get_sha256("res://tests/test_character_compositor.gd")}}
	if arguments.has("report"):
		var output: FileAccess = FileAccess.open(arguments.report, FileAccess.WRITE)
		if output == null:
			push_error("Cannot write GPU compositor report")
			quit(1)
			return
		output.store_string(JSON.stringify(report, "  ") + "\n")
	print(JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
