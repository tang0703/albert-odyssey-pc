shader_type canvas_item;
render_mode unshaded;

// Foreground is an exact binary-alpha source layer, sampled at map coordinates.
uniform sampler2D source_foreground : source_color, filter_nearest, repeat_disable;
uniform vec2 canvas_size = vec2(320.0, 224.0);
varying vec2 foreground_uv;

void vertex() {
    foreground_uv = VERTEX / canvas_size;
}

void fragment() {
    vec4 sprite = texture(TEXTURE, UV);
    vec4 foreground = texture(source_foreground, foreground_uv);
    // Replace RGB, not alpha: a later priority-2 writer must also cover any
    // earlier priority-3 writer with the foreground's color at this pixel.
    if (foreground.a > 0.5) {
        sprite.rgb = foreground.rgb;
    }
    COLOR = sprite;
}
