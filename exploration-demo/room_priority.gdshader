shader_type canvas_item;
render_mode unshaded;
uniform sampler2D source_foreground : source_color, filter_nearest, repeat_disable;
uniform vec2 canvas_size = vec2(320.0,224.0);
uniform vec2 camera_offset = vec2(32.0,0.0);
varying vec2 foreground_uv;
void vertex() {
	foreground_uv = (VERTEX / canvas_size * vec2(320.0,224.0) + camera_offset) / vec2(448.0,256.0);
}
void fragment() {
	vec4 sprite = texture(TEXTURE,UV);
	vec4 foreground = texture(source_foreground,foreground_uv);
	if (foreground.a > 0.5) { sprite.rgb = foreground.rgb; }
	COLOR = sprite;
}
