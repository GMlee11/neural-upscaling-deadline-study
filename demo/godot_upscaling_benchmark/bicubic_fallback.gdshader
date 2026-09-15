shader_type canvas_item;
render_mode unshaded;

// The A=-0.75 cubic kernel matches PyTorch/OpenCV residual reconstruction.
// This shader executes 16 texture taps and never enters the LR render target,
// so native-resolution HUD text remains crisp.
float cubic_weight(float distance) {
	float x = abs(distance);
	float coefficient = -0.75;
	if (x <= 1.0) {
		return (
			((coefficient + 2.0) * x - (coefficient + 3.0))
			* x * x + 1.0
		);
	}
	if (x < 2.0) {
		return (
			((coefficient * x - 5.0 * coefficient) * x
			+ 8.0 * coefficient) * x - 4.0 * coefficient
		);
	}
	return 0.0;
}


// Reconstruct one output pixel from the surrounding 4x4 LR neighborhood.
// Clamping the sample coordinates matches the software baselines' replicated
// edge behavior rather than sampling undefined texels beyond the image.
void fragment() {
	vec2 source_size = vec2(textureSize(TEXTURE, 0));
	vec2 source_position = UV * source_size - vec2(0.5);
	vec2 base_pixel = floor(source_position);
	vec2 fraction = source_position - base_pixel;
	vec4 accumulated = vec4(0.0);
	float total_weight = 0.0;

	for (int offset_y = -1; offset_y <= 2; offset_y++) {
		for (int offset_x = -1; offset_x <= 2; offset_x++) {
			vec2 offset = vec2(float(offset_x), float(offset_y));
			float weight = (
				cubic_weight(offset.x - fraction.x)
				* cubic_weight(offset.y - fraction.y)
			);
			vec2 sample_pixel = clamp(
				base_pixel + offset,
				vec2(0.0),
				source_size - vec2(1.0)
			);
			vec2 sample_uv = (sample_pixel + vec2(0.5)) / source_size;
			accumulated += texture(TEXTURE, sample_uv) * weight;
			total_weight += weight;
		}
	}

	COLOR = accumulated / max(total_weight, 0.000001);
}
