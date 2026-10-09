extends RefCounted
## The 52-frame HD package is separately pinned; no draft/source-image fallback.
const Common = preload("res://package_loader.gd")
const Source = preload("res://character_loader.gd")
const SourceAnimation = preload("res://character_animation_core.gd")
const Movement = preload("res://movement_core.gd")
const SCHEMA: String = "ao_pc_character_hd_bundle_v1"
const PIN_SCHEMA: String = "ao_pc_character_hd_bundle_pin_v1"
const DIRECTIONS: Array[String] = ["down","left","right","up"]
const DRAFTS: Dictionary = {"down":"69f0b62b922970de1ed6858d5bb02a97155ea2bc58d580da8b9b783151ab8c32",
	"left":"0a8b2a8ba87d308e0d7a6eaa7e01a8f7dce7e6294574badc0c6eca4642ace2d5",
	"right":"e50459c5657b069f85ca074c7da20efd3c274284f9c98243b49fb13031a46b3c",
	"up":"0d9808ae52ad55b1c5dfa1a2c78f0433d2ecb3141a43898f7ddc34890fdd3373"}
const TIMING: Dictionary = {"cycle_updates":40,"primary_updates":10,"subframes_per_primary":3,
	"primary_walk_indices":[0,3,6,9],"phase_formula":"floor((source_timer + render_phase) * 3 / 10)",
	"render_phase_interval":"[0,1)","idle_uses_source_state":true,"writes_movement":false}

static func default_directory() -> String:
	return OS.get_executable_path().get_base_dir().path_join("character-hd") if not OS.has_feature("editor") else ProjectSettings.globalize_path("res://generated/character-hd")

static func expected_frames() -> Array[Dictionary]:
	var rows: Array[Dictionary] = []
	for direction: String in DIRECTIONS:
		for cell: int in 13:
			var walk: int = cell if cell<12 else -1
			var suffix: String = "walk-%02d"%walk if walk>=0 else "idle"
			var sub: int = walk%3 if walk>=0 else -1
			var primary: int = walk/3 if walk>=0 else -1
			rows.append({"id":"map001_player_hd/"+direction+"/"+suffix,"direction":direction,
				"action":"walk" if walk>=0 else "idle","kind":"idle" if walk<0 else ("primary" if sub==0 else "transition"),
				"walk_index":walk,"primary_source_index":primary if walk>=0 else null,
				"next_primary_source_index":(primary+1)%4 if sub>0 else null,
				"transition_fraction":{"numerator":sub,"denominator":3} if sub>0 else null,
				"file":direction+"-"+suffix+".png","atlas":direction+"-atlas.png","cell":cell,
				"rect":[(cell%4)*512,(cell/4)*512,512,512],"dimensions":[512,512]})
	return rows

static func _point(value: Variant) -> bool:
	return value is Array and value.size()==2 and _number(value[0],0.0,512.0) and _number(value[1],0.0,512.0)

static func _number(value: Variant, minimum: float, maximum: float) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and value>=minimum and value<=maximum

static func _equal(value: Variant, expected: Variant) -> bool:
	if expected==null: return value==null
	if expected is int: return Movement.integer(value) and int(value)==expected
	if expected is bool: return value is bool and value==expected
	if expected is String: return value is String and value==expected
	if expected is Array:
		if not value is Array or value.size()!=expected.size(): return false
		for index: int in expected.size():
			if not _equal(value[index],expected[index]): return false
		return true
	if expected is Dictionary:
		if not value is Dictionary or not Movement._keys_match(value,expected.keys()): return false
		for key: String in expected:
			if not _equal(value[key],expected[key]): return false
		return true
	return false

static func validate_appearances(value: Variant) -> Dictionary:
	if not value is Dictionary or not Movement._keys_match(value,["schema","character_id","timing","frames"]) or not _equal(value.schema,"ao_pc_character_hd_appearances_v1") or not _equal(value.character_id,"map001_player_hd") or not _equal(value.timing,TIMING):
		return Source.rejected("HD appearance schema or source timing is unsupported.")
	if not value.frames is Array or value.frames.size()!=52: return Source.rejected("All 52 actual HD frames are required.")
	var expected: Array[Dictionary] = expected_frames()
	for index: int in 52:
		var row: Variant = value.frames[index]
		var base: Dictionary = expected[index]
		if not row is Dictionary or not Movement._keys_match(row,base.keys()+["ground_anchor","actor_anchor","display_scale"]): return Source.rejected("HD frame metadata is incomplete.")
		for key: String in base:
			if not _equal(row[key],base[key]): return Source.rejected("HD frame/atlas mapping differs: "+key)
		if not _point(row.ground_anchor) or row.ground_anchor!=[256,448] or not _point(row.actor_anchor) or not _number(row.display_scale,0.01,0.25):
			return Source.rejected("HD ground/actor anchor or source-pixel scale is invalid.")
	return {"ok":true,"error":"","frames":value.frames}

static func load_bundle(directory: String, scene_sha: String, source_character_sha: String) -> Dictionary:
	var pin: Variant = Common.read_json("res://character-hd-pin.json")
	if not pin is Dictionary or not Movement._keys_match(pin,["schema","manifest_sha256","scene_manifest_sha256","source_character_manifest_sha256"]) or not _equal(pin.schema,PIN_SCHEMA):
		return Source.rejected("No approved 52-frame HD package pin is installed.")
	if not _equal(pin.scene_manifest_sha256,scene_sha) or not _equal(pin.source_character_manifest_sha256,source_character_sha):
		return Source.rejected("HD/source character/scene versions differ.")
	return load_verified(directory,str(pin.manifest_sha256),scene_sha,source_character_sha)

static func _png(raw: PackedByteArray, dimensions: Vector2i) -> Image:
	var image := Image.new()
	if image.load_png_from_buffer(raw)!=OK or image.get_size()!=dimensions or image.get_format()!=Image.FORMAT_RGBA8: return null
	return image

static func load_verified(directory: String, manifest_sha: String, scene_sha: String, source_sha: String) -> Dictionary:
	for identity: String in [manifest_sha,scene_sha,source_sha]:
		if not Source._hash_valid(identity): return Source.rejected("Three trusted HD/source/scene hashes are required.")
	if FileAccess.get_sha256(directory.path_join("package.json"))!=manifest_sha: return Source.rejected("HD package missing or modified.")
	var data: Variant = Common.read_json(directory.path_join("package.json"))
	if not data is Dictionary or not Movement._keys_match(data,["schema","character_id","source_local_only","state","scene_manifest_sha256","source_character_manifest_sha256","source","files"]): return Source.rejected("Invalid HD package metadata.")
	if not _equal(data.schema,SCHEMA) or not _equal(data.character_id,"map001_player_hd") or not _equal(data.source_local_only,true) or not _equal(data.state,"approved_52_frames") or not _equal(data.scene_manifest_sha256,scene_sha) or not _equal(data.source_character_manifest_sha256,source_sha):
		return Source.rejected("Draft or incompatible HD appearance package.")
	var provenance: Variant = data.source
	if not provenance is Dictionary or not Movement._keys_match(provenance,["art_manifest_sha256","draft_approval_record_sha256","approved_drafts","art_review_status"]) or not _equal(provenance.approved_drafts,DRAFTS) or not _equal(provenance.art_review_status,"approved") or not Source._hash_valid(provenance.art_manifest_sha256) or not Source._hash_valid(provenance.draft_approval_record_sha256):
		return Source.rejected("HD final art is not bound to approved design and review.")
	var files: Array[String] = ["appearances.json"]
	for row: Dictionary in expected_frames(): files.append(row.file)
	for direction: String in DIRECTIONS: files.append(direction+"-atlas.png")
	if not data.files is Dictionary or not Movement._keys_match(data.files,files): return Source.rejected("HD allowlist must contain 52 frames and four atlases.")
	var actual: PackedStringArray = DirAccess.get_files_at(directory)
	var expected: PackedStringArray = PackedStringArray(files+["package.json"])
	actual.sort()
	expected.sort()
	if actual!=expected or not DirAccess.get_directories_at(directory).is_empty(): return Source.rejected("HD package contains missing or unlisted files.")
	var raw: Dictionary = {}
	for name: String in files:
		var identity: Variant = data.files[name]
		if not identity is Dictionary or not Movement._keys_match(identity,["bytes","sha256"]) or not Movement.integer(identity.bytes) or identity.bytes<=0 or not Source._hash_valid(identity.sha256): return Source.rejected("Invalid HD file identity.")
		raw[name]=FileAccess.get_file_as_bytes(directory.path_join(name))
		if raw[name].size()!=identity.bytes or SourceAnimation._hash(raw[name])!=identity.sha256: return Source.rejected("HD file missing, changed or truncated: "+name)
	var appearance: Variant = Common.normalize_integers(JSON.parse_string(raw["appearances.json"].get_string_from_utf8()))
	var validated: Dictionary = validate_appearances(appearance)
	if not validated.ok: return validated
	var atlases: Dictionary = {}
	var atlas_images: Dictionary = {}
	for direction: String in DIRECTIONS:
		var image: Image = _png(raw[direction+"-atlas.png"],Vector2i(2048,2048))
		if image==null: return Source.rejected("HD atlas is not a 2048 square RGBA PNG.")
		for cell: int in range(13,16):
			var empty: PackedByteArray = image.get_region(Rect2i((cell%4)*512,(cell/4)*512,512,512)).get_data()
			for byte: int in empty:
				if byte!=0: return Source.rejected("Unused HD atlas cells must be zero RGBA.")
		atlas_images[direction]=image
		atlases[direction]=ImageTexture.create_from_image(image)
	var frames: Dictionary = {}
	var textures: Dictionary = {}
	var seen: Dictionary = {}
	for row: Dictionary in validated.frames:
		var image: Image = _png(raw[row.file],Vector2i(512,512))
		if image==null: return Source.rejected("HD frame is not a 512 square RGBA PNG.")
		var pixels: PackedByteArray = image.get_data()
		var opaque: bool = false
		var transparent: bool = false
		for alpha_index: int in range(3,pixels.size(),4):
			opaque=opaque or pixels[alpha_index]>=128
			transparent=transparent or pixels[alpha_index]==0
		if not opaque or not transparent: return Source.rejected("HD frame body or transparency is missing.")
		var identity: String = str(row.direction)+":"+SourceAnimation._hash(pixels)
		if seen.has(identity): return Source.rejected("Repeated still images cannot replace distinct HD poses.")
		seen[identity]=true
		var rectangle := Rect2i(int(row.rect[0]),int(row.rect[1]),512,512)
		if atlas_images[row.direction].get_region(rectangle).get_data()!=pixels: return Source.rejected("HD atlas differs from the individual frame pixels.")
		var texture := AtlasTexture.new()
		texture.atlas=atlases[row.direction]
		texture.region=Rect2(rectangle)
		texture.filter_clip=true
		frames[row.id]=row.duplicate(true)
		textures[row.id]=texture
	return {"ok":true,"error":"","data":data,"frames":frames,"textures":textures,"atlases":atlases,"preloaded":true}

static func lookup(bundle: Dictionary, selected: Dictionary) -> Dictionary:
	if not bundle.get("ok",false) or not bundle.get("preloaded",false) or not selected.get("ok",false): return Source.rejected("HD package or selected source pose is invalid.")
	var id: String = str(selected.get("frame_id",""))
	if not bundle.get("frames") is Dictionary or not bundle.get("textures") is Dictionary or not bundle.frames.has(id) or not bundle.textures.has(id): return Source.rejected("Required HD pose is missing.")
	var texture: Variant = bundle.textures[id]
	if not texture is AtlasTexture or not is_instance_valid(texture) or texture.atlas==null or texture.get_size()!=Vector2(512,512): return Source.rejected("Required preloaded HD texture is invalid.")
	var frame: Dictionary = bundle.frames[id].duplicate(true)
	frame.anchor=frame.actor_anchor.duplicate()
	return {"ok":true,"error":"","frame":frame,"texture":texture}
