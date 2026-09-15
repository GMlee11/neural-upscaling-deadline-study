shader_type spatial;
render_mode unshaded, fog_disabled;

// Motion is stored as two signed 12-bit fixed-point values in opaque RGB.
// R/G hold each high byte and B packs the two low nibbles.  The range is wide
// enough for fast nearby geometry while retaining subpixel trace precision.
uniform mat4 previous_model_matrix;
uniform mat4 previous_view_projection_matrix;
uniform vec2 output_size = vec2(1280.0, 720.0);
uniform float motion_range_pixels = 256.0;

varying vec4 current_clip_position;
varying vec4 previous_clip_position;


// Preserve the renderer's current clip position and independently project the
// same local vertex through the previous object/camera state.
void vertex() {
	vec4 local_position = vec4(VERTEX, 1.0);
	current_clip_position = PROJECTION_MATRIX * MODELVIEW_MATRIX * local_position;
	previous_clip_position = (
		previous_view_projection_matrix * previous_model_matrix * local_position
	);
	POSITION = current_clip_position;
}


// Encode backward motion: every current pixel points to its source location in
// the previous top-left-origin image captured by Godot.
void fragment() {
	vec2 current_ndc = current_clip_position.xy / current_clip_position.w;
	vec2 previous_ndc = previous_clip_position.xy / previous_clip_position.w;
	vec2 current_uv = current_ndc * 0.5 + 0.5;
	vec2 previous_uv = previous_ndc * 0.5 + 0.5;
	vec2 motion_pixels = vec2(
		(previous_uv.x - current_uv.x) * output_size.x,
		(current_uv.y - previous_uv.y) * output_size.y
	);
	vec2 normalized = clamp(
		motion_pixels / (2.0 * motion_range_pixels) + 0.5,
		vec2(0.0),
		vec2(1.0)
	);
	ivec2 code = ivec2(round(normalized * 4095.0));
	float x_high = float(code.x >> 4) / 255.0;
	float y_high = float(code.y >> 4) / 255.0;
	float packed_low = float(((code.x & 15) << 4) | (code.y & 15)) / 255.0;
	ALBEDO = vec3(x_high, y_high, packed_low);
}
