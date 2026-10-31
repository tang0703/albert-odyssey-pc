shader_type canvas_item;
render_mode unshaded;
uniform sampler2D scene_screen : hint_screen_texture, filter_nearest, repeat_disable;
uniform float source_offset = 0.0;
void fragment() {
	vec4 scene = texture(scene_screen,SCREEN_UV);
	COLOR = vec4(clamp(scene.rgb + vec3(source_offset),vec3(0.0),vec3(1.0)),1.0);
}
