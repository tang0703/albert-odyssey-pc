extends RefCounted
## View-only bridge for the source image cache. Never passed back to movement.
static func project(raw: Dictionary) -> Dictionary:
	var result: Dictionary = raw.duplicate(true)
	var image: int = int(raw.image_index)
	var mirror: bool = bool(int(raw.render_flags_word)&1)
	var heading: int
	var primary: int = -1
	if image == 0: heading = 2
	elif image == 1: heading = 0 if mirror else 4
	elif image == 2: heading = 6
	elif image >= 5 and image <= 8: heading = 2; primary = image-5
	elif image >= 9 and image <= 12: heading = 0 if mirror else 4; primary = image-9
	elif image >= 13 and image <= 16: heading = 6; primary = image-13
	else: return {}
	if mirror != (heading == 0): return {}
	result.heading = heading
	result.status_word = 0x8180 | (2 if primary >= 0 else 0)
	result.animation_index = heading+(8 if primary >= 0 else 0)
	result.animation_cursor = primary*3 if primary >= 0 else 0
	result.animation_duration = 10 if primary >= 0 else 1
	return result
