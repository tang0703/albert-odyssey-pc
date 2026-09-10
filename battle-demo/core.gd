class_name DemoBattle
extends RefCounted
## Pure deterministic rules. Presentation never mutates these fields.

var definitions: Dictionary
var units: Array[Dictionary] = []
var skills: Dictionary
var queue: Array[String] = []
var current: String = ""
var round_number: int = 0
var turn_token: int = 0
var potions: int = 3
var outcome: String = ""
var totals: Dictionary = {}
var journal: Array[Dictionary] = []

func _init(data: Dictionary = {}) -> void:
	if data.is_empty():
		data = JSON.parse_string(FileAccess.get_file_as_string("res://data/encounter.json"))
	definitions = data.duplicate(true)
	reset()

func reset() -> void:
	units.clear()
	skills = definitions["skills"].duplicate(true)
	for definition: Dictionary in definitions["units"]:
		var unit: Dictionary = definition.duplicate(true)
		unit["max_hp"] = int(unit["hp"])
		unit["max_mp"] = int(unit["mp"])
		for key: String in ["hp", "mp", "attack", "defense", "magic", "speed"]:
			unit[key] = int(unit[key])
		unit["guarding"] = false
		units.append(unit)
	queue.clear()
	current = ""
	round_number = 0
	turn_token += 1 # Old UI requests cannot be reused after restart.
	potions = 3
	outcome = ""
	totals = {"party_damage":0,"enemy_damage":0,"healing":0,"party_down":0,"enemy_down":0}
	journal.clear()
	advance()

func unit_by_id(id: String) -> Dictionary:
	for unit: Dictionary in units:
		if unit["id"] == id:
			return unit
	return {}

func living(side: String) -> Array[String]:
	var result: Array[String] = []
	for unit: Dictionary in units:
		if unit["side"] == side and unit["hp"] > 0:
			result.append(unit["id"])
	return result

func advance() -> void:
	if not outcome.is_empty():
		return
	if queue.is_empty():
		round_number += 1
		var ordered: Array[Dictionary] = []
		for i: int in range(units.size()):
			if units[i]["hp"] > 0:
				ordered.append({"id":units[i]["id"],"speed":units[i]["speed"],"index":i})
		ordered.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
			return a["speed"] > b["speed"] if a["speed"] != b["speed"] else a["index"] < b["index"])
		for item: Dictionary in ordered:
			queue.append(item["id"])
	current = queue.pop_front()
	unit_by_id(current)["guarding"] = false
	turn_token += 1

func targets(action: String) -> Array[String]:
	var actor: Dictionary = unit_by_id(current)
	var result: Array[String] = []
	if actor.is_empty() or not skills.has(action):
		return result
	var kind: String = skills[action]["target"]
	if kind == "self":
		return [current]
	var side: String = actor["side"] if kind == "ally" else ("enemy" if actor["side"] == "party" else "party")
	for id: String in living(side):
		var target: Dictionary = unit_by_id(id)
		if kind != "ally" or target["hp"] < target["max_hp"]:
			result.append(id)
	return result

func available(action: String) -> bool:
	var actor: Dictionary = unit_by_id(current)
	if actor.is_empty() or not skills.has(action) or not outcome.is_empty():
		return false
	if action not in ["attack", "guard", actor["skill"]] and not (action == "potion" and actor["side"] == "party"):
		return false
	return actor["mp"] >= int(skills[action]["cost"]) and (action != "potion" or potions > 0) and not targets(action).is_empty()

func amount(action: String, actor: Dictionary, target: Dictionary) -> int:
	var skill: Dictionary = skills[action]
	var value: int = 0
	match skill["kind"]:
		"physical": value = maxi(1, int(floor(actor["attack"] * float(skill.get("multiplier", 1.0)))) - int(target["defense"]))
		"magic": value = maxi(1, int(actor["magic"]) - int(floor(float(target["defense"]) * 0.5)))
		"heal": return mini(int(actor["magic"]) * 2, int(target["max_hp"]) - int(target["hp"]))
		"potion": return mini(50, int(target["max_hp"]) - int(target["hp"]))
		"guard": return 0
	if target["guarding"]:
		value = maxi(1, int(floor(value * 0.5)))
	return mini(value, int(target["hp"]))

func request(action: String, target: String = "") -> Dictionary:
	return {"actor":current,"action":action,"target":target,"token":turn_token}

func submit(command: Dictionary) -> Dictionary:
	# Validate completely before changing state or consuming any resource.
	if command.get("actor", "") != current or command.get("token", -1) != turn_token:
		return {"ok":false,"reason":"stale_turn"}
	var action: String = command.get("action", "")
	if not available(action):
		return {"ok":false,"reason":"unavailable"}
	var allowed: Array[String] = targets(action)
	var target_id: String = command.get("target", "")
	if target_id not in allowed:
		return {"ok":false,"reason":"invalid_target"}
	var actor: Dictionary = unit_by_id(current)
	var skill: Dictionary = skills[action]
	var affected: Array[String] = []
	if skill["target"] == "all_foes": affected.assign(allowed)
	else: affected.append(target_id)
	var events: Array[Dictionary] = []
	actor["mp"] -= int(skill["cost"])
	if action == "potion":
		potions -= 1
	events.append({"type":"action","actor":current,"action":action,"mp_cost":int(skill["cost"]),"potions":potions})
	for id: String in affected:
		var target: Dictionary = unit_by_id(id)
		var value: int = amount(action, actor, target)
		var kind: String = skill["kind"]
		if kind == "guard":
			target["guarding"] = true
			events.append({"type":"guard","target":id,"amount":0})
		elif kind in ["heal", "potion"]:
			target["hp"] += value
			totals["healing"] += value
			events.append({"type":"heal","target":id,"amount":value})
		else:
			target["hp"] -= value
			totals["party_damage" if actor["side"] == "party" else "enemy_damage"] += value
			events.append({"type":"damage","target":id,"amount":value})
			if target["hp"] == 0:
				queue.erase(id)
				totals["party_down" if target["side"] == "party" else "enemy_down"] += 1
				events.append({"type":"down","target":id})
	if living("enemy").is_empty():
		outcome = "victory"
	elif living("party").is_empty():
		outcome = "defeat"
	if not outcome.is_empty():
		events.append({"type":"end","outcome":outcome})
	journal.append({"round":round_number,"command":command.duplicate(),"events":events.duplicate(true)})
	turn_token += 1
	if outcome.is_empty():
		advance()
	return {"ok":true,"events":events}

func enemy_command() -> Dictionary:
	var actor: Dictionary = unit_by_id(current)
	var action: String = actor["skill"] if available(actor["skill"]) else "attack"
	var candidates: Array[String] = targets(action)
	var chosen: String = candidates[0]
	for id: String in candidates:
		var a: Dictionary = unit_by_id(id)
		var b: Dictionary = unit_by_id(chosen)
		if int(a["hp"]) * int(b["max_hp"]) < int(b["hp"]) * int(a["max_hp"]):
			chosen = id
	return request(action, chosen)
