extends RefCounted
## Read-only source sample selection. LAIA has her own 48-update cycle.
const Core = preload("res://transition_core.gd")
const SEQUENCES: Dictionary = {0:[3],3:[6],4:[3,4,3,5],6:[3,4,3,5],7:[6,7,6,8]}
const DIRECTIONS: Dictionary = {0:"right",3:"up",4:"right",6:"left",7:"up"}

static func select(raw: PackedByteArray, fraction: float = 0.0) -> Dictionary:
	if raw.size()<0x38 or not is_finite(fraction) or fraction<0 or fraction>=1: return {"ok":false,"error":"Invalid LAIA record or render phase"}
	var selector: int = Core.word(raw,0x36)
	var cursor: int = Core.word(raw,0x2c)
	var timer: int = Core.word(raw,0x30)
	var duration: int = Core.word(raw,0x32)
	var image: int = Core.word(raw,0x34)
	var mirror: int = Core.word(raw,0x14)&1
	if not SEQUENCES.has(selector) or mirror != (1 if selector in [0,4] else 0): return {"ok":false,"error":"Unknown LAIA selector or mirror"}
	var sequence: Array = SEQUENCES[selector]
	var cell: int = 12
	if selector in [0,3]:
		if cursor!=0 or duration!=1 or image!=int(sequence[0]): return {"ok":false,"error":"Invalid LAIA idle cache"}
	else:
		if cursor not in [0,3,6,9] or duration!=12 or timer>11: return {"ok":false,"error":"Invalid LAIA walking cursor/timer"}
		var primary: int = cursor/3
		if image!=int(sequence[primary]):
			# The source terminal decode resets cursor before returning while
			# retaining the last image. This is a held final pose, not an idle.
			if selector==7 and cursor==0 and timer==0 and image==8 and not (Core.word(raw,6)&0x100): cell=11
			else: return {"ok":false,"error":"LAIA image disagrees with source animation"}
		else: cell=primary*3+mini(2,int(floor((timer+fraction)/4.0)))
	return {"ok":true,"direction":DIRECTIONS[selector],"cell":cell,"key":str(DIRECTIONS[selector])+"/"+("idle" if cell==12 else "walk-%02d"%cell),"source_selector":selector,"source_cursor":cursor,"source_timer":timer}
