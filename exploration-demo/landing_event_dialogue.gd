extends RefCounted
## Whole-page adapter for the locked old dialogue and new five/three-page text.
## Generation and page tokens reject delayed/duplicate confirmations on reset.
var active: bool = false
var page: int = -1
var pending: bool = false
var held: bool = false
var accepted: int = 0
var generation: int = 0
var page_count: int = 0

func reset() -> void:
	active = false; page = -1; pending = false; held = false; accepted = 0; generation += 1; page_count = 0

func open(count: int = 2) -> Dictionary:
	if count not in [1,2,3,5]: return {"ok":false,"error":"Unapproved dialogue page count"}
	page_count = count; active = true; page = 0; pending = false; generation += 1
	return {"ok":true,"generation":generation,"page":page}

func submit(response_generation: int, response_page: int) -> bool:
	if not active or response_generation != generation or response_page != page or pending: return false
	pending = true
	return true

func key(pressed: bool, echo: bool = false) -> void:
	if pressed and not echo and not held: submit(generation,page)
	held = pressed

func click() -> void: submit(generation,page)

func clear_input() -> void:
	pending = false; held = false

func step() -> bool:
	var advanced: bool = active and pending
	pending = false
	if advanced:
		accepted += 1; page += 1
		if page == page_count: active = false; page = -1
	return advanced
