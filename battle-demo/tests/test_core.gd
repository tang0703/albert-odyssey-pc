extends SceneTree
const Core = preload("res://core.gd")
var checks: int = 0

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		push_error(message)
		quit(1)
		assert(value,message)

func focus(b: DemoBattle, id: String) -> void:
	b.current = id
	b.queue.clear()
	for unit: Dictionary in b.units:
		if unit["id"] != id and unit["hp"] > 0: b.queue.append(unit["id"])

func _initialize() -> void:
	var b := Core.new()
	check(b.current == "scout" and b.queue == ["mage","enemy_mage","healer","guardian","armor"],"speed order")
	var data: Dictionary = b.definitions.duplicate(true)
	for unit: Dictionary in data["units"]: unit["speed"] = 10
	var tied := Core.new(data)
	check(tied.current == "guardian" and tied.queue == ["mage","healer","armor","scout","enemy_mage"],"stable ties")
	focus(b,"guardian")
	check(b.amount("attack",b.unit_by_id("guardian"),b.unit_by_id("armor")) == 14,"attack formula")
	check(b.amount("heavy",b.unit_by_id("guardian"),b.unit_by_id("armor")) == 36,"heavy floor")
	check(b.amount("wave",b.unit_by_id("mage"),b.unit_by_id("scout")) == 27,"magic formula")
	var command: Dictionary = b.request("heavy","armor")
	check(b.submit(command)["ok"],"valid heavy")
	check(b.unit_by_id("guardian")["mp"] == 15,"cost once")
	check(not b.submit(command)["ok"] and b.unit_by_id("guardian")["mp"] == 15,"duplicate token rejected")
	focus(b,"guardian")
	var before: String = JSON.stringify(b.units)
	check(not b.submit(b.request("heavy","guardian"))["ok"] and JSON.stringify(b.units) == before,"invalid target atomic")
	b.unit_by_id("guardian")["mp"] = 0
	check(not b.available("heavy"),"insufficient MP")
	check(not b.available("wave"),"foreign skill rejected")
	b.potions = 0
	check(not b.available("potion"),"empty items")
	b.reset()
	focus(b,"healer")
	check(not b.available("heal") and not b.available("potion"),"full health invalid")
	b.unit_by_id("mage")["hp"] = 90
	check(b.submit(b.request("heal","mage"))["ok"] and b.unit_by_id("mage")["hp"] == 100,"heal cap")
	check(b.unit_by_id("healer")["mp"] == 24,"heal MP")
	focus(b,"healer")
	b.unit_by_id("mage")["hp"] = 0
	check("mage" not in b.targets("heal"),"no revival")
	b.reset(); focus(b,"guardian")
	b.unit_by_id("mage")["hp"] = 80
	check(b.submit(b.request("potion","mage"))["ok"] and b.potions == 2 and b.unit_by_id("mage")["hp"] == 100,"potion cap and count")
	b.reset(); focus(b,"guardian")
	b.submit(b.request("guard","guardian"))
	check(b.unit_by_id("guardian")["guarding"],"guard persists after action")
	check(b.amount("attack",b.unit_by_id("armor"),b.unit_by_id("guardian")) == 6,"guard half")
	b.queue = ["guardian"]
	b.advance()
	check(not b.unit_by_id("guardian")["guarding"],"guard expires next own turn")
	b.unit_by_id("guardian")["guarding"] = true
	b.unit_by_id("guardian")["defense"] = 100
	check(b.amount("attack",b.unit_by_id("scout"),b.unit_by_id("guardian")) == 1,"minimum guarded damage")
	b.reset(); focus(b,"mage")
	b.unit_by_id("scout")["hp"] = 1
	b.submit(b.request("wave","armor"))
	check(b.unit_by_id("scout")["hp"] == 0 and "scout" not in b.queue and b.current != "scout","skip dead queued unit")
	b.reset(); focus(b,"mage")
	for id: String in b.living("enemy"): b.unit_by_id(id)["hp"] = 1
	var result: Dictionary = b.submit(b.request("wave","armor"))
	check(b.outcome == "victory" and b.totals["enemy_down"] == 3,"AOE victory after all targets")
	check(result["events"][-1]["type"] == "end" and b.unit_by_id("mage")["mp"] == 28,"end event and single AOE cost")
	b.reset(); focus(b,"scout")
	for id: String in ["guardian","healer"]: b.unit_by_id(id)["hp"] = 0
	b.unit_by_id("mage")["hp"] = 1
	b.submit(b.request("attack","mage"))
	check(b.outcome == "defeat","last party death")
	b.reset(); focus(b,"enemy_mage")
	check(b.enemy_command()["target"] == "guardian","AI ties use party order")
	b.unit_by_id("mage")["hp"] = 49
	check(b.enemy_command()["target"] == "mage" and b.enemy_command()["action"] == "fire","AI ratio and magic")
	b.unit_by_id("enemy_mage")["mp"] = 5
	check(b.enemy_command()["action"] == "attack","AI depleted MP fallback")
	var old: Dictionary = b.request("attack","mage")
	b.reset()
	check(not b.submit(old)["ok"] and b.potions == 3 and b.unit_by_id("mage")["hp"] == 100 and b.journal.is_empty(),"reset rejects prior requests and restores battle")
	var outcomes: Array[String] = []
	for mode: int in range(2):
		b.reset()
		for step: int in range(300):
			if not b.outcome.is_empty(): break
			var request: Dictionary = b.enemy_command() if b.unit_by_id(b.current)["side"] == "enemy" else (b.request("guard",b.current) if mode == 1 else strategy(b))
			check(b.submit(request)["ok"],"complete battle valid action")
		outcomes.append(b.outcome)
	check(outcomes == ["victory","defeat"],"full victory and defeat flows")
	# Same command policy on fresh cores has identical journals, irrespective of presentation delays.
	var journals: Array[String] = []
	for repeat: int in range(2):
		var replay := Core.new()
		for step: int in range(300):
			if not replay.outcome.is_empty(): break
			replay.submit(replay.enemy_command() if replay.unit_by_id(replay.current)["side"] == "enemy" else strategy(replay))
		journals.append(JSON.stringify(replay.journal))
	check(journals[0] == journals[1],"deterministic replay")
	print("BATTLE CORE: %d checks passed" % checks)
	quit()

func strategy(b: DemoBattle) -> Dictionary:
	var actor: Dictionary = b.unit_by_id(b.current)
	var injured: String = ""
	for id: String in b.living("party"):
		var unit: Dictionary = b.unit_by_id(id)
		if unit["hp"] <= unit["max_hp"] * 0.6 and (injured.is_empty() or unit["hp"] < b.unit_by_id(injured)["hp"]): injured = id
	if not injured.is_empty():
		if actor["skill"] == "heal" and b.available("heal"): return b.request("heal",injured)
		if b.unit_by_id(injured)["hp"] < 35 and b.available("potion"): return b.request("potion",injured)
	var action: String = actor["skill"] if actor["skill"] != "heal" and b.available(actor["skill"]) else "attack"
	var choices: Array[String] = b.targets(action)
	var target: String = choices[0]
	for id: String in choices:
		if b.unit_by_id(id)["hp"] < b.unit_by_id(target)["hp"]: target = id
	return b.request(action,target)
