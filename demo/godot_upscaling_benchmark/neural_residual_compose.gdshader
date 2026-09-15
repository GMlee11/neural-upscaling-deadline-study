shader_type canvas_item;
render_mode unshaded;

// RKNN emits one signed INT8 residual per final RGB output location. The
// native bridge PixelShuffles those values and stores q+128 in an RGB8 texture.
// Keeping reconstruction here lets the GPU reuse the already-present LR render
// while the ARM avoids bicubic interpolation, residual add, and output clamp.
uniform sampler2D residual_texture : filter_nearest, repeat_disable;
uniform float residual_scale = 0.001;
uniform float residual_zero_point = 0.0;
const float CUBIC_A = -0.75;


// Match the A=-0.75 cubic kernel used by model training and CPU validation.
float cubic_weight(float distance) {
	float x = abs(distance);
	if (x <= 1.0) {
		return (
			((CUBIC_A + 2.0) * x - (CUBIC_A + 3.0))
			* x * x + 1.0
		);
	}
	if (x < 2.0) {
		return (
			((CUBIC_A * x - 5.0 * CUBIC_A) * x
			+ 8.0 * CUBIC_A) * x - 4.0 * CUBIC_A
		);
	}
	return 0.0;
}


// Reconstruct the bicubic base and add the dequantized neural correction in
// the same native-resolution fragment. HUD composition remains a later pass.
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

	vec3 base_rgb = accumulated.rgb / max(total_weight, 0.000001);
	vec3 encoded_residual = texture(residual_texture, UV).rgb;
	vec3 quantized_residual = round(encoded_residual * 255.0) - vec3(128.0);
	vec3 correction = (
		quantized_residual - vec3(residual_zero_point)
	) * residual_scale;
	COLOR = vec4(clamp(base_rgb + correction, vec3(0.0), vec3(1.0)), 1.0);
}
