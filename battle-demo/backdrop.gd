extends Control

func _draw() -> void:
	var w: float = size.x
	var h: float = size.y
	draw_rect(Rect2(Vector2.ZERO,size),Color("0d1928"))
	draw_circle(Vector2(w*0.51,h*0.30),65,Color("273b48"))
	draw_circle(Vector2(w*0.51,h*0.30),53,Color("b5c5b5"))
	for layer: int in range(3):
		var points := PackedVector2Array([Vector2(0,h)])
		for i: int in range(13):
			points.append(Vector2(w*i/12.0,h*(0.42+layer*0.12)+sin(i*1.7+layer)*h*0.14))
		points.append(Vector2(w,h))
		draw_colored_polygon(points, [Color("1b3040"),Color("172b36"),Color("12232e")][layer])
	for i: int in range(7):
		var x: float = w*(0.1+i*0.14)
		draw_line(Vector2(x,h*0.64),Vector2(x+40,h),Color("233843"),2)
	for j: int in range(5):
		draw_line(Vector2(0,h*(0.68+j*0.07)),Vector2(w,h*(0.68+j*0.07)),Color("233843"),1)
