extends Control
## An explicit asset workbench until gate B has real map/animation/battle evidence.

var package: Dictionary = {}
var records: Array = []
var selected_record: int = 0
var selected_page: int = 0
var text_view: RichTextLabel
var status_label: Label
var record_picker: OptionButton
var page_label: Label
var history: Array[String] = []
var qa_output: String = ""
var qa_frames: int = 0
var frame_times: Array[float] = []
var last_frame_usec: int = 0
var qa_target: Vector2i = Vector2i.ZERO

func _ready() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--qa-output="):
			qa_output = argument.trim_prefix("--qa-output=")
		if argument.begins_with("--qa-size="):
			var sizes: PackedStringArray = argument.trim_prefix("--qa-size=").split("x")
			if sizes.size() == 2:
				qa_target = Vector2i(int(sizes[0]), int(sizes[1]))
	if qa_target.x > 0 and qa_target.y > 0:
		get_window().borderless = true
		get_window().position = Vector2i.ZERO
		get_window().size = qa_target
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["Microsoft JhengHei", "Microsoft YaHei", "Noto Sans CJK TC"])
	var ui_theme := Theme.new()
	ui_theme.default_font = font
	ui_theme.default_font_size = 26
	theme = ui_theme
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://generated/package.json"))
	if data is Dictionary and data.get("schema", "") == "ao_pc_asset_package_v1":
		package = data
		records = package.get("dialogue_records", [])
	build_ui()
	show_page()
	set_process(not qa_output.is_empty())

func label_for(value: String, size: int = 26) -> Label:
	var label := Label.new()
	label.text = value
	label.add_theme_font_size_override("font_size", size)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return label

func build_ui() -> void:
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for edge: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + edge, 44)
	add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 20)
	margin.add_child(column)
	column.add_child(label_for("ALBERT ODYSSEY  /  PC REMAKE", 20))
	column.add_child(label_for("哈比村・資源驗證台", 48))
	var banner := label_for("開發工具｜尚非可玩重製版。地圖、碰撞、事件觸發與戰鬥仍待還原。", 25)
	banner.modulate = Color("edc57c")
	column.add_child(banner)
	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 40)
	column.add_child(body)
	var left := VBoxContainer.new()
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left.size_flags_stretch_ratio = 1.15
	left.add_theme_constant_override("separation", 16)
	body.add_child(left)
	left.add_child(label_for("已核對的繁中對話", 32))
	record_picker = OptionButton.new()
	for record: Dictionary in records:
		record_picker.add_item(str(record["speaker"]) + " · " + str(record["id"]))
	record_picker.item_selected.connect(func(index: int) -> void:
		selected_record = index
		selected_page = 0
		show_page())
	left.add_child(record_picker)
	text_view = RichTextLabel.new()
	text_view.bbcode_enabled = false
	text_view.size_flags_vertical = Control.SIZE_EXPAND_FILL
	text_view.add_theme_font_size_override("normal_font_size", 32)
	left.add_child(text_view)
	page_label = label_for("")
	left.add_child(page_label)
	var buttons := HBoxContainer.new()
	buttons.add_theme_constant_override("separation", 20)
	left.add_child(buttons)
	for item: Array in [["上一頁", -1], ["下一頁", 1]]:
		var button := Button.new()
		button.text = item[0]
		button.custom_minimum_size = Vector2(160, 52)
		var direction: int = item[1]
		button.pressed.connect(func() -> void: advance_page(direction))
		buttons.add_child(button)
	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(right)
	right.add_child(label_for("原始角色紋理・索引檢視", 32))
	right.add_child(label_for("灰階僅顯示索引；原色、角色綁定與動畫時序尚未確認。", 22))
	var image := TextureRect.new()
	if ResourceLoader.exists("res://generated/v1n-index-contact.png"):
		image.texture = load("res://generated/v1n-index-contact.png")
	image.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	image.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	image.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	image.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(image)
	status_label = label_for("", 20)
	column.add_child(status_label)
	status_label.text = "%d 段具名對話  ·  %d 筆紋理記錄  ·  原作規則優先  ·  Windows / Compatibility" % [records.size(), package.get("textures", []).size()]

func show_page() -> void:
	if records.is_empty():
		text_view.text = "資料包未生成或格式不符。請先執行 tools/pipeline.py build。"
		return
	var record: Dictionary = records[selected_record]
	var pages: Array = record["pages"]
	var page: Dictionary = pages[selected_page]
	text_view.text = str(page["speaker"]) + "\n\n" + str(page["zh_tw"]) + "\n\n" + str(page["en"])
	if not page["playback_allowed"]:
		text_view.text += "\n\n含未解析控制碼：僅供文字檢查，禁止事件播放。"
	page_label.text = "第 %d / %d 頁  ·  MAP001.TWN @ 0x%06X\n來源文字已核對；本畫面不代表事件可達性。" % [selected_page + 1, pages.size(), int(page["offset"])]
	if not history.has(str(page["id"])):
		history.append(str(page["id"]))

func advance_page(direction: int) -> void:
	if records.is_empty():
		return
	selected_page = clampi(selected_page + direction, 0, records[selected_record]["pages"].size() - 1)
	show_page()

func _process(_delta: float) -> void:
	var now: int = Time.get_ticks_usec()
	qa_frames += 1
	if qa_frames > 60 and last_frame_usec > 0:
		frame_times.append(float(now - last_frame_usec) / 1000.0)
	last_frame_usec = now
	if qa_frames == 240:
		capture_qa()

func capture_qa() -> void:
	set_process(false)
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(qa_output)
	var screenshot: Image = get_viewport().get_texture().get_image()
	var png_error: Error = screenshot.save_png(qa_output.path_join("screen.png"))
	frame_times.sort()
	var average: float = 0.0
	for value: float in frame_times:
		average += value
	average /= max(1, frame_times.size())
	var report: Dictionary = {"scope": "asset_workbench_only_not_gameplay", "image_error": png_error,
		"requested_width": qa_target.x, "requested_height": qa_target.y,
		"width": screenshot.get_width(), "height": screenshot.get_height(),
		"sample_frames": frame_times.size(), "average_frame_ms": average,
		"p95_frame_ms": frame_times[int(frame_times.size() * 0.95)],
		"engine_static_memory_bytes": OS.get_static_memory_usage(),
		"video_memory_bytes": Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED),
		"playable": false}
	var file: FileAccess = FileAccess.open(qa_output.path_join("render.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t"))
	file.close()
	var size_ok: bool = qa_target == Vector2i.ZERO or screenshot.get_size() == qa_target
	get_tree().quit(0 if png_error == OK and size_ok else 1)
