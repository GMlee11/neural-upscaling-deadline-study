shader_type spatial;
render_mode unshaded, fog_disabled;

uniform float camera_near = 0.08;
uniform float camera_far = 100.0;

varying float view_depth;

// Carry perspective-correct view depth into the fragment stage.  Logarithmic
// encoding gives approximately uniform relative precision from near to far.
void vertex() {
	vec4 view_position = MODELVIEW_MATRIX * vec4(VERTEX, 1.0);
	view_depth = max(-view_position.z, camera_near);
}


// Repeat one log-depth code in RGB. The trace decoder reverses framebuffer sRGB
// conversion before interpreting this normalized linear value.
void fragment() {
	float normalized_depth = clamp(
		log(view_depth / camera_near) / log(camera_far / camera_near),
		0.0,
		1.0
	);
	ALBEDO = vec3(normalized_depth);
}
