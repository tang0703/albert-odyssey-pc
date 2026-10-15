extends RefCounted
## Whole-page PC policy. Edges are consumed only by a complete logical update.
var active: bool = false
var page: int = -1
var pending: bool = false
var held: bool = false
var accepted: int = 0
var generation: int = 0

func reset() -> void:
	active = false; page = -1; pending = false; held = false; accepted = 0; generation += 1

func open() -> void:
	active = true; page = 0; pending = false; generation += 1

func key(pressed: bool, echo: bool = false) -> void:
	if pressed and not echo and not held and active: pending = true
	held = pressed

func click() -> void:
	if active: pending = true

func clear_input() -> void:
	pending = false; held = false

func step() -> bool:
	var advanced: bool = active and pending
	pending = false
	if advanced:
		accepted += 1
		page += 1
		if page == 2: active = false; page = -1
	return advanced
