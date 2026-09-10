extends SceneTree
const Core = preload("res://core.gd")

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var signatures: Array[String] = []
	for fps: int in [30,60,120]:
		Engine.max_fps = fps
		for presentation_speed: float in [1.0,2.0]:
			var battle := Core.new()
			for i: int in range(20):
				var command: Dictionary = battle.enemy_command() if battle.unit_by_id(battle.current)["side"] == "enemy" else battle.request("attack",battle.targets("attack")[0])
				await create_timer(0.01 / presentation_speed).timeout
				var result: Dictionary = battle.submit(command)
				if not result["ok"]: quit(1); return
			signatures.append(JSON.stringify({"units":battle.units,"journal":battle.journal,"potions":battle.potions}))
	for signature: String in signatures:
		if signature != signatures[0]: push_error("Timing changed battle outcome"); quit(1); return
	print("BATTLE TIMING: 6 FPS/speed combinations identical")
	quit()
