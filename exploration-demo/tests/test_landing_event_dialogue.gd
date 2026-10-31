extends SceneTree
const Dialogue = preload("res://landing_event_dialogue.gd")
var checks: int = 0
func _initialize() -> void: call_deferred("run")
func demand(value: bool, message: String) -> bool:
	checks += 1
	if not value: push_error(message); quit(1)
	return value
func run() -> void:
	var dialogue := Dialogue.new()
	dialogue.key(true)
	if not demand(dialogue.open(5).ok,"Five-page source text rejected"): return
	dialogue.key(true)
	if not demand(not dialogue.step() and dialogue.page == 0,"Held trigger key passed into dialogue"): return
	dialogue.key(false); dialogue.key(true)
	if not demand(dialogue.step() and dialogue.page == 1,"Fresh key did not confirm one page"): return
	for i: int in 8:
		dialogue.key(true)
		if not demand(not dialogue.step() and dialogue.page == 1,"Held key advanced another page"): return
	var token: int = dialogue.generation
	if not demand(dialogue.submit(token,1),"Valid page token rejected"): return
	if not demand(not dialogue.submit(token,1),"Duplicate pending response accepted"): return
	if not demand(dialogue.step() and dialogue.page == 2,"Duplicate response consumed extra page"): return
	if not demand(not dialogue.submit(token,1),"Late previous-page response accepted"): return
	for target: int in [2,3,4]:
		if not demand(dialogue.submit(token,target) and dialogue.step(),"Remaining source page failed"): return
	if not demand(not dialogue.active and dialogue.accepted == 5,"Source text did not close after exactly five confirmations"): return
	if not demand(dialogue.open(3).ok and not dialogue.submit(token,0),"First text response leaked into second text"): return
	token = dialogue.generation
	dialogue.submit(token,0); dialogue.reset()
	if not demand(not dialogue.submit(token,0) and not dialogue.step() and not dialogue.active,"Reset accepted stale text completion"): return
	if not demand(not dialogue.open(99).ok and not dialogue.active,"Unapproved source page count accepted"): return
	print(JSON.stringify({"passed":true,"checks":checks,"performance_tested":false,"scope":"Whole-page input/generation contract only; no source pixels or UI acceptance."}))
	quit(0)
