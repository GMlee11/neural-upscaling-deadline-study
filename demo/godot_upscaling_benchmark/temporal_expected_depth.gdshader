shader_type spatial;
render_mode unshaded, fog_disabled;

uniform mat4 previous_model_matrix;
uniform mat4 previous_view_matrix;
uniform float camera_near = 0.08;
uniform float camera_far = 100.0;

varying float previous_view_depth;


// Project the current surface through its previous object and camera transform;
// this is the depth that should be present at the backward-motion coordinate.
void vertex() {
	vec4 previous_view_position = (
		previous_view_matrix * previous_model_matrix * vec4(VERTEX, 1.0)
	);
	previous_view_depth = max(-previous_view_position.z, camera_near);
}


// Use the same logarithmic convention as the current-depth pass so a relative
// consistency test can reject disocclusion without reconstructing world space.
void fragment() {
	float normalized_depth = clamp(
		log(previous_view_depth / camera_near) / log(camera_far / camera_near),
		0.0,
		1.0
	);
	ALBEDO = vec3(normalized_depth);
}
