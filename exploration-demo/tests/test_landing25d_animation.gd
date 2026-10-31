extends SceneTree
const Select = preload("res://landing25d_animation.gd")
const Core = preload("res://transition_core.gd")
var errors: Array[String] = []
var checks: int = 0
func check(v: bool,s: String) -> void:
	checks+=1
	if not v: errors.append(s)
func _initialize() -> void:
	for selector: int in [4,6,7]:
		var raw:=PackedByteArray();raw.resize(128)
		Core.put(raw,0x36,selector);Core.put(raw,0x32,12);Core.put(raw,0x14,1 if selector==4 else 0)
		for phase: int in 48:
			Core.put(raw,0x2c,(phase/12)*3);Core.put(raw,0x30,phase%12);Core.put(raw,0x34,Select.SEQUENCES[selector][phase/12])
			var before:=raw.duplicate()
			for fraction: float in [0.0,0.5,0.999]:
				var frame: Dictionary=Select.select(raw,fraction)
				check(frame.ok and frame.cell==phase/4,"48 update cycle and thirds")
				check(before==raw,"Selector cannot mutate source state")
		Core.put(raw,0x34,99);check(not Select.select(raw).ok,"Unknown pose rejects")
		Core.put(raw,0x36,99);check(not Select.select(raw).ok,"Unknown selector rejects")
	check(not Select.select(PackedByteArray()).ok,"Truncated source rejects")
	var result: Dictionary={"passed":errors.is_empty(),"checks":checks,"failures":errors,"performance_tested":false}
	var f:=FileAccess.open("res://../reports/enhanced25d-landing/animation-test.json",FileAccess.WRITE);f.store_string(JSON.stringify(result,"\t"));f.close()
	print(JSON.stringify(result));quit(0 if errors.is_empty() else 1)
