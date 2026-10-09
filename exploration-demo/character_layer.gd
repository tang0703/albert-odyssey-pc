extends Node2D
## One persistent source sprite; coordinates are local to the shared map canvas.
var texture: Texture2D
var target_rect: Rect2

func show_sprite(image: Texture2D, rectangle: Rect2, priority_material: Material, order: int) -> void:
	var changed: bool = texture != image or target_rect != rectangle
	texture = image
	target_rect = rectangle
	material = priority_material
	z_index = order
	visible = true
	if changed: queue_redraw()

func _draw() -> void:
	if texture != null: draw_texture_rect(texture, target_rect, false)
