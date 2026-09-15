shader_type canvas_item;

// GPU Lanczos-3 fallback for the direct metadata-admission experiment.
// The filter uses source-texel coordinates and a bounded 6x6 footprint. It is
// intentionally labeled as a GPU implementation rather than assumed identical
// to Pillow's CPU Lanczos kernel; saved frames are validated separately.
float sinc(float x) {
	if (abs(x) < 0.00001) {
		return 1.0;
	}
	float radians = PI * x;
	return sin(radians) / radians;
}

float lanczos3(float x) {
	float distance = abs(x);
	if (distance >= 3.0) {
		return 0.0;
	}
	return sinc(x) * sinc(x / 3.0);
}

void fragment() {
	vec2 source_size = vec2(textureSize(TEXTURE, 0));
	vec2 source_position = UV * source_size - vec2(0.5);
	vec2 base = floor(source_position);
	vec4 weighted = vec4(0.0);
	float total_weight = 0.0;
	for (int y_offset = -2; y_offset <= 3; y_offset++) {
		for (int x_offset = -2; x_offset <= 3; x_offset++) {
			vec2 sample_position = base + vec2(
				float(x_offset),
				float(y_offset)
			);
			vec2 distance = source_position - sample_position;
			float weight = lanczos3(distance.x) * lanczos3(distance.y);
			vec2 sample_uv = (sample_position + vec2(0.5)) / source_size;
			weighted += texture(TEXTURE, clamp(sample_uv, vec2(0.0), vec2(1.0))) * weight;
			total_weight += weight;
		}
	}
	COLOR = weighted / max(abs(total_weight), 0.000001);
}
