extends Node

## Interactive and deterministic low-resolution rendering benchmark.
##
## Godot owns simulation, LR/native rendering, controls, split-screen display,
## and native-resolution HUD composition. The Python runtime owns swappable
## upscalers. Deterministic replay uses this exact scene and request path.

const PROTOCOL_ID := "upscaling-runtime-v1"
const TRANSPORTS := [
	"png",
	"raw_rgb",
	"persistent_tcp_rgb",
	"native_dmabuf",
	"direct_dmabuf",
]
const BACKENDS := [
	"native_render",
	"cpu_bicubic",
	"cpu_lanczos",
	"gpu_bicubic",
	"cpu_onnx_student",
	"gpu_onnx_student",
	"gpu_neural_torch",
	"adaptive_tiles_cpu",
	"npu_rknn",
	"heterogeneous_progressive",
	"fpga_attached",
]
const MODES := {
	"mode_360p_to_720p": {
		"lr": Vector2i(640, 360),
		"hr": Vector2i(1280, 720),
		"label": "640x360 -> 1280x720",
	},
	"mode_180p_to_360p": {
		"lr": Vector2i(320, 180),
		"hr": Vector2i(640, 360),
		"label": "320x180 -> 640x360",
	},
}
const SCENE_VARIANTS := [
	"corridor_neon",
	"forest_outpost",
	"barrier_yard",
	"reflective_plaza",
	"hud_particles",
	"v2_neon_turn",
	"v2_forest_crossing",
	"v2_crate_slalom",
	"v2_reflection_arc",
	"v2_particle_gate",
	"v2_occlusion_lab",
	"p1c_market_pan",
	"p1c_foliage_bridge",
	"p1c_industrial_turn",
]
const COLOR_RENDER_LAYER := 1
const TEMPORAL_MOTION_LAYER := 2
const TEMPORAL_DEPTH_LAYER := 4
const TEMPORAL_EXPECTED_DEPTH_LAYER := 8
const TEMPORAL_MOTION_RANGE_PIXELS := 256.0

var service_url := "http://127.0.0.1:8765"
var backend_id := "cpu_bicubic"
var mode_id := "mode_360p_to_720p"
var benchmark_mode := false
var benchmark_frames := 300
var benchmark_frame_start := 0
var benchmark_total_frames := 0
var benchmark_warmup_frames := 20
var benchmark_fps := 30.0
var maximum_neural_age_frames := 1
var neural_refresh_period_frames := 1
var benchmark_output_dir := ""
var run_id := "godot_steps_11_14"
var temperature_c: Variant = null
var observed_power_w: Variant = null
var power_budget_w: Variant = null
var temperature_limit_c := 80.0
var temperature_critical_c := 90.0
var constraint_trace_id := ""
var transport_id := "raw_rgb"
var stream_host := "127.0.0.1"
var stream_port := 8767
var pipeline_depth := 3
var native_bridge_model_path := ""
var native_bridge_method := "stage_a"
var native_bridge_slots_per_core := 3
var native_bridge_core_profile := "dual_independent_01"
var native_bridge_worker_count := 2
var metadata_selector_path := ""
var npu_topology_policy_path := ""
var neural_refresh_policy_path := ""
var scene_variant_id := "corridor_neon"
var forced_classical_method := ""
var transfer_reference := false
var native_readback := true
var capture_reference := true
var snapshot_stride := 30
var direct_validation_readback := false
var capture_temporal_metadata := false

var world_root: Node3D
var lr_viewport: SubViewport
var hr_viewport: SubViewport
var lr_camera: Camera3D
var hr_camera: Camera3D
var temporal_motion_viewport: SubViewport
var temporal_depth_viewport: SubViewport
var temporal_expected_depth_viewport: SubViewport
var temporal_motion_camera: Camera3D
var temporal_depth_camera: Camera3D
var temporal_expected_depth_camera: Camera3D
var output_rect: TextureRect
var reference_rect: TextureRect
var lr_rect: TextureRect
var hud_label: Label
var help_label: Label
var request_node: HTTPRequest
var output_texture: ImageTexture
var phase7_fallback_material: ShaderMaterial
var phase7_lanczos_material: ShaderMaterial
var phase7_neural_residual_material: ShaderMaterial
var phase7_residual_texture: ImageTexture
var direct_output_textures: Array[ImageTexture] = []
var request_pending := false
var frame_counter := 0
var previous_frame_ms := 0.0
var current_gpu_frame_ms := 0.0
var frame_interval_accumulator := 0.0
var split_enabled := true
var camera_yaw := 0.0
var camera_pitch := -0.08
var last_metadata: Dictionary = {}
var benchmark_pending: Dictionary = {}
var benchmark_completed: Dictionary = {}
var persistent_stream_slots: Array[Dictionary] = []
var native_bridge: Variant = null
var metadata_selector: Dictionary = {}
var npu_topology_policy: Dictionary = {}
var neural_refresh_policy: Dictionary = {}
var renderer_metadata_bins: Dictionary = {}
var last_committed_neural_frame := -1
var last_submitted_neural_frame := -1
var neural_service_ewma_ms: Variant = null
var temporal_proxy_rows: Array[Dictionary] = []
var temporal_history_initialized := false

signal benchmark_response_ready(frame_id: int)


## Parse automation arguments, build the shared scene, and start the chosen mode.
func _ready() -> void:
	_parse_arguments(OS.get_cmdline_user_args())
	if benchmark_mode:
		_configure_unthrottled_benchmark_runtime()
	_build_world()
	_build_viewports()
	_build_interface()
	_apply_mode(mode_id)
	if not metadata_selector_path.is_empty():
		if not _load_metadata_selector(metadata_selector_path):
			get_tree().quit(3)
			return
	if not npu_topology_policy_path.is_empty():
		if not _load_npu_topology_policy(npu_topology_policy_path):
			get_tree().quit(3)
			return
	if not neural_refresh_policy_path.is_empty():
		if not _load_neural_refresh_policy(neural_refresh_policy_path):
			get_tree().quit(3)
			return
	if transport_id == "native_dmabuf" or transport_id == "direct_dmabuf":
		if not await _initialize_native_bridge():
			get_tree().quit(3)
			return
	elif transport_id == "persistent_tcp_rgb":
		if not await _initialize_persistent_streams():
			get_tree().quit(3)
			return
	if benchmark_mode:
		call_deferred("_run_deterministic_replay")
	else:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


## Prevent a remote or unfocused benchmark window from entering Godot's
## low-processor sleep path. The deterministic replay controls its own work and
## must not inherit desktop power-saving cadence as if it were GPU performance.
func _configure_unthrottled_benchmark_runtime() -> void:
	OS.low_processor_usage_mode = false
	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	print(
		"GODOT_BENCHMARK_RUNTIME low_processor=%s max_fps=%d vsync=%d"
		% [
			str(OS.low_processor_usage_mode),
			Engine.max_fps,
			DisplayServer.window_get_vsync_mode(),
		]
	)


## Accept explicit --key=value options plus a standalone --benchmark switch.
func _parse_arguments(arguments: PackedStringArray) -> void:
	for argument in arguments:
		if argument == "--benchmark":
			benchmark_mode = true
			continue
		if not argument.begins_with("--") or not argument.contains("="):
			push_error("unsupported argument: %s" % argument)
			get_tree().quit(2)
			return
		var separator := argument.find("=")
		var key := argument.substr(2, separator - 2).replace("-", "_")
		var value := argument.substr(separator + 1)
		match key:
			"backend": backend_id = value
			"mode": mode_id = value
			"frames": benchmark_frames = int(value)
			"frame_start": benchmark_frame_start = int(value)
			"total_frames": benchmark_total_frames = int(value)
			"warmup_frames": benchmark_warmup_frames = int(value)
			"fps": benchmark_fps = float(value)
			"maximum_neural_age_frames": maximum_neural_age_frames = int(value)
			"neural_refresh_period_frames":
				neural_refresh_period_frames = int(value)
			"output_dir": benchmark_output_dir = value
			"run_id": run_id = value
			"service_url": service_url = value.trim_suffix("/")
			"temperature_c": temperature_c = float(value)
			"observed_power_w": observed_power_w = float(value)
			"power_budget_w": power_budget_w = float(value)
			"constraint_trace": constraint_trace_id = value
			"transport": transport_id = value
			"stream_host": stream_host = value
			"stream_port": stream_port = int(value)
			"pipeline_depth": pipeline_depth = int(value)
			"native_bridge_model": native_bridge_model_path = value
			"native_bridge_method": native_bridge_method = value
			"native_bridge_slots_per_core": native_bridge_slots_per_core = int(value)
			"native_bridge_core_profile": native_bridge_core_profile = value
			"metadata_selector": metadata_selector_path = value
			"npu_topology_policy": npu_topology_policy_path = value
			"neural_refresh_policy": neural_refresh_policy_path = value
			"scene_variant": scene_variant_id = value
			"forced_classical_method": forced_classical_method = value
			"transfer_reference": transfer_reference = (value.to_lower() == "true")
			"native_readback": native_readback = (value.to_lower() == "true")
			"capture_reference": capture_reference = (value.to_lower() == "true")
			"snapshot_stride": snapshot_stride = int(value)
			"direct_validation_readback":
				direct_validation_readback = (value.to_lower() == "true")
			"capture_temporal_metadata":
				capture_temporal_metadata = (value.to_lower() == "true")
			_:
				push_error("unknown argument: --%s" % key.replace("_", "-"))
				get_tree().quit(2)
				return
	# Existing single-process benchmarks need no new argument. Only chunked
	# capture supplies an explicit total timeline larger than this invocation.
	if benchmark_total_frames == 0:
		benchmark_total_frames = benchmark_frames
	if not BACKENDS.has(backend_id):
		push_error("unknown backend: %s" % backend_id)
		get_tree().quit(2)
	if not MODES.has(mode_id):
		push_error("unknown mode: %s" % mode_id)
		get_tree().quit(2)
	if not SCENE_VARIANTS.has(scene_variant_id):
		push_error("unknown scene variant: %s" % scene_variant_id)
		get_tree().quit(2)
	if not forced_classical_method.is_empty() and not [
		"bicubic", "lanczos"
	].has(forced_classical_method):
		push_error("forced classical method must be bicubic or lanczos")
		get_tree().quit(2)
	if benchmark_frames < 1 or benchmark_warmup_frames < 0 or benchmark_fps <= 0.0:
		push_error("benchmark frames/FPS must be positive and warmups nonnegative")
		get_tree().quit(2)
	if (
		benchmark_frame_start < 0
		or benchmark_total_frames < 1
		or benchmark_frame_start + benchmark_frames > benchmark_total_frames
	):
		push_error("benchmark frame chunk must remain inside the total replay")
		get_tree().quit(2)
	if capture_temporal_metadata and not capture_reference:
		push_error("temporal metadata capture requires the synchronized HR reference")
		get_tree().quit(2)
	if (
		not TRANSPORTS.has(transport_id)
		or pipeline_depth < 1
		or snapshot_stride < 1
		or stream_port < 1
		or stream_port > 65535
		or maximum_neural_age_frames < 1
		or maximum_neural_age_frames > 4
		or neural_refresh_period_frames < 1
		or native_bridge_slots_per_core < 1
		or native_bridge_slots_per_core > 8
	):
		push_error("transport, pipeline depth, and snapshot stride are invalid")
		get_tree().quit(2)
	if (
		(transport_id == "native_dmabuf" or transport_id == "direct_dmabuf")
		and (
			native_bridge_model_path.is_empty()
			or native_bridge_method.is_empty()
			or not [
				"dual_independent_01",
				"single_core_0",
				"single_core_1",
				"single_dualcore_01",
				"preloaded_split_fused_012",
			].has(native_bridge_core_profile)
		)
	):
		push_error("native DMA-BUF transport requires a model and stage method")
		get_tree().quit(2)
	if (
		native_bridge_core_profile == "preloaded_split_fused_012"
		and npu_topology_policy_path.is_empty()
	):
		push_error("preloaded split/fused profile requires a topology policy")
		get_tree().quit(2)


## Release native RKNN contexts after all deterministic workers have drained.
func _exit_tree() -> void:
	if native_bridge != null:
		native_bridge.close()
		native_bridge = null


## Build a dense original scene with thin geometry, motion cues, and materials.
func _build_world() -> void:
	world_root = Node3D.new()
	world_root.name = "BenchmarkWorld"
	add_child(world_root)
	var environment_node := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.025, 0.045, 0.085)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.46, 0.52, 0.68)
	environment.ambient_light_energy = 0.72
	environment_node.environment = environment
	world_root.add_child(environment_node)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52.0, -28.0, 0.0)
	sun.light_energy = 1.25
	# The benchmark targets low-power rendering. Real-time shadow maps dominate
	# this small Mali GPU without changing the upscaler's thin-edge workload, so
	# automated measurements disable them while interactive desktop use retains
	# the richer presentation.
	sun.shadow_enabled = not benchmark_mode
	world_root.add_child(sun)
	_add_box(Vector3(0.0, -0.2, -28.0), Vector3(16.0, 0.4, 64.0), Color(0.11, 0.13, 0.17), 0.15, false, ["repeated_patterns"], 2.0)

	# Alternating structures, lane marks, rails, lights, and signs make forward
	# motion visible and stress exactly the edges the upscaler must reconstruct.
	for index in range(28):
		var z := -float(index) * 2.2 - 2.0
		var side := -1.0 if index % 2 == 0 else 1.0
		_add_box(Vector3(-4.8, 1.2, z), Vector3(2.6, 2.4 + (index % 3), 1.3), Color(0.16, 0.22 + 0.01 * (index % 4), 0.31), 0.55, false, ["reflective_surfaces"], 2.2)
		_add_box(Vector3(4.8, 1.0, z - 0.8), Vector3(2.2, 2.0 + (index % 4), 1.1), Color(0.25, 0.17, 0.30 + 0.01 * (index % 5)), 0.45, false, ["reflective_surfaces"], 2.0)
		_add_box(Vector3(side * 2.7, 0.055, z), Vector3(0.12, 0.11, 1.15), Color(0.96, 0.78, 0.22), 0.1, false, ["thin_geometry", "repeated_patterns"], 0.5)
		_add_cylinder(Vector3(side * 3.35, 1.0, z - 0.4), 0.055, 2.0, Color(0.50, 0.62, 0.72), ["thin_geometry", "fences"], 0.8)
		if index % 3 == 0:
			_add_box(Vector3(side * 3.35, 1.75, z - 0.4), Vector3(0.9, 0.5, 0.08), Color(0.08, 0.85, 0.95), 0.2, true, ["thin_geometry", "repeated_patterns"], 0.8)
	for rail_side in [-1.0, 1.0]:
		_add_box(Vector3(rail_side * 3.55, 0.52, -30.0), Vector3(0.09, 0.09, 60.0), Color(0.55, 0.62, 0.70), 0.75, false, ["thin_geometry", "fences", "repeated_patterns"], 2.5)
		for post in range(31):
			_add_box(Vector3(rail_side * 3.55, 0.33, -float(post) * 2.0), Vector3(0.08, 0.66, 0.08), Color(0.44, 0.51, 0.60), 0.7, false, ["thin_geometry", "fences"], 0.35)

	# Moving emissive cubes provide deterministic temporal change without any
	# random-number dependency between interactive and replay operation.
	for index in range(6):
		var mover := MeshInstance3D.new()
		mover.name = "Mover_%02d" % index
		var mesh := BoxMesh.new()
		mesh.size = Vector3(0.42, 0.42, 0.42)
		mover.mesh = mesh
		mover.position = Vector3(-2.0 + 0.8 * index, 1.2 + 0.15 * (index % 2), -8.0 - 5.5 * index)
		mover.set_meta("base_position", mover.position)
		mover.set_meta("phase", float(index) * 0.71)
		mover.set_meta("content_tags", ["particles"])
		mover.set_meta("coverage_weight", 0.8)
		_register_renderer_metadata(
			mover.position,
			["particles"],
			0.8,
		)
		mover.material_override = _material(Color(0.95, 0.22 + index * 0.08, 0.12), 0.1, true)
		world_root.add_child(mover)
		_register_temporal_proxy(mover)
	_build_scene_variant_content()


## Add deterministic content that makes each Paper-1 temporal scene distinct.
##
## All geometry is authored before measurement, so renderer metadata remains a
## bounded bin lookup rather than a per-frame scene-tree scan on the ARM CPU.
func _build_scene_variant_content() -> void:
	if scene_variant_id == "corridor_neon":
		for index in range(12):
			_add_box(
				Vector3(-2.2 + float(index % 4) * 1.45, 0.28, -5.0 - index * 4.1),
				Vector3(0.72, 0.56, 0.72),
				Color(0.12, 0.62, 0.88),
				0.22,
				index % 3 == 0,
				["repeated_patterns", "reflective_surfaces"],
				0.7,
			)
	elif scene_variant_id == "forest_outpost":
		for index in range(34):
			var side := -1.0 if index % 2 == 0 else 1.0
			var z := -2.0 - float(index) * 1.75
			_add_cylinder(
				Vector3(side * (2.5 + 0.35 * (index % 4)), 1.35, z),
				0.12 + 0.015 * (index % 3),
				2.7,
				Color(0.24, 0.18, 0.10),
				["thin_geometry", "foliage"],
				0.85,
			)
			_add_box(
				Vector3(side * (2.5 + 0.35 * (index % 4)), 2.75, z),
				Vector3(0.9, 0.75, 0.9),
				Color(0.12, 0.42 + 0.03 * (index % 3), 0.16),
				0.75,
				false,
				["foliage"],
				1.2,
			)
	elif scene_variant_id == "barrier_yard":
		for row in range(8):
			var z := -6.0 - float(row) * 6.5
			for column in range(9):
				var x := -3.2 + float(column) * 0.8
				_add_cylinder(
					Vector3(x, 0.6, z),
					0.035,
					1.2,
					Color(0.72, 0.72, 0.68),
					["thin_geometry", "fences", "repeated_patterns"],
					0.3,
				)
			_add_box(
				Vector3(0.0, 1.0, z),
				Vector3(6.8, 0.055, 0.055),
				Color(0.92, 0.42, 0.10),
				0.5,
				false,
				["thin_geometry", "fences", "repeated_patterns"],
				1.5,
			)
	elif scene_variant_id == "reflective_plaza":
		for index in range(22):
			var side := -1.0 if index % 2 == 0 else 1.0
			_add_box(
				Vector3(side * (2.0 + 0.3 * (index % 5)), 1.1, -3.0 - index * 2.6),
				Vector3(1.25, 2.2, 0.22),
				Color(0.22 + 0.02 * (index % 4), 0.52, 0.68),
				0.08,
				index % 4 == 0,
				["reflective_surfaces", "thin_geometry"],
				1.4,
			)
	elif scene_variant_id == "hud_particles":
		# Bright sign-like panels and tiny moving-looking markers stress text,
		# particles, and high-contrast edge reconstruction without putting the
		# native-resolution benchmark HUD into the LR render target.
		for index in range(30):
			var side := -1.0 if index % 2 == 0 else 1.0
			_add_box(
				Vector3(side * 2.9, 1.4 + 0.25 * (index % 3), -2.0 - index * 1.95),
				Vector3(0.82, 0.28, 0.06),
				Color(0.96, 0.24 + 0.08 * (index % 5), 0.18),
				0.18,
				true,
				["hud_text", "particles", "thin_geometry"],
				0.75,
			)
	elif scene_variant_id == "v2_neon_turn":
		# Alternating luminous gates create strong parallax during the curved path.
		for index in range(18):
			var side := -1.0 if index % 2 == 0 else 1.0
			var z := -3.0 - float(index) * 3.0
			_add_box(
				Vector3(side * 2.35, 1.45, z),
				Vector3(0.16, 2.9, 0.38),
				Color(0.10, 0.76, 0.96) if side < 0.0 else Color(0.96, 0.18, 0.58),
				0.12,
				true,
				["thin_geometry", "reflective_surfaces"],
				1.1,
			)
			_add_box(
				Vector3(0.0, 2.85, z),
				Vector3(4.9, 0.14, 0.38),
				Color(0.18, 0.28, 0.42),
				0.3,
				false,
				["repeated_patterns", "thin_geometry"],
				1.0,
			)
	elif scene_variant_id == "v2_forest_crossing":
		# Dense trunks and crossing rails reveal depth rejection failures quickly.
		for index in range(46):
			var side := -1.0 if index % 2 == 0 else 1.0
			var z := -1.0 - float(index) * 1.25
			var x := side * (1.9 + 0.28 * float(index % 6))
			_add_cylinder(
				Vector3(x, 1.65, z),
				0.10 + 0.02 * float(index % 4),
				3.3,
				Color(0.26, 0.16, 0.08),
				["foliage", "thin_geometry"],
				0.8,
			)
			_add_box(
				Vector3(x, 3.1, z),
				Vector3(0.75, 0.55, 0.75),
				Color(0.10, 0.34 + 0.03 * float(index % 4), 0.13),
				0.8,
				false,
				["foliage"],
				0.9,
			)
	elif scene_variant_id == "v2_crate_slalom":
		# Staggered close crates force substantial lateral motion and reveal borders.
		for index in range(24):
			var side := -1.0 if index % 2 == 0 else 1.0
			var z := -4.0 - float(index) * 2.25
			_add_box(
				Vector3(side * 1.45, 0.62, z),
				Vector3(1.05, 1.24, 1.05),
				Color(0.48, 0.27 + 0.02 * float(index % 5), 0.10),
				0.72,
				false,
				["repeated_patterns"],
				1.4,
			)
			_add_box(
				Vector3(side * 1.45, 1.3, z - 0.52),
				Vector3(0.72, 0.06, 0.06),
				Color(0.95, 0.76, 0.16),
				0.35,
				true,
				["thin_geometry"],
				0.5,
			)
	elif scene_variant_id == "v2_reflection_arc":
		# Offset metallic panels expose history errors in highlights and seams.
		for index in range(32):
			var angle := float(index) * 0.47
			var side := -1.0 if index % 2 == 0 else 1.0
			_add_box(
				Vector3(
					side * (2.25 + 0.35 * sin(angle)),
					1.25,
					-2.0 - float(index) * 1.75
				),
				Vector3(0.95, 2.5, 0.11),
				Color(0.16 + 0.03 * float(index % 4), 0.48, 0.74),
				0.04,
				index % 5 == 0,
				["reflective_surfaces", "thin_geometry"],
				1.2,
			)
	elif scene_variant_id == "v2_particle_gate":
		# Sealed variant: many tiny bright markers cross close occluding frames.
		for index in range(42):
			var side := -1.0 if index % 2 == 0 else 1.0
			var z := -2.0 - float(index) * 1.3
			_add_box(
				Vector3(side * (1.6 + 0.2 * float(index % 5)), 1.0 + 0.19 * float(index % 6), z),
				Vector3(0.16, 0.16, 0.16),
				Color(0.98, 0.20 + 0.09 * float(index % 6), 0.12),
				0.1,
				true,
				["particles", "thin_geometry"],
				0.35,
			)
	elif scene_variant_id == "v2_occlusion_lab":
		# Sealed occlusion lab: near alternating walls repeatedly reveal background.
		for index in range(20):
			var side := -1.0 if index % 2 == 0 else 1.0
			_add_box(
				Vector3(side * 1.75, 1.55, -3.0 - float(index) * 2.75),
				Vector3(2.1, 3.1, 0.32),
				Color(0.30 + 0.03 * float(index % 4), 0.22, 0.52),
				0.45,
				false,
				["thin_geometry", "repeated_patterns"],
				1.8,
			)
	elif scene_variant_id == "p1c_market_pan":
		# Confirmatory scene 1 combines sign-like panels, posts, and irregular
		# stalls. Its lateral camera sweep was frozen before any output metric.
		for index in range(36):
			var side := -1.0 if index % 2 == 0 else 1.0
			var z := -2.0 - float(index) * 1.48
			_add_box(
				Vector3(side * (2.0 + 0.22 * float(index % 4)), 1.15, z),
				Vector3(0.92, 1.55, 0.28),
				Color(0.18 + 0.11 * float(index % 5), 0.24, 0.72),
				0.52,
				index % 6 == 0,
				["hud_text", "repeated_patterns", "thin_geometry"],
				1.0,
			)
			_add_cylinder(
				Vector3(side * 1.28, 1.45, z - 0.48),
				0.045,
				2.9,
				Color(0.72, 0.74, 0.78),
				["thin_geometry"],
				0.35,
			)
	elif scene_variant_id == "p1c_foliage_bridge":
		# Confirmatory scene 2 deliberately mixes dense foliage silhouettes with
		# bridge rails and repeating gaps that create frequent disocclusions.
		for index in range(52):
			var side := -1.0 if index % 2 == 0 else 1.0
			var z := -1.5 - float(index) * 1.08
			var x := side * (2.15 + 0.30 * float(index % 5))
			_add_cylinder(
				Vector3(x, 1.55, z),
				0.09 + 0.015 * float(index % 3),
				3.1,
				Color(0.20, 0.13, 0.07),
				["foliage", "thin_geometry"],
				0.70,
			)
			_add_box(
				Vector3(side * 1.72, 0.88, z),
				Vector3(0.06, 0.08, 1.35),
				Color(0.70, 0.50, 0.20),
				0.62,
				false,
				["fences", "repeated_patterns", "thin_geometry"],
				0.42,
			)
	elif scene_variant_id == "p1c_industrial_turn":
		# Confirmatory scene 3 stresses close metallic occluders, horizontal
		# seams, and emissive pipe markers during a stronger authored turn.
		for index in range(28):
			var side := -1.0 if index % 2 == 0 else 1.0
			var z := -2.5 - float(index) * 1.95
			_add_box(
				Vector3(side * 1.95, 1.35, z),
				Vector3(1.45, 2.7, 0.16),
				Color(0.16, 0.38 + 0.04 * float(index % 4), 0.48),
				0.06,
				false,
				["reflective_surfaces", "thin_geometry"],
				1.35,
			)
			_add_cylinder(
				Vector3(side * 1.12, 2.15, z - 0.42),
				0.07,
				2.4,
				Color(0.96, 0.34, 0.08),
				["pipes", "thin_geometry"],
				0.55,
			)


## Create a physically based material; emission is explicit for bright edge tests.
func _material(color: Color, roughness: float, emissive := false) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = roughness
	material.metallic = 0.25 if roughness < 0.5 else 0.0
	if emissive:
		material.emission_enabled = true
		material.emission = color
		material.emission_energy_multiplier = 2.2
	return material


## Add one positioned box with an independently owned mesh and material.
func _add_box(
	position: Vector3,
	size: Vector3,
	color: Color,
	roughness: float,
	emissive := false,
	content_tags: Array = [],
	coverage_weight := 1.0,
) -> void:
	var instance := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size
	instance.mesh = mesh
	instance.position = position
	instance.material_override = _material(color, roughness, emissive)
	instance.set_meta("content_tags", content_tags)
	instance.set_meta("coverage_weight", coverage_weight)
	world_root.add_child(instance)
	_register_temporal_proxy(instance)
	_register_renderer_metadata(position, content_tags, coverage_weight)


## Add one thin cylinder used for poles and high-frequency vertical detail.
func _add_cylinder(
	position: Vector3,
	radius: float,
	height: float,
	color: Color,
	content_tags: Array = [],
	coverage_weight := 1.0,
) -> void:
	var instance := MeshInstance3D.new()
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = height
	# Eight sides are enough for narrow poles at this scale and avoid spending
	# embedded-GPU work on curvature that is not visible in the LR frame.
	mesh.radial_segments = 8
	instance.mesh = mesh
	instance.position = position
	instance.material_override = _material(color, 0.48)
	instance.set_meta("content_tags", content_tags)
	instance.set_meta("coverage_weight", coverage_weight)
	world_root.add_child(instance)
	_register_temporal_proxy(instance)
	_register_renderer_metadata(position, content_tags, coverage_weight)


## Mirror one color mesh into hidden motion/depth layers used only by V2 traces.
##
## Proxies are children of the original mesh, so deterministic object animation
## is inherited exactly. Each owns its material because previous model matrices
## differ per object even when the underlying mesh resource is shared.
func _register_temporal_proxy(original: MeshInstance3D) -> void:
	if not capture_temporal_metadata:
		return
	original.layers = COLOR_RENDER_LAYER
	var motion_proxy := MeshInstance3D.new()
	motion_proxy.name = "%s_TemporalMotion" % original.name
	motion_proxy.mesh = original.mesh
	motion_proxy.layers = TEMPORAL_MOTION_LAYER
	var motion_material := ShaderMaterial.new()
	motion_material.shader = load("res://temporal_motion.gdshader")
	motion_material.set_shader_parameter(
		"motion_range_pixels", TEMPORAL_MOTION_RANGE_PIXELS
	)
	motion_proxy.material_override = motion_material
	original.add_child(motion_proxy)

	var depth_proxy := MeshInstance3D.new()
	depth_proxy.name = "%s_TemporalDepth" % original.name
	depth_proxy.mesh = original.mesh
	depth_proxy.layers = TEMPORAL_DEPTH_LAYER
	var depth_material := ShaderMaterial.new()
	depth_material.shader = load("res://temporal_depth.gdshader")
	depth_proxy.material_override = depth_material
	original.add_child(depth_proxy)

	var expected_proxy := MeshInstance3D.new()
	expected_proxy.name = "%s_TemporalExpectedDepth" % original.name
	expected_proxy.mesh = original.mesh
	expected_proxy.layers = TEMPORAL_EXPECTED_DEPTH_LAYER
	var expected_material := ShaderMaterial.new()
	expected_material.shader = load("res://temporal_expected_depth.gdshader")
	expected_proxy.material_override = expected_material
	original.add_child(expected_proxy)

	temporal_proxy_rows.append(
		{
			"original": original,
			"motion_material": motion_material,
			"expected_depth_material": expected_material,
		}
	)


## Aggregate authored object tags into coarse forward-path spatial bins.
##
## A production renderer would update these counters while culling draw calls.
## Pre-binning preserves that constant-cost contract in Godot and avoids an
## expensive scene-tree scan in the admission path on the ARM CPU.
func _register_renderer_metadata(
	position: Vector3,
	content_tags: Array,
	coverage_weight: float,
) -> void:
	if content_tags.is_empty() or coverage_weight <= 0.0:
		return
	var bin_index := int(floor(position.z / 2.0))
	if not renderer_metadata_bins.has(bin_index):
		renderer_metadata_bins[bin_index] = {}
	var tag_weights: Dictionary = renderer_metadata_bins[bin_index]
	for tag_value in content_tags:
		var tag := str(tag_value)
		tag_weights[tag] = float(tag_weights.get(tag, 0.0)) + coverage_weight
	renderer_metadata_bins[bin_index] = tag_weights


## Create synchronized LR and native-reference viewports sharing one 3D world.
func _build_viewports() -> void:
	lr_viewport = SubViewport.new()
	lr_viewport.name = "LowResolutionViewport"
	lr_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	lr_viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
	lr_viewport.world_3d = get_viewport().world_3d
	add_child(lr_viewport)
	lr_camera = Camera3D.new()
	lr_camera.current = true
	lr_camera.fov = 72.0
	lr_camera.near = 0.08
	lr_camera.far = 100.0
	lr_camera.cull_mask = COLOR_RENDER_LAYER
	lr_viewport.add_child(lr_camera)

	hr_viewport = SubViewport.new()
	hr_viewport.name = "NativeReferenceViewport"
	hr_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	hr_viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
	hr_viewport.world_3d = get_viewport().world_3d
	add_child(hr_viewport)
	hr_camera = Camera3D.new()
	hr_camera.current = true
	hr_camera.fov = lr_camera.fov
	hr_camera.near = lr_camera.near
	hr_camera.far = lr_camera.far
	hr_camera.cull_mask = COLOR_RENDER_LAYER
	hr_viewport.add_child(hr_camera)

	if capture_temporal_metadata:
		var metadata_environment := Environment.new()
		metadata_environment.background_mode = Environment.BG_COLOR
		metadata_environment.background_color = Color.BLACK
		metadata_environment.ambient_light_source = Environment.AMBIENT_SOURCE_DISABLED

		temporal_motion_viewport = SubViewport.new()
		temporal_motion_viewport.name = "TemporalMotionViewport"
		temporal_motion_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		temporal_motion_viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
		temporal_motion_viewport.world_3d = get_viewport().world_3d
		add_child(temporal_motion_viewport)
		temporal_motion_camera = Camera3D.new()
		temporal_motion_camera.current = true
		temporal_motion_camera.fov = lr_camera.fov
		temporal_motion_camera.near = lr_camera.near
		temporal_motion_camera.far = lr_camera.far
		temporal_motion_camera.cull_mask = TEMPORAL_MOTION_LAYER
		temporal_motion_camera.environment = metadata_environment
		temporal_motion_viewport.add_child(temporal_motion_camera)

		temporal_depth_viewport = SubViewport.new()
		temporal_depth_viewport.name = "TemporalDepthViewport"
		temporal_depth_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		temporal_depth_viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
		temporal_depth_viewport.world_3d = get_viewport().world_3d
		add_child(temporal_depth_viewport)
		temporal_depth_camera = Camera3D.new()
		temporal_depth_camera.current = true
		temporal_depth_camera.fov = lr_camera.fov
		temporal_depth_camera.near = lr_camera.near
		temporal_depth_camera.far = lr_camera.far
		temporal_depth_camera.cull_mask = TEMPORAL_DEPTH_LAYER
		temporal_depth_camera.environment = metadata_environment
		temporal_depth_viewport.add_child(temporal_depth_camera)

		temporal_expected_depth_viewport = SubViewport.new()
		temporal_expected_depth_viewport.name = "TemporalExpectedDepthViewport"
		temporal_expected_depth_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		temporal_expected_depth_viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
		temporal_expected_depth_viewport.world_3d = get_viewport().world_3d
		add_child(temporal_expected_depth_viewport)
		temporal_expected_depth_camera = Camera3D.new()
		temporal_expected_depth_camera.current = true
		temporal_expected_depth_camera.fov = lr_camera.fov
		temporal_expected_depth_camera.near = lr_camera.near
		temporal_expected_depth_camera.far = lr_camera.far
		temporal_expected_depth_camera.cull_mask = TEMPORAL_EXPECTED_DEPTH_LAYER
		temporal_expected_depth_camera.environment = metadata_environment
		temporal_expected_depth_viewport.add_child(temporal_expected_depth_camera)
	_set_camera_transform(Vector3(0.0, 1.65, 3.0), 0.0, -0.08)


## Build split-screen textures and a HUD that never enters the LR render target.
func _build_interface() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var background := ColorRect.new()
	background.color = Color(0.012, 0.016, 0.028)
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	layer.add_child(background)
	output_rect = TextureRect.new()
	output_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	output_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	phase7_fallback_material = ShaderMaterial.new()
	phase7_fallback_material.shader = load("res://bicubic_fallback.gdshader")
	phase7_lanczos_material = ShaderMaterial.new()
	phase7_lanczos_material.shader = load("res://lanczos_fallback.gdshader")
	phase7_neural_residual_material = ShaderMaterial.new()
	phase7_neural_residual_material.shader = load(
		"res://neural_residual_compose.gdshader"
	)
	layer.add_child(output_rect)
	reference_rect = TextureRect.new()
	reference_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	reference_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	reference_rect.texture = hr_viewport.get_texture()
	layer.add_child(reference_rect)
	lr_rect = TextureRect.new()
	lr_rect.position = Vector2(18.0, 530.0)
	lr_rect.size = Vector2(288.0, 162.0)
	lr_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	lr_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	lr_rect.texture = lr_viewport.get_texture()
	layer.add_child(lr_rect)
	var panel := ColorRect.new()
	panel.position = Vector2(0.0, 0.0)
	panel.size = Vector2(1280.0, 88.0)
	panel.color = Color(0.015, 0.025, 0.045, 0.92)
	layer.add_child(panel)
	hud_label = Label.new()
	hud_label.position = Vector2(20.0, 12.0)
	hud_label.size = Vector2(1240.0, 34.0)
	hud_label.add_theme_font_size_override("font_size", 19)
	hud_label.add_theme_color_override("font_color", Color(0.86, 0.95, 1.0))
	layer.add_child(hud_label)
	help_label = Label.new()
	help_label.position = Vector2(20.0, 48.0)
	help_label.size = Vector2(1240.0, 28.0)
	help_label.text = "WASD / left stick: move | mouse / right stick: look | Tab/RB: backend | M/LB: resolution | V/Y: split"
	help_label.add_theme_font_size_override("font_size", 13)
	help_label.add_theme_color_override("font_color", Color(0.62, 0.73, 0.84))
	layer.add_child(help_label)
	request_node = HTTPRequest.new()
	request_node.timeout = 30.0
	request_node.request_completed.connect(_on_interactive_request_completed)
	add_child(request_node)
	_apply_split_layout()
	_update_hud()


## Resize only render targets; the main UI always remains native 1280x720.
func _apply_mode(new_mode: String) -> void:
	mode_id = new_mode
	var mode: Dictionary = MODES[mode_id]
	lr_viewport.size = mode["lr"]
	hr_viewport.size = mode["hr"]
	if capture_temporal_metadata:
		temporal_motion_viewport.size = mode["hr"]
		temporal_depth_viewport.size = mode["hr"]
		temporal_expected_depth_viewport.size = mode["hr"]
		for row in temporal_proxy_rows:
			var motion_material: ShaderMaterial = row["motion_material"]
			motion_material.set_shader_parameter(
				"output_size", Vector2(mode["hr"])
			)
	previous_frame_ms = 0.0
	_update_hud()


## Keep both cameras exactly synchronized for native LR/HR comparisons.
func _set_camera_transform(position: Vector3, yaw: float, pitch: float) -> void:
	camera_yaw = yaw
	camera_pitch = clampf(pitch, -1.25, 1.25)
	var rotation := Vector3(camera_pitch, camera_yaw, 0.0)
	var synchronized_cameras: Array = [lr_camera, hr_camera]
	if capture_temporal_metadata:
		synchronized_cameras.append(temporal_motion_camera)
		synchronized_cameras.append(temporal_depth_camera)
		synchronized_cameras.append(temporal_expected_depth_camera)
	for camera in synchronized_cameras:
		camera.position = position
		camera.rotation = rotation


## Return a camera matrix that maps world coordinates into clip coordinates.
func _temporal_view_projection(camera: Camera3D) -> Projection:
	# Godot's renderer-facing PROJECTION_MATRIX includes its clip-space Y flip;
	# Camera3D.get_camera_projection() does not. Match the shader convention so
	# identical current/previous poses encode exactly zero motion.
	var view_projection := camera.get_camera_projection().flipped_y()
	return view_projection * Projection(camera.global_transform.affine_inverse())


## Initialize previous-frame uniforms from the current deterministic state.
##
## This is called after warmup and before measured frame zero, preventing the
## last shader-warmup pose from leaking motion into the first trace frame.
func _reset_temporal_metadata_history() -> void:
	if not capture_temporal_metadata:
		return
	var previous_view_projection := _temporal_view_projection(temporal_motion_camera)
	var previous_view := Projection(
		temporal_expected_depth_camera.global_transform.affine_inverse()
	)
	for row in temporal_proxy_rows:
		var original: MeshInstance3D = row["original"]
		var motion_material: ShaderMaterial = row["motion_material"]
		var expected_material: ShaderMaterial = row["expected_depth_material"]
		motion_material.set_shader_parameter(
			"previous_model_matrix", original.global_transform
		)
		motion_material.set_shader_parameter(
			"previous_view_projection_matrix", previous_view_projection
		)
		expected_material.set_shader_parameter(
			"previous_model_matrix", original.global_transform
		)
		expected_material.set_shader_parameter(
			"previous_view_matrix", previous_view
		)
	temporal_history_initialized = true


## Commit the just-rendered state as history for the next measured frame.
func _advance_temporal_metadata_history() -> void:
	_reset_temporal_metadata_history()


## Animate deterministic scene content from the replay's logical time only.
func _update_scene_time(logical_time: float) -> void:
	for child in world_root.get_children():
		if child is MeshInstance3D and child.has_meta("base_position"):
			var base: Vector3 = child.get_meta("base_position")
			var phase := float(child.get_meta("phase"))
			child.position = base + Vector3(sin(logical_time * 1.7 + phase) * 0.75, cos(logical_time * 2.1 + phase) * 0.18, 0.0)
			child.rotation.y = logical_time * 0.55 + phase


## Drive a smooth forward path with slight authored curvature but no camera bob.
func _set_replay_camera(frame_id: int) -> void:
	var progress := float(frame_id) / maxf(1.0, float(benchmark_total_frames - 1))
	var z := lerpf(3.0, -50.0, progress)
	var path_index := SCENE_VARIANTS.find(scene_variant_id)
	var v2_path := scene_variant_id.begins_with("v2_")
	var confirmatory_path := scene_variant_id.begins_with("p1c_")
	var local_path_index := (
		path_index - 11 if confirmatory_path else (path_index - 5 if v2_path else path_index)
	)
	var path_phase := float(local_path_index) * 0.71
	var path_cycles := 1.75 if confirmatory_path else (1.5 if v2_path else 1.0)
	var path_scale := (
		1.05 + float(local_path_index) * 0.12
		if confirmatory_path
		else 0.85 + float(local_path_index) * 0.10
		if v2_path
		else 0.35 + float(path_index) * 0.12
	)
	var path_angle := progress * PI * 2.0 * path_cycles + path_phase
	var x := path_scale * sin(path_angle)
	# Yaw follows the lateral path direction. The path remains smooth and does
	# not add camera bob, but the stronger V2 turn stresses temporal reprojection.
	var yaw := -0.070 * path_scale * cos(path_angle) if confirmatory_path else (
		-0.055 * path_scale * cos(path_angle) if v2_path else (
		-0.02 * (1.0 + path_index * 0.2) * sin(path_angle)
	))
	var eye_height := 1.58 + float(path_index % 3) * 0.06
	_set_camera_transform(Vector3(x, eye_height, z), yaw, -0.075)
	_update_scene_time(float(frame_id) / benchmark_fps)


## Move interactively while preserving eye-level, non-bobbing camera behavior.
func _process(delta: float) -> void:
	if benchmark_mode:
		return
	var movement := Input.get_vector("move_left", "move_right", "move_forward", "move_backward")
	var forward := -lr_camera.global_transform.basis.z
	var right := lr_camera.global_transform.basis.x
	var position := lr_camera.position + (right * movement.x + forward * -movement.y) * 4.0 * delta
	position.y = 1.65
	var look := Input.get_vector("look_left", "look_right", "look_up", "look_down")
	camera_yaw -= look.x * 1.9 * delta
	camera_pitch -= look.y * 1.4 * delta
	_set_camera_transform(position, camera_yaw, camera_pitch)
	_update_scene_time(Time.get_ticks_msec() / 1000.0)
	frame_interval_accumulator += delta
	if frame_interval_accumulator >= 1.0 / 30.0 and not request_pending:
		frame_interval_accumulator = 0.0
		if backend_id == "native_render":
			output_rect.material = null
			output_rect.texture = hr_viewport.get_texture()
			_update_hud()
		else:
			_send_interactive_frame()


## Handle mouse look independently from controller look axes.
func _unhandled_input(event: InputEvent) -> void:
	if benchmark_mode:
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		camera_yaw -= event.relative.x * 0.0025
		camera_pitch -= event.relative.y * 0.0025
	if event.is_action_pressed("cycle_backend"):
		backend_id = BACKENDS[(BACKENDS.find(backend_id) + 1) % BACKENDS.size()]
		_update_hud()
	if event.is_action_pressed("toggle_mode"):
		_apply_mode("mode_180p_to_360p" if mode_id == "mode_360p_to_720p" else "mode_360p_to_720p")
	if event.is_action_pressed("toggle_split"):
		split_enabled = not split_enabled
		_apply_split_layout()
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


## Position output/reference panels without changing rendered image dimensions.
func _apply_split_layout() -> void:
	if split_enabled:
		output_rect.position = Vector2(0.0, 88.0)
		output_rect.size = Vector2(640.0, 632.0)
		reference_rect.position = Vector2(640.0, 88.0)
		reference_rect.size = Vector2(640.0, 632.0)
		reference_rect.visible = true
	else:
		output_rect.position = Vector2(0.0, 88.0)
		output_rect.size = Vector2(1280.0, 632.0)
		reference_rect.visible = false


## Present the current LR render through Godot's GPU bicubic shader.
##
## Phase 7 uses this path immediately when a frame is captured. The display
## therefore never waits for the CPU selector or NPU. A timely neural response
## may replace this texture later; a rejected, stale, or late result leaves the
## already-presented classical frame untouched.
func _present_gpu_fallback(method_id := "bicubic") -> void:
	output_rect.material = (
		phase7_lanczos_material
		if method_id == "lanczos"
		else phase7_fallback_material
	)
	output_rect.texture = lr_viewport.get_texture()


## Compose the NPU's PixelShuffled INT8 residual over the live LR GPU texture.
##
## The payload remains quantized until fragment shading. This removes the ARM
## bicubic, residual add, clamp, and full reconstructed-frame materialization
## while preserving the same A=-0.75 base used during model training.
func _present_gpu_neural_residual(residual_image: Image, metadata: Dictionary) -> void:
	phase7_residual_texture = ImageTexture.create_from_image(residual_image)
	phase7_neural_residual_material.set_shader_parameter(
		"residual_texture",
		phase7_residual_texture,
	)
	phase7_neural_residual_material.set_shader_parameter(
		"residual_scale",
		float(metadata.get("residual_scale", 0.0)),
	)
	phase7_neural_residual_material.set_shader_parameter(
		"residual_zero_point",
		float(metadata.get("residual_zero_point", 0)),
	)
	output_rect.texture = lr_viewport.get_texture()
	output_rect.material = phase7_neural_residual_material


## Capture one interactive LR frame and send it without blocking the render loop.
func _send_interactive_frame() -> void:
	if backend_id == "heterogeneous_progressive":
		_present_gpu_fallback()
	var lr_image := lr_viewport.get_texture().get_image()
	var hr_image := hr_viewport.get_texture().get_image()
	var body := _pack_request_body(lr_image, hr_image)
	var reference_size := hr_image.get_size() if transfer_reference else Vector2i.ZERO
	var headers := _request_headers(frame_counter, lr_image.get_size(), reference_size)
	request_pending = true
	var endpoint := "/upscale-latest" if backend_id == "heterogeneous_progressive" else "/upscale"
	var error := request_node.request_raw(service_url + endpoint, headers, HTTPClient.METHOD_POST, body)
	if error != OK:
		request_pending = false
		last_metadata = {"error": "HTTPRequest start failed: %d" % error}
		_update_hud()
	frame_counter += 1


## Decode an asynchronous interactive response and update the displayed texture.
func _on_interactive_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	request_pending = false
	if response_code != 200:
		last_metadata = {"error": body.get_string_from_utf8()}
		_update_hud()
		return
	var decoded := _decode_response(body)
	if not bool(decoded.get("valid", false)):
		last_metadata = {"error": str(decoded.get("error", "invalid response"))}
		_update_hud()
		return
	last_metadata = decoded["metadata"]
	if decoded["image"] != null:
		if str(last_metadata.get("neural_payload_kind", "")) == "pixelshuffled_int8_residual_biased_128":
			_present_gpu_neural_residual(decoded["image"], last_metadata)
		else:
			output_texture = ImageTexture.create_from_image(decoded["image"])
			output_rect.material = null
			output_rect.texture = output_texture
	elif backend_id == "heterogeneous_progressive":
		_present_gpu_fallback()
	previous_frame_ms = (
		float(last_metadata.get("backend_prepare_ms", 0.0))
		+ float(last_metadata.get("backend_inference_ms", 0.0))
		+ float(last_metadata.get("backend_reconstruction_ms", 0.0))
		+ float(last_metadata.get("backend_materialize_ms", 0.0))
	)
	_update_hud()


## Execute the exact fixed camera path, transport, backend, and composition loop.
func _run_deterministic_replay() -> void:
	if benchmark_output_dir.is_empty():
		push_error("deterministic replay requires --output-dir")
		get_tree().quit(2)
		return
	if DirAccess.make_dir_recursive_absolute(benchmark_output_dir) != OK:
		push_error("could not create benchmark output directory")
		get_tree().quit(2)
		return
	var telemetry_path := benchmark_output_dir.path_join("godot_frames.jsonl")
	var telemetry_mode := (
		FileAccess.READ_WRITE if benchmark_frame_start > 0 else FileAccess.WRITE
	)
	var telemetry := FileAccess.open(telemetry_path, telemetry_mode)
	if telemetry == null:
		push_error("could not create Godot telemetry")
		get_tree().quit(2)
		return
	if benchmark_frame_start > 0:
		telemetry.seek_end()
	# Chunked capture uses global frame IDs. Start the recorder at the same
	# global boundary so a later chunk never waits for an earlier process's row.
	var next_frame_to_record := benchmark_frame_start
	# A native-resolution baseline should render only the HR viewport. The
	# readback-enabled diagnostic deliberately leaves both viewports active so
	# transfer and capture overhead can still be measured separately.
	if backend_id == "native_render" and not native_readback:
		lr_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	elif not capture_reference:
		# Performance runs must not secretly pay for a native-HR render. A
		# separate correctness replay enables this reference viewport.
		hr_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	# Rendering warmups compile shaders and populate driver caches without
	# entering the measured replay. Backend warmups remain the responsibility
	# of the backend-specific runner and are not implied by this loop.
	for warmup_id in range(benchmark_warmup_frames):
		_set_replay_camera(
			(benchmark_frame_start + warmup_id) % benchmark_total_frames
		)
		await RenderingServer.frame_post_draw
	if capture_temporal_metadata:
		# A later chunk initializes history from its immediately preceding global
		# frame so motion/depth metadata remains identical to one 300-frame run.
		_set_replay_camera(maxi(0, benchmark_frame_start - 1))
		_reset_temporal_metadata_history()
		await RenderingServer.frame_post_draw
	var replay_start := Time.get_ticks_usec()
	for local_frame_id in range(benchmark_frames):
		var frame_id := benchmark_frame_start + local_frame_id
		# Phase 7 follows the display clock. Falling behind is measured; future
		# camera states are never submitted early to make throughput look better.
		if backend_id == "heterogeneous_progressive":
			var target_usec := replay_start + int(round(float(local_frame_id) * 1000000.0 / benchmark_fps))
			while Time.get_ticks_usec() < target_usec:
				await get_tree().process_frame
		var frame_capture_start := Time.get_ticks_usec()
		var simulation_start := Time.get_ticks_usec()
		_set_replay_camera(frame_id)
		var simulation_ms := (Time.get_ticks_usec() - simulation_start) / 1000.0
		var render_wait_start := Time.get_ticks_usec()
		await RenderingServer.frame_post_draw
		var render_wait_ms := (Time.get_ticks_usec() - render_wait_start) / 1000.0
		current_gpu_frame_ms = render_wait_ms
		var lr_image: Image = null
		var hr_image: Image = null
		var request_body := PackedByteArray()
		var lr_readback_ms := 0.0
		var reference_readback_ms := 0.0
		var request_pack_ms := 0.0
		var temporal_metadata_readback_ms := 0.0
		var temporal_motion_image: Image = null
		var temporal_depth_image: Image = null
		var temporal_expected_depth_image: Image = null
		if (
			(backend_id != "native_render" or native_readback)
			and transport_id != "direct_dmabuf"
		):
			var readback_start := Time.get_ticks_usec()
			lr_image = lr_viewport.get_texture().get_image()
			lr_readback_ms = (Time.get_ticks_usec() - readback_start) / 1000.0
			if capture_reference or backend_id == "native_render":
				readback_start = Time.get_ticks_usec()
				hr_image = hr_viewport.get_texture().get_image()
				reference_readback_ms = (Time.get_ticks_usec() - readback_start) / 1000.0
			var pack_start := Time.get_ticks_usec()
			request_body = _pack_request_body(lr_image, hr_image)
			request_pack_ms = (Time.get_ticks_usec() - pack_start) / 1000.0
		elif transport_id == "direct_dmabuf" and direct_validation_readback:
			# Publication-quality validation is a separate, deliberately slow
			# run. It captures the exact board-rendered LR/native pair while the
			# performance matrix keeps this synchronous readback disabled.
			var readback_start := Time.get_ticks_usec()
			lr_image = lr_viewport.get_texture().get_image()
			lr_readback_ms = (Time.get_ticks_usec() - readback_start) / 1000.0
			if capture_reference:
				readback_start = Time.get_ticks_usec()
				hr_image = hr_viewport.get_texture().get_image()
				reference_readback_ms = (
					Time.get_ticks_usec() - readback_start
				) / 1000.0
		if capture_temporal_metadata:
			var metadata_readback_start := Time.get_ticks_usec()
			temporal_motion_image = temporal_motion_viewport.get_texture().get_image()
			temporal_depth_image = temporal_depth_viewport.get_texture().get_image()
			temporal_expected_depth_image = (
				temporal_expected_depth_viewport.get_texture().get_image()
			)
			temporal_metadata_readback_ms = (
				Time.get_ticks_usec() - metadata_readback_start
			) / 1000.0
			_advance_temporal_metadata_history()
		var fallback_presented_usec := 0
		if backend_id == "heterogeneous_progressive":
			_present_gpu_fallback()
			fallback_presented_usec = Time.get_ticks_usec()
		# Preserve the historical aggregate while exposing its real components.
		var render_capture_ms := (
			render_wait_ms + lr_readback_ms + reference_readback_ms + request_pack_ms
		)
		current_gpu_frame_ms = render_capture_ms
		var context := {
			"frame_capture_start_usec": frame_capture_start,
			"fallback_presented_usec": fallback_presented_usec,
			"simulation_ms": simulation_ms,
			"render_wait_ms": render_wait_ms,
			"lr_readback_ms": lr_readback_ms,
			"reference_readback_ms": reference_readback_ms,
			"request_pack_ms": request_pack_ms,
			"temporal_metadata_readback_ms": temporal_metadata_readback_ms,
			"temporal_motion_image": temporal_motion_image,
			"temporal_depth_image": temporal_depth_image,
			"temporal_expected_depth_image": temporal_expected_depth_image,
			"render_capture_ms": render_capture_ms,
			"lr_image": lr_image,
			"hr_image": hr_image,
			"request_payload_bytes": request_body.size(),
			"camera_x": lr_camera.position.x,
			"camera_y": lr_camera.position.y,
			"camera_z": lr_camera.position.z,
			"camera_rotation_x": lr_camera.rotation.x,
			"camera_rotation_y": lr_camera.rotation.y,
			"scene_variant_id": scene_variant_id,
		}

		# Native rendering is already complete inside Godot. Returning the exact
		# HR viewport locally avoids inventing a Python "native" backend and
		# keeps this run focused on GPU render/capture/composition performance.
		if backend_id == "native_render":
			context["roundtrip_ms"] = 0.0
			context["response_payload_bytes"] = (
				hr_image.get_data().size() if native_readback else 0
			)
			context["response"] = {
				"valid": true,
				"image": hr_image,
				"metadata": {
					"backend_id": "native_render",
					"backend_prepare_ms": 0.0,
					"backend_inference_ms": 0.0,
					"backend_materialize_ms": 0.0,
					"output_sha256": (
						_sha256_image(hr_image) if native_readback else ""
					),
				},
			}
			benchmark_completed[frame_id] = context
		elif (
			backend_id == "heterogeneous_progressive"
			and not forced_classical_method.is_empty()
		):
			# Pure GPU classical controls use the identical render and display
			# loop without reserving an NPU slot. They are not approximated by a
			# long fixed period that would still submit frame zero.
			context["roundtrip_ms"] = 0.0
			context["response_received_usec"] = Time.get_ticks_usec()
			context["response_payload_bytes"] = 0
			context["response"] = {
				"valid": true,
				"image": null,
				"metadata": {
					"backend_id": "heterogeneous_progressive",
					"route_status": "forced_classical_control",
					"selected_method_id": forced_classical_method,
					"raw_method_id": "forced_classical_control",
					"backend_prepare_ms": 0.0,
					"backend_inference_ms": 0.0,
					"backend_materialize_ms": 0.0,
					"output_sha256": "",
				},
			}
			benchmark_completed[frame_id] = context
		elif (
			backend_id == "heterogeneous_progressive"
			and frame_id % neural_refresh_period_frames != 0
		):
			# Fixed-period refresh is a publication control, not a simulated
			# neural result. Skipped frames present the already-created GPU
			# fallback and complete immediately without submitting NPU work.
			context["roundtrip_ms"] = 0.0
			context["response_received_usec"] = Time.get_ticks_usec()
			context["response_payload_bytes"] = 0
			context["response"] = {
				"valid": true,
				"image": null,
				"metadata": {
					"backend_id": "heterogeneous_progressive",
					"route_status": "fixed_period_fallback",
					"selected_method_id": "bicubic",
					"raw_method_id": "fixed_period",
					"backend_prepare_ms": 0.0,
					"backend_inference_ms": 0.0,
					"backend_materialize_ms": 0.0,
					"output_sha256": "",
				},
			}
			benchmark_completed[frame_id] = context
		else:
			var request_error := _begin_benchmark_request(frame_id, request_body, context)
			if request_error != OK:
				telemetry.close()
				push_error("benchmark request failed to start at frame %d: %d" % [frame_id, request_error])
				get_tree().quit(3)
				return

		# Bound outstanding images so asynchronous overlap cannot grow memory
		# without limit. Results are still recorded in deterministic frame order.
		while frame_id - next_frame_to_record + 1 >= pipeline_depth:
			var completed_context: Dictionary = await _wait_for_benchmark_frame(next_frame_to_record)
			if not await _record_benchmark_frame(telemetry, next_frame_to_record, completed_context, replay_start):
				telemetry.close()
				get_tree().quit(3)
				return
			next_frame_to_record += 1

	# Drain the final in-flight requests in the same deterministic order.
	while next_frame_to_record < benchmark_frame_start + benchmark_frames:
		var completed_context: Dictionary = await _wait_for_benchmark_frame(next_frame_to_record)
		if not await _record_benchmark_frame(telemetry, next_frame_to_record, completed_context, replay_start):
			telemetry.close()
			get_tree().quit(3)
			return
		next_frame_to_record += 1
	telemetry.close()
	print("GODOT_BENCHMARK_COMPLETE frames=%d telemetry=%s" % [benchmark_frames, telemetry_path])
	get_tree().quit(0)


## Hash native RGB bytes with the same lowercase SHA-256 representation used
## by the Python service so deterministic replays remain directly comparable.
func _sha256_image(image: Image) -> String:
	var rgb_image := image.duplicate()
	rgb_image.convert(Image.FORMAT_RGB8)
	var hashing_context := HashingContext.new()
	hashing_context.start(HashingContext.HASH_SHA256)
	hashing_context.update(rgb_image.get_data())
	return hashing_context.finish().hex_encode()


## Start one copied frame request without blocking rendering of the next frame.
func _begin_benchmark_request(frame_id: int, body: PackedByteArray, context: Dictionary) -> Error:
	if transport_id == "direct_dmabuf":
		if not metadata_selector.is_empty():
			var decision := _predict_metadata_route()
			context["metadata_decision"] = decision
			var selected_method := str(decision["method_id"])
			if selected_method == "bicubic" or selected_method == "lanczos":
				context["roundtrip_ms"] = 0.0
				context["response_received_usec"] = Time.get_ticks_usec()
				context["response_payload_bytes"] = 0
				context["response"] = {
					"valid": true,
					"image": null,
					"metadata": {
						"backend_id": "heterogeneous_progressive",
						"route_status": "metadata_classical_bypass",
						"selected_method_id": selected_method,
						"raw_method_id": str(decision["raw_method_id"]),
						"selector_confidence": float(decision["confidence"]),
						"selector_ms": float(decision["selector_ms"]),
						"metadata_features_ms": float(
							decision["metadata_features_ms"]
						),
						"metadata_model_ms": float(
							decision["metadata_model_ms"]
						),
						"renderer_metadata_used": true,
						"control_reasons": decision["control_reasons"],
						"npu_worker_id": null,
						"npu_queue_depth": 0,
						"npu_queue_limit": pipeline_depth,
						"backend_queue_wait_ms": 0.0,
						"backend_queue_service_ms": 0.0,
						"backend_inference_ms": 0.0,
						"backend_materialize_ms": 0.0,
						"host_pixel_bytes_per_frame": 0,
					},
				}
				benchmark_completed[frame_id] = context
				return OK
			# The selected artifact chose no partial stage on its validation or
			# internal test splits. An unexpected partial-stage prediction is
			# conservatively upgraded to the configured complete graph.
			if selected_method != native_bridge_method:
				decision["method_id"] = native_bridge_method
				decision["upgraded_to_configured_graph"] = true
				context["metadata_decision"] = decision
		if not neural_refresh_policy.is_empty():
			var refresh_decision := _predict_neural_refresh(frame_id)
			context["neural_refresh_decision"] = refresh_decision
			if str(refresh_decision["action"]) == "bypass":
				return _complete_refresh_bypass(
					frame_id,
					context,
					refresh_decision,
				)
		return _begin_direct_bridge_request(frame_id, context)
	if transport_id == "native_dmabuf":
		return _begin_native_bridge_request(frame_id, body, context)
	if transport_id == "persistent_tcp_rgb":
		return _begin_persistent_stream_request(frame_id, body, context)
	var request := HTTPRequest.new()
	request.timeout = 60.0
	add_child(request)
	context["roundtrip_start_usec"] = Time.get_ticks_usec()
	benchmark_pending[frame_id] = context
	request.request_completed.connect(_on_benchmark_request_completed.bind(frame_id, request))
	var mode: Dictionary = MODES[mode_id]
	var endpoint := "/upscale-latest" if backend_id == "heterogeneous_progressive" else "/upscale"
	var error := request.request_raw(
		service_url + endpoint,
		_request_headers(
			frame_id,
			mode["lr"],
			mode["hr"] if transfer_reference else Vector2i.ZERO,
		),
		HTTPClient.METHOD_POST,
		body,
	)
	if error != OK:
		benchmark_pending.erase(frame_id)
		request.queue_free()
	return error


## Complete requests in any network order while retaining frame-owned context.
func _on_benchmark_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray, frame_id: int, request: HTTPRequest) -> void:
	var context: Dictionary = benchmark_pending.get(frame_id, {})
	benchmark_pending.erase(frame_id)
	context["response_received_usec"] = Time.get_ticks_usec()
	context["roundtrip_ms"] = (Time.get_ticks_usec() - int(context.get("roundtrip_start_usec", Time.get_ticks_usec()))) / 1000.0
	context["response_payload_bytes"] = body.size()
	context["response"] = (
		_decode_response(body)
		if response_code == 200
		else {"valid": false, "error": body.get_string_from_utf8()}
	)
	benchmark_completed[frame_id] = context
	request.queue_free()
	benchmark_response_ready.emit(frame_id)


## Await a specific frame even if later responses completed first.
func _wait_for_benchmark_frame(frame_id: int) -> Dictionary:
	while not benchmark_completed.has(frame_id):
		if (
			transport_id == "persistent_tcp_rgb"
			or transport_id == "native_dmabuf"
			or transport_id == "direct_dmabuf"
		):
			await get_tree().process_frame
		else:
			await benchmark_response_ready
	var context: Dictionary = benchmark_completed[frame_id]
	benchmark_completed.erase(frame_id)
	return context


## Compose, snapshot, and record one completed frame in replay order.
func _record_benchmark_frame(telemetry: FileAccess, frame_id: int, context: Dictionary, replay_start: int) -> bool:
	var response: Dictionary = context["response"]
	if not bool(response.get("valid", false)):
		push_error("benchmark request failed at frame %d: %s" % [frame_id, str(response.get("error", "unknown"))])
		return false
	var response_image: Variant = response.get("image")
	var response_texture: Variant = response.get("texture")
	var neural_payload_kind := str(
		response.get("metadata", {}).get("neural_payload_kind", "")
	)
	var service_had_neural_image := (
		response_image != null
		or (
			neural_payload_kind == "direct_dmabuf_fused_texture"
			and response_texture != null
		)
	)
	var deadline_ms := (
		float(maximum_neural_age_frames) * 1000.0 / benchmark_fps
	)
	var response_received_usec := int(
		context.get("response_received_usec", Time.get_ticks_usec())
	)
	var neural_response_age_ms := (
		response_received_usec - int(context["frame_capture_start_usec"])
	) / 1000.0
	var has_neural_image := (
		service_had_neural_image and neural_response_age_ms <= deadline_ms
	)
	last_metadata = response["metadata"].duplicate(true)
	if service_had_neural_image and not has_neural_image:
		last_metadata["service_route_status"] = str(
			last_metadata.get("route_status", "")
		)
		last_metadata["route_status"] = "client_late_neural_discarded"
	var upload_start := Time.get_ticks_usec()
	if backend_id != "native_render" or native_readback:
		if has_neural_image:
			if neural_payload_kind == "direct_dmabuf_fused_texture":
				output_texture = response_texture
				output_rect.material = null
				output_rect.texture = output_texture
			elif neural_payload_kind == "pixelshuffled_int8_residual_biased_128":
				_present_gpu_neural_residual(response_image, response["metadata"])
			else:
				output_texture = ImageTexture.create_from_image(response_image)
				output_rect.material = null
	elif backend_id == "heterogeneous_progressive":
		_present_gpu_fallback(
			str(last_metadata.get("selected_method_id", "bicubic"))
		)
	var upload_ms := (Time.get_ticks_usec() - upload_start) / 1000.0
	if has_neural_image and neural_response_age_ms + upload_ms > deadline_ms:
		has_neural_image = false
		last_metadata["service_route_status"] = str(
			last_metadata.get("route_status", "")
		)
		last_metadata["route_status"] = "client_late_neural_discarded"
		_present_gpu_fallback()
	var composition_start := Time.get_ticks_usec()
	if (
		(backend_id != "native_render" or native_readback)
		and has_neural_image
		and neural_payload_kind != "pixelshuffled_int8_residual_biased_128"
		and neural_payload_kind != "direct_dmabuf_fused_texture"
	):
		output_rect.texture = output_texture
	_update_hud()
	var composition_ms := (Time.get_ticks_usec() - composition_start) / 1000.0
	if frame_id % snapshot_stride == 0 and (backend_id != "native_render" or native_readback):
		var snapshot_root := benchmark_output_dir.path_join("snapshots")
		DirAccess.make_dir_recursive_absolute(snapshot_root.path_join("lr"))
		DirAccess.make_dir_recursive_absolute(snapshot_root.path_join("native"))
		DirAccess.make_dir_recursive_absolute(snapshot_root.path_join("output"))
		if capture_temporal_metadata:
			DirAccess.make_dir_recursive_absolute(
				snapshot_root.path_join("temporal_motion")
			)
			DirAccess.make_dir_recursive_absolute(
				snapshot_root.path_join("temporal_depth")
			)
			DirAccess.make_dir_recursive_absolute(
				snapshot_root.path_join("temporal_expected_depth")
			)
			context["temporal_motion_image"].save_png(
				snapshot_root.path_join(
					"temporal_motion/frame_%04d.png" % frame_id
				)
			)
			context["temporal_depth_image"].save_png(
				snapshot_root.path_join(
					"temporal_depth/frame_%04d.png" % frame_id
				)
			)
			context["temporal_expected_depth_image"].save_png(
				snapshot_root.path_join(
					"temporal_expected_depth/frame_%04d.png" % frame_id
				)
			)
		if context["lr_image"] != null:
			context["lr_image"].save_png(
				snapshot_root.path_join("lr/frame_%04d.png" % frame_id)
			)
		if context["hr_image"] != null:
			context["hr_image"].save_png(snapshot_root.path_join("native/frame_%04d.png" % frame_id))
		if has_neural_image and response_image != null:
			if str(last_metadata.get("neural_payload_kind", "")) == "pixelshuffled_int8_residual_biased_128":
				DirAccess.make_dir_recursive_absolute(
					snapshot_root.path_join("residual_payload")
				)
				response_image.save_png(
					snapshot_root.path_join(
						"residual_payload/frame_%04d.png" % frame_id
					)
				)
			else:
				response_image.save_png(snapshot_root.path_join("output/frame_%04d.png" % frame_id))
		elif (
			has_neural_image
			and neural_payload_kind == "direct_dmabuf_fused_texture"
			and direct_validation_readback
		):
			# This diagnostic readback is explicitly excluded from performance
			# runs. Present the native-written texture once before asking Godot
			# to read it back; otherwise ImageTexture may return its original
			# CPU-side allocation rather than the GLES-updated display image.
			await RenderingServer.frame_post_draw
			var direct_output_image: Image = response_texture.get_image()
			direct_output_image.save_png(
				snapshot_root.path_join("output/frame_%04d.png" % frame_id)
			)
			var validation_lr_image: Image = response.get(
				"validation_lr_image"
			)
			var validation_residual_image: Image = response.get(
				"validation_residual_image"
			)
			DirAccess.make_dir_recursive_absolute(
				snapshot_root.path_join("validation_input")
			)
			validation_lr_image.save_png(
				snapshot_root.path_join(
					"validation_input/frame_%04d.png" % frame_id
				)
			)
			# Legacy validation runs disabled source readback, so retain the
			# old `lr` location only when no independent source image exists.
			if context["lr_image"] == null:
				validation_lr_image.save_png(
					snapshot_root.path_join("lr/frame_%04d.png" % frame_id)
				)
			DirAccess.make_dir_recursive_absolute(
				snapshot_root.path_join("residual_payload")
			)
			validation_residual_image.save_png(
				snapshot_root.path_join(
					"residual_payload/frame_%04d.png" % frame_id
				)
			)
	var presentation_start := Time.get_ticks_usec()
	if backend_id != "native_render" or native_readback:
		await get_tree().process_frame
	var presentation_ms := (Time.get_ticks_usec() - presentation_start) / 1000.0
	if neural_payload_kind == "direct_dmabuf_fused_texture":
		var release_result: Dictionary = native_bridge.consume_direct_frame(
			int(last_metadata["direct_frame_token"])
		)
		if not bool(release_result.get("ok", false)):
			push_error(
				"failed to release direct frame %d: %s"
				% [
					frame_id,
					str(release_result.get("error", "unknown")),
				]
			)
	var frame_age_ms := (
		Time.get_ticks_usec() - int(context["frame_capture_start_usec"])
	) / 1000.0
	# Update the service estimate only after a real NPU completion. Bypass rows
	# remain genuine zero-work observations and cannot make future predictions
	# look artificially cheap.
	if service_had_neural_image:
		var observed_service_ms := float(context["roundtrip_ms"])
		var alpha := float(
			neural_refresh_policy.get("service_ewma_alpha", 0.25)
		)
		neural_service_ewma_ms = (
			observed_service_ms
			if neural_service_ewma_ms == null
			else alpha * observed_service_ms
			+ (1.0 - alpha) * float(neural_service_ewma_ms)
		)
	if has_neural_image:
		last_committed_neural_frame = frame_id
	var strict_frame_deadline_ms := 1000.0 / benchmark_fps
	var strict_same_frame_neural := (
		service_had_neural_image
		and neural_response_age_ms + upload_ms <= strict_frame_deadline_ms
	)
	var row := {
		"schema_version": 3,
		"run_id": run_id,
		"frame_id": frame_id,
		"backend_id": backend_id,
		"mode_id": mode_id,
		"scene_variant_id": str(context["scene_variant_id"]),
		"transport_id": transport_id,
		"pipeline_depth": pipeline_depth,
		"native_readback": native_readback,
		"capture_reference": capture_reference,
		"logical_time_seconds": float(frame_id) / benchmark_fps,
		"frame_capture_elapsed_ms": (
			int(context["frame_capture_start_usec"]) - replay_start
		) / 1000.0,
		"fallback_presentation_elapsed_ms": (
			(int(context["fallback_presented_usec"]) - replay_start) / 1000.0
			if int(context["fallback_presented_usec"]) > 0
			else null
		),
		"camera_x": context["camera_x"],
		"camera_y": context["camera_y"],
		"camera_z": context["camera_z"],
		"camera_rotation_x": context["camera_rotation_x"],
		"camera_rotation_y": context["camera_rotation_y"],
		"godot_simulation_ms": context["simulation_ms"],
		"godot_gpu_render_wait_ms": context["render_wait_ms"],
		"godot_lr_readback_ms": context["lr_readback_ms"],
		"godot_reference_readback_ms": context["reference_readback_ms"],
		"godot_request_pack_ms": context["request_pack_ms"],
		"godot_temporal_metadata_readback_ms": context.get(
			"temporal_metadata_readback_ms", 0.0
		),
		"capture_temporal_metadata": capture_temporal_metadata,
		"temporal_motion_range_pixels": TEMPORAL_MOTION_RANGE_PIXELS,
		"godot_render_capture_ms": context["render_capture_ms"],
		"request_transfer_ms": context["roundtrip_ms"],
		"request_payload_bytes": context["request_payload_bytes"],
		"response_payload_bytes": context["response_payload_bytes"],
		"godot_upload_ms": upload_ms,
		"godot_composition_ms": composition_ms,
		"godot_presentation_ms": presentation_ms,
		"frame_age_ms": frame_age_ms,
		"replay_elapsed_ms": (Time.get_ticks_usec() - replay_start) / 1000.0,
		"output_sha256": str(last_metadata.get("output_sha256", "")),
		"has_neural_image": has_neural_image,
		"service_had_neural_image": service_had_neural_image,
		"neural_response_age_ms": neural_response_age_ms,
		"strict_frame_deadline_ms": strict_frame_deadline_ms,
		"strict_same_frame_neural": strict_same_frame_neural,
		"client_deadline_ms": deadline_ms,
		"maximum_neural_age_frames": maximum_neural_age_frames,
		"neural_refresh_period_frames": neural_refresh_period_frames,
		"route_status": str(last_metadata.get("route_status", "")),
		"selected_method_id": str(last_metadata.get("selected_method_id", "")),
		"raw_method_id": str(last_metadata.get("raw_method_id", "")),
		"selector_confidence": float(
			last_metadata.get("selector_confidence", 0.0)
		),
		"renderer_metadata_used": bool(
			last_metadata.get("renderer_metadata_used", false)
		),
		"control_reasons": last_metadata.get("control_reasons", []),
		"npu_worker_id": last_metadata.get("npu_worker_id"),
		"npu_core_mask": int(last_metadata.get("npu_core_mask", 0)),
		"npu_topology_mode": str(
			last_metadata.get("npu_topology_mode", "fixed")
		),
		"npu_topology_reason": str(
			last_metadata.get("npu_topology_reason", "")
		),
		"npu_topology_selector_ms": float(
			last_metadata.get("npu_topology_selector_ms", 0.0)
		),
		"npu_topology_remaining_slack_ms": float(
			last_metadata.get("npu_topology_remaining_slack_ms", 0.0)
		),
		"npu_queue_depth": int(last_metadata.get("npu_queue_depth", 0)),
		"npu_queue_limit": int(last_metadata.get("npu_queue_limit", 0)),
		"npu_queue_wait_ms": float(last_metadata.get("backend_queue_wait_ms", 0.0)),
		"npu_service_ms": float(last_metadata.get("backend_queue_service_ms", 0.0)),
		"refresh_policy_action": str(
			last_metadata.get("refresh_policy_action", "disabled")
		),
		"refresh_policy_reason": str(
			last_metadata.get("refresh_policy_reason", "disabled_control")
		),
		"refresh_policy_selector_ms": float(
			last_metadata.get("refresh_policy_selector_ms", 0.0)
		),
		"refresh_predicted_service_ms": float(
			last_metadata.get("refresh_predicted_service_ms", 0.0)
		),
		"refresh_predicted_completion_age_ms": float(
			last_metadata.get("refresh_predicted_completion_age_ms", 0.0)
		),
		"refresh_predicted_same_frame": bool(
			last_metadata.get("refresh_predicted_same_frame", false)
		),
		"refresh_frames_since_commit": int(
			last_metadata.get("refresh_frames_since_commit", -1)
		),
		"refresh_renderer_priority_score": float(
			last_metadata.get("refresh_renderer_priority_score", 0.0)
		),
		"refresh_renderer_priority": bool(
			last_metadata.get("refresh_renderer_priority", false)
		),
		"refresh_effective_period_frames": int(
			last_metadata.get("refresh_effective_period_frames", 0)
		),
		"selector_ms": float(last_metadata.get("selector_ms", 0.0)),
		"metadata_features_ms": float(
			last_metadata.get("metadata_features_ms", 0.0)
		),
		"metadata_model_ms": float(
			last_metadata.get("metadata_model_ms", 0.0)
		),
		"neural_payload_kind": str(last_metadata.get("neural_payload_kind", "")),
		# Preserve the exact active RKNN output quantizer in every physical
		# row. Correctness tooling must never borrow these values from an older
		# graph merely because both artifacts implement the same stage.
		"residual_scale": float(last_metadata.get("residual_scale", 0.0)),
		"residual_zero_point": int(
			last_metadata.get("residual_zero_point", 0)
		),
		"backend_rga_resize_ms": float(last_metadata.get("backend_rga_resize_ms", 0.0)),
		"backend_residual_pack_ms": float(last_metadata.get("backend_residual_pack_ms", 0.0)),
		"backend_native_total_ms": float(last_metadata.get("backend_native_total_ms", 0.0)),
		"backend_npu_inference_ms": float(
			last_metadata.get("backend_inference_ms", 0.0)
		),
		"backend_gpu_capture_ms": float(last_metadata.get("backend_gpu_capture_ms", 0.0)),
		"backend_rga_input_convert_ms": float(last_metadata.get("backend_rga_input_convert_ms", 0.0)),
		"backend_gpu_compose_ms": float(last_metadata.get("backend_gpu_compose_ms", 0.0)),
	}
	telemetry.store_line(JSON.stringify(row))
	previous_frame_ms = float(context["roundtrip_ms"])
	if frame_id % 30 == 0 or frame_id + 1 == benchmark_total_frames:
		print("GODOT_BENCHMARK_PROGRESS frame=%d/%d backend=%s mode=%s transport=%s depth=%d" % [frame_id + 1, benchmark_total_frames, backend_id, mode_id, transport_id, pipeline_depth])
	return true


## Build the stable runtime headers, omitting unmeasured optional sensor values.
func _request_headers(frame_id: int, lr_size: Vector2i = Vector2i.ZERO, hr_size: Vector2i = Vector2i.ZERO) -> PackedStringArray:
	var deadline_ms := (
		float(maximum_neural_age_frames) * 1000.0
		/ (benchmark_fps if benchmark_mode else 30.0)
	)
	var headers := PackedStringArray([
		"Content-Type: application/octet-stream",
		"X-Upscale-Protocol: %s" % PROTOCOL_ID,
		"X-Run-Id: %s" % run_id,
		"X-Frame-Id: %d" % frame_id,
		"X-Backend-Id: %s" % backend_id,
		"X-Deadline-Ms: %.9f" % deadline_ms,
		"X-GPU-Frame-Ms: %.6f" % current_gpu_frame_ms,
		"X-Deadline-Slack-Ms: %.6f" % maxf(0.0, deadline_ms - current_gpu_frame_ms),
		"X-Temperature-Limit-C: %.3f" % temperature_limit_c,
		"X-Temperature-Critical-C: %.3f" % temperature_critical_c,
		"X-Previous-Frame-Ms: %.6f" % previous_frame_ms,
		"X-Frame-Transport: %s" % transport_id,
	])
	var renderer_metadata := _renderer_metadata()
	headers.append(
		"X-Camera-FOV-Degrees: %.6f"
		% float(renderer_metadata["camera_fov_degrees"])
	)
	headers.append(
		"X-Camera-Pitch-Radians: %.6f"
		% float(renderer_metadata["camera_pitch_radians"])
	)
	headers.append(
		"X-Antialiasing-Mode: %s"
		% str(renderer_metadata["antialiasing_mode"])
	)
	for metadata_key in [
		"thin_geometry_fraction",
		"repeated_patterns_fraction",
		"foliage_fraction",
		"hud_text_fraction",
		"particles_fraction",
		"fences_fraction",
		"reflective_surfaces_fraction",
	]:
		headers.append(
			"X-%s: %.6f"
			% [
				_metadata_header_name(metadata_key),
				float(renderer_metadata[metadata_key]),
			]
		)
	if lr_size != Vector2i.ZERO:
		headers.append("X-LR-Width: %d" % lr_size.x)
		headers.append("X-LR-Height: %d" % lr_size.y)
	if hr_size != Vector2i.ZERO:
		headers.append("X-HR-Width: %d" % hr_size.x)
		headers.append("X-HR-Height: %d" % hr_size.y)
	if not constraint_trace_id.is_empty():
		headers.append("X-Constraint-Trace-Id: %s" % constraint_trace_id)
	if temperature_c != null:
		headers.append("X-Temperature-C: %.3f" % float(temperature_c))
	if observed_power_w != null:
		headers.append("X-Observed-Power-W: %.6f" % float(observed_power_w))
	if power_budget_w != null:
		headers.append("X-Power-Budget-W: %.6f" % float(power_budget_w))
	return headers


## Return renderer-visible information without examining the rendered image.
func _renderer_metadata() -> Dictionary:
	var metadata := {
		"camera_fov_degrees": lr_camera.fov,
		"camera_pitch_radians": lr_camera.rotation.x,
		"antialiasing_mode": "disabled",
		"thin_geometry_fraction": 0.05,
		"repeated_patterns_fraction": 0.10,
		"foliage_fraction": 0.0,
		"hud_text_fraction": 0.0,
		"particles_fraction": 0.0,
		"fences_fraction": 0.05,
		"reflective_surfaces_fraction": 0.0,
		"dynamic_object_fraction": null,
		"disocclusion_fraction": null,
	}
	# The camera follows the authored forward corridor. Reading the next 16
	# two-meter bins approximates the renderer's visible draw-list composition
	# with a fixed upper bound independent of scene object count.
	var camera_bin := int(floor(lr_camera.position.z / 2.0))
	for offset in range(17):
		var bin_index := camera_bin - offset
		if not renderer_metadata_bins.has(bin_index):
			continue
		var bin_z := (float(bin_index) + 0.5) * 2.0
		var depth := maxf(lr_camera.position.z - bin_z, 0.5)
		var tag_weights: Dictionary = renderer_metadata_bins[bin_index]
		for tag_value in tag_weights:
			var field_name := "%s_fraction" % str(tag_value)
			if not metadata.has(field_name):
				continue
			var coverage := clampf(
				float(tag_weights[tag_value]) / (depth * depth),
				0.0,
				0.25,
			)
			metadata[field_name] = minf(
				1.0,
				float(metadata[field_name]) + coverage,
			)
	# The benchmark viewports currently disable MSAA. This field describes the
	# actual LR render path rather than a desired or inferred quality setting.
	return metadata


## Convert snake-case protocol fields to their explicit HTTP spelling.
func _metadata_header_name(field_name: String) -> String:
	var names := {
		"thin_geometry_fraction": "Thin-Geometry-Fraction",
		"repeated_patterns_fraction": "Repeated-Patterns-Fraction",
		"foliage_fraction": "Foliage-Fraction",
		"hud_text_fraction": "HUD-Text-Fraction",
		"particles_fraction": "Particles-Fraction",
		"fences_fraction": "Fences-Fraction",
		"reflective_surfaces_fraction": "Reflective-Surfaces-Fraction",
	}
	return str(names[field_name])


## Load the topology policy shared with the Python reference implementation.
##
## Keeping this as a small JSON artifact makes every threshold inspectable and
## prevents a physical run from silently changing policy between controls.
func _load_npu_topology_policy(path: String) -> bool:
	var policy_file := FileAccess.open(path, FileAccess.READ)
	if policy_file == null:
		push_error("could not open NPU topology policy: %s" % path)
		return false
	var parsed: Variant = JSON.parse_string(policy_file.get_as_text())
	if not parsed is Dictionary:
		push_error("NPU topology policy root must be a dictionary")
		return false
	var candidate: Dictionary = parsed
	if (
		str(candidate.get("artifact", ""))
		!= "rk3576_npu_topology_policy_phase13"
		or str(candidate.get("policy_id", "")) != "deadline_queue_v1"
		or not candidate.get("supported_workloads", []) is Array
		or int(candidate.get("maximum_pending_frames", -1)) < 0
	):
		push_error("NPU topology policy artifact is incompatible")
		return false
	for field_name in [
		"minimum_remaining_slack_ms",
		"fused_slack_ceiling_ms",
		"previous_frame_late_factor",
	]:
		if float(candidate.get(field_name, 0.0)) <= 0.0:
			push_error("NPU topology policy threshold is invalid: %s" % field_name)
			return false
	npu_topology_policy = candidate
	print(
		"GODOT_NPU_TOPOLOGY_POLICY_READY policy=%s workloads=%d"
		% [
			str(npu_topology_policy["policy_id"]),
			npu_topology_policy["supported_workloads"].size(),
		]
	)
	return true


## Load the preregistered age-bounded refresh policy shared with Python tests.
##
## This artifact controls dispatch timing only. It never sees HR pixels and it
## does not revive any frozen quality-selector threshold.
func _load_neural_refresh_policy(path: String) -> bool:
	var policy_file := FileAccess.open(path, FileAccess.READ)
	if policy_file == null:
		push_error("could not open neural refresh policy: %s" % path)
		return false
	var parsed: Variant = JSON.parse_string(policy_file.get_as_text())
	if not parsed is Dictionary:
		push_error("neural refresh policy root must be a dictionary")
		return false
	var candidate: Dictionary = parsed
	if (
		str(candidate.get("artifact", ""))
		!= "rk3576_neural_refresh_policy_paper1_v1"
		or str(candidate.get("policy_id", "")) != "renderer_deadline_refresh_v1"
		or not candidate.get("supported_workloads", []) is Array
		or not candidate.get("renderer_priority_weights", {}) is Dictionary
		or int(candidate.get("maximum_pending_frames", -1)) < 0
		or int(candidate.get("priority_refresh_period_frames", 0)) < 1
	):
		push_error("neural refresh policy artifact is incompatible")
		return false
	var alpha := float(candidate.get("service_ewma_alpha", 0.0))
	var priority_threshold := float(
		candidate.get("renderer_priority_threshold", -1.0)
	)
	if (
		alpha <= 0.0
		or alpha > 1.0
		or priority_threshold < 0.0
		or priority_threshold > 1.0
	):
		push_error("neural refresh EWMA alpha is invalid")
		return false
	for workload_value in candidate["supported_workloads"]:
		if not workload_value is Dictionary:
			push_error("neural refresh workload must be a dictionary")
			return false
		var workload: Dictionary = workload_value
		if (
			str(workload.get("mode_id", "")).is_empty()
			or int(workload.get("target_fps", 0)) <= 0
			or int(workload.get("target_refresh_period_frames", 0)) <= 0
			or int(workload.get("maximum_refresh_age_frames", 0)) <= 0
			or float(workload.get("initial_service_ms", -1.0)) < 0.0
		):
			push_error("neural refresh workload fields are invalid")
			return false
	neural_refresh_policy = candidate
	print(
		"GODOT_NEURAL_REFRESH_POLICY_READY policy=%s workloads=%d"
		% [
			str(neural_refresh_policy["policy_id"]),
			neural_refresh_policy["supported_workloads"].size(),
		]
	)
	return true


## Find the exact mode/FPS row rather than borrowing another workload's timing.
func _neural_refresh_workload() -> Dictionary:
	var target_fps := int(round(benchmark_fps if benchmark_mode else 30.0))
	for workload_value in neural_refresh_policy["supported_workloads"]:
		var workload: Dictionary = workload_value
		if (
			str(workload["mode_id"]) == mode_id
			and int(workload["target_fps"]) == target_fps
		):
			return workload
	return {}


## Admit only due work that fits the bounded neural-refresh age.
##
## `predicted_same_frame` is telemetry, not an admission shortcut. A request
## may satisfy the looser refresh-age contract while missing the strict one-
## frame deadline, and the final report keeps those outcomes separate.
func _predict_neural_refresh(frame_id: int) -> Dictionary:
	var started_usec := Time.get_ticks_usec()
	var target_fps := int(round(benchmark_fps if benchmark_mode else 30.0))
	var frame_deadline_ms := 1000.0 / float(target_fps)
	var workload := _neural_refresh_workload()
	if workload.is_empty():
		return {
			"action": "bypass",
			"reason": "unsupported_workload",
			"frame_deadline_ms": frame_deadline_ms,
			"selector_ms": (Time.get_ticks_usec() - started_usec) / 1000.0,
		}
	var maximum_age_frames := int(workload["maximum_refresh_age_frames"])
	var refresh_deadline_ms := frame_deadline_ms * maximum_age_frames
	var frames_since_commit := (
		maximum_age_frames
		if last_committed_neural_frame < 0
		else maxi(0, frame_id - last_committed_neural_frame)
	)
	var target_period := int(workload["target_refresh_period_frames"])
	var frames_since_submit := (
		target_period
		if last_submitted_neural_frame < 0
		else maxi(0, frame_id - last_submitted_neural_frame)
	)
	# Renderer-owned draw-list metadata raises refresh priority without a CPU
	# image scan. The bounded weighted mean is mirrored in the Python contract.
	var renderer_metadata := _renderer_metadata()
	var priority_weights: Dictionary = neural_refresh_policy[
		"renderer_priority_weights"
	]
	var priority_weighted_sum := 0.0
	var priority_weight_total := 0.0
	for field_value in priority_weights:
		var field_name := str(field_value)
		var weight := maxf(0.0, float(priority_weights[field_value]))
		var value := clampf(float(renderer_metadata.get(field_name, 0.0)), 0.0, 1.0)
		priority_weighted_sum += weight * value
		priority_weight_total += weight
	var renderer_priority_score := (
		priority_weighted_sum / maxf(priority_weight_total, 0.000001)
	)
	var renderer_priority := (
		renderer_priority_score
		>= float(neural_refresh_policy["renderer_priority_threshold"])
	)
	var effective_refresh_period := (
		int(neural_refresh_policy["priority_refresh_period_frames"])
		if renderer_priority
		else target_period
	)
	var service_ms := (
		float(workload["initial_service_ms"])
		if neural_service_ewma_ms == null
		else float(neural_service_ewma_ms)
	)
	var predicted_age_ms := (
		current_gpu_frame_ms
		+ service_ms
		+ float(neural_refresh_policy["fixed_completion_overhead_ms"])
		+ float(neural_refresh_policy["safety_margin_ms"])
	)
	var pending_frames := benchmark_pending.size()
	var action := "submit"
	var reason := "refresh_due_capacity_available"
	if (
		temperature_c != null
		and float(temperature_c)
		>= float(neural_refresh_policy["temperature_limit_c"])
	):
		action = "bypass"
		reason = "temperature_limit"
	elif pending_frames > int(neural_refresh_policy["maximum_pending_frames"]):
		action = "bypass"
		reason = "latest_frame_only_context_busy"
	elif frames_since_submit < effective_refresh_period:
		action = "bypass"
		reason = "refresh_period_not_due"
	elif predicted_age_ms > refresh_deadline_ms:
		action = "bypass"
		reason = "predicted_refresh_would_be_stale"
	return {
		"action": action,
		"reason": reason,
		"frame_deadline_ms": frame_deadline_ms,
		"refresh_deadline_ms": refresh_deadline_ms,
		"maximum_refresh_age_frames": maximum_age_frames,
		"target_refresh_period_frames": target_period,
		"effective_refresh_period_frames": effective_refresh_period,
		"renderer_priority_score": renderer_priority_score,
		"renderer_priority": renderer_priority,
		"frames_since_neural_commit": frames_since_commit,
		"frames_since_neural_submit": frames_since_submit,
		"predicted_service_ms": service_ms,
		"predicted_completion_age_ms": predicted_age_ms,
		"predicted_same_frame": predicted_age_ms <= frame_deadline_ms,
		"pending_frames": pending_frames,
		"selector_ms": (Time.get_ticks_usec() - started_usec) / 1000.0,
	}


## Choose split, fused, or bypass before reserving any physical NPU context.
##
## This mirrors `src/runtime/npu_topology_policy.py`. It uses only timing and
## queue state available before dispatch; no HR pixel or future outcome enters
## the decision.
func _predict_npu_topology() -> Dictionary:
	var started_usec := Time.get_ticks_usec()
	var target_fps := int(round(benchmark_fps if benchmark_mode else 30.0))
	var deadline_ms := 1000.0 / float(target_fps)
	var remaining_slack_ms := maxf(0.0, deadline_ms - current_gpu_frame_ms)
	var pending_frames := benchmark_pending.size()
	var supported := false
	for workload in npu_topology_policy["supported_workloads"]:
		if (
			str(workload["mode_id"]) == mode_id
			and int(workload["target_fps"]) == target_fps
		):
			supported = true
			break
	var action := ""
	var reason := ""
	if not supported:
		action = str(npu_topology_policy["unsupported_workload_action"])
		reason = "unsupported_workload_no_oracle_headroom"
	elif (
		remaining_slack_ms
		< float(npu_topology_policy["minimum_remaining_slack_ms"])
	):
		action = "bypass"
		reason = "insufficient_remaining_slack"
	elif (
		previous_frame_ms
		> deadline_ms * float(npu_topology_policy["previous_frame_late_factor"])
	):
		action = "bypass"
		reason = "previous_frame_far_beyond_deadline"
	elif pending_frames > int(npu_topology_policy["maximum_pending_frames"]):
		action = "bypass"
		reason = "bounded_queue_full"
	elif pending_frames == 1:
		action = "split"
		reason = "fill_second_independent_core"
	elif (
		remaining_slack_ms
		<= float(npu_topology_policy["fused_slack_ceiling_ms"])
	):
		action = "fused"
		reason = "tight_slack_prefers_fused_latency"
	else:
		action = "split"
		reason = "ample_slack_prefers_split_capacity"
	return {
		"action": action,
		"reason": reason,
		"deadline_ms": deadline_ms,
		"remaining_slack_ms": remaining_slack_ms,
		"pending_frames": pending_frames,
		"selector_ms": (Time.get_ticks_usec() - started_usec) / 1000.0,
	}


## Load the same portable artifact used by the Python admission runtime.
func _load_metadata_selector(path: String) -> bool:
	var selector_file := FileAccess.open(path, FileAccess.READ)
	if selector_file == null:
		push_error("could not open metadata selector: %s" % path)
		return false
	var parsed: Variant = JSON.parse_string(selector_file.get_as_text())
	if not parsed is Dictionary:
		push_error("metadata selector root must be a dictionary")
		return false
	var candidate: Dictionary = parsed
	if (
		str(candidate.get("artifact", ""))
		!= "renderer_metadata_admission_phase12"
		or not ["decision_tree", "tiny_mlp"].has(
			str(candidate.get("model_type", ""))
		)
		or not candidate.get("method_ids", []) is Array
		or not candidate.get("feature_names", []) is Array
	):
		push_error("metadata selector artifact is incompatible")
		return false
	if candidate["feature_names"].size() != 14:
		push_error("metadata selector feature count changed")
		return false
	metadata_selector = candidate
	print(
		"GODOT_METADATA_SELECTOR_READY model=%s features=%d"
		% [
			str(metadata_selector["model_type"]),
			metadata_selector["feature_names"].size(),
		]
	)
	return true


## Convert current renderer observations to the frozen normalized feature row.
func _metadata_selector_features() -> Array:
	var metadata := _renderer_metadata()
	var antialiasing_samples := {
		"disabled": 0.0,
		"fxaa": 1.0,
		"msaa_2x": 2.0,
		"msaa_4x": 4.0,
		"msaa_8x": 8.0,
	}
	var dynamic_available := (
		metadata.get("dynamic_object_fraction") != null
	)
	var disocclusion_available := (
		metadata.get("disocclusion_fraction") != null
	)
	var raw := [
		float(metadata["camera_fov_degrees"]) / 180.0,
		absf(float(metadata["camera_pitch_radians"])) / PI,
		float(
			antialiasing_samples.get(
				str(metadata["antialiasing_mode"]),
				0.0,
			)
		) / 8.0,
		float(metadata["thin_geometry_fraction"]),
		float(metadata["repeated_patterns_fraction"]),
		float(metadata["foliage_fraction"]),
		float(metadata["hud_text_fraction"]),
		float(metadata["particles_fraction"]),
		float(metadata["fences_fraction"]),
		float(metadata["reflective_surfaces_fraction"]),
		(
			float(metadata["dynamic_object_fraction"])
			if dynamic_available
			else 0.0
		),
		(
			float(metadata["disocclusion_fraction"])
			if disocclusion_available
			else 0.0
		),
		1.0 if dynamic_available else 0.0,
		1.0 if disocclusion_available else 0.0,
	]
	var mean: Array = metadata_selector["feature_mean"]
	var deviation: Array = metadata_selector["feature_std"]
	var normalized: Array = []
	for index in range(raw.size()):
		normalized.append(
			(float(raw[index]) - float(mean[index]))
			/ float(deviation[index])
		)
	return normalized


## Execute the frozen tiny model without touching LR pixels or crossing process.
func _metadata_model_probabilities(features: Array) -> Array:
	var model: Dictionary = metadata_selector["model"]
	if str(metadata_selector["model_type"]) == "decision_tree":
		var nodes: Array = model["nodes"]
		var node_index := 0
		while true:
			var node: Dictionary = nodes[node_index]
			if bool(node["leaf"]):
				var leaf: Array = node["probabilities"]
				var leaf_sum := 0.0
				for value in leaf:
					leaf_sum += float(value)
				var normalized_leaf: Array = []
				for value in leaf:
					normalized_leaf.append(float(value) / leaf_sum)
				return normalized_leaf
			var feature_index := int(node["feature_index"])
			node_index = int(
				node["left"]
				if float(features[feature_index]) <= float(node["threshold"])
				else node["right"]
			)

	var output := features.duplicate()
	var layers: Array = model["layers"]
	for layer_index in range(layers.size()):
		var layer: Dictionary = layers[layer_index]
		var weights: Array = layer["weight"]
		var biases: Array = layer["bias"]
		var next_output: Array = []
		for output_index in range(weights.size()):
			var total := float(biases[output_index])
			var row: Array = weights[output_index]
			for input_index in range(row.size()):
				total += float(row[input_index]) * float(output[input_index])
			if layer_index + 1 < layers.size():
				total = maxf(0.0, total)
			next_output.append(total)
		output = next_output
	var maximum := -INF
	for value in output:
		maximum = maxf(maximum, float(value))
	var exponentials: Array = []
	var exponential_sum := 0.0
	for value in output:
		var exponential := exp(
			(float(value) - maximum)
			/ float(metadata_selector["calibration_temperature"])
		)
		exponentials.append(exponential)
		exponential_sum += exponential
	for index in range(exponentials.size()):
		exponentials[index] = float(exponentials[index]) / exponential_sum
	return exponentials


## Select one classical bypass or complete NPU graph before slot reservation.
func _predict_metadata_route() -> Dictionary:
	var started_usec := Time.get_ticks_usec()
	var features := _metadata_selector_features()
	var features_complete_usec := Time.get_ticks_usec()
	var probabilities := _metadata_model_probabilities(features)
	var model_complete_usec := Time.get_ticks_usec()
	var selected_index := 0
	for index in range(1, probabilities.size()):
		if float(probabilities[index]) > float(probabilities[selected_index]):
			selected_index = index
	var methods: Array = metadata_selector["method_ids"]
	var raw_method := str(methods[selected_index])
	var confidence := float(probabilities[selected_index])
	var selected_method := (
		str(metadata_selector["fallback_method"])
		if confidence < float(metadata_selector["confidence_threshold"])
		else raw_method
	)
	var reasons: Array = ["renderer_metadata"]
	var deadline_ms := (
		float(maximum_neural_age_frames) * 1000.0
		/ (benchmark_fps if benchmark_mode else 30.0)
	)
	# Deadline and thermal pressure must bypass work immediately. Power is not
	# considered until an external measurement source is available.
	if (
		current_gpu_frame_ms >= deadline_ms
		or previous_frame_ms > deadline_ms
	):
		selected_method = "bicubic"
		reasons.append("deadline_pressure")
	if (
		temperature_c != null
		and float(temperature_c) >= temperature_limit_c
	):
		selected_method = "bicubic"
		reasons.append("temperature_pressure")
	return {
		"method_id": selected_method,
		"raw_method_id": raw_method,
		"confidence": confidence,
		"probabilities": probabilities,
		"selector_ms": (
			Time.get_ticks_usec() - started_usec
		) / 1000.0,
		"metadata_features_ms": (
			features_complete_usec - started_usec
		) / 1000.0,
		"metadata_model_ms": (
			model_complete_usec - features_complete_usec
		) / 1000.0,
		"control_reasons": reasons,
	}


## Encode either compatibility PNG framing or exact copied RGB8 frame bytes.
func _pack_request_body(lr_image: Image, hr_image: Image) -> PackedByteArray:
	if (
		transport_id == "raw_rgb"
		or transport_id == "persistent_tcp_rgb"
		or transport_id == "native_dmabuf"
		or transport_id == "direct_dmabuf"
	):
		var lr_rgb := lr_image.duplicate()
		lr_rgb.convert(Image.FORMAT_RGB8)
		var raw_body: PackedByteArray = lr_rgb.get_data()
		if transfer_reference:
			var hr_rgb := hr_image.duplicate()
			hr_rgb.convert(Image.FORMAT_RGB8)
			raw_body.append_array(hr_rgb.get_data())
		return raw_body
	var lr_png := lr_image.save_png_to_buffer()
	var hr_png := hr_image.save_png_to_buffer() if transfer_reference else PackedByteArray()
	var body := PackedByteArray()
	var length := lr_png.size()
	body.append((length >> 24) & 0xFF)
	body.append((length >> 16) & 0xFF)
	body.append((length >> 8) & 0xFF)
	body.append(length & 0xFF)
	body.append_array(lr_png)
	body.append_array(hr_png)
	return body


## Create the target-only in-process NPU bridge dynamically.
##
## Dynamic ClassDB construction keeps the desktop benchmark loadable when the
## ARM64 extension is absent. On RK3576, two native contexts and finite
## DMA-BUF rings replace the Python companion and socket-owned RGB payloads.
func _initialize_native_bridge() -> bool:
	if not ClassDB.class_exists("RK3576NativeBridge"):
		push_error(
			"RK3576NativeBridge is unavailable; build native_bridge first"
		)
		return false
	native_bridge = ClassDB.instantiate("RK3576NativeBridge")
	if native_bridge == null:
		push_error("could not instantiate RK3576NativeBridge")
		return false
	var mode: Dictionary = MODES[mode_id]
	var configuration: Dictionary = native_bridge.configure(
		native_bridge_model_path,
		int(mode["lr"].x),
		int(mode["lr"].y),
		native_bridge_slots_per_core,
		native_bridge_core_profile,
	)
	if not bool(configuration.get("ok", false)):
		push_error(
			"native bridge configuration failed: %s"
			% str(configuration.get("error", "unknown"))
		)
		return false
	native_bridge_worker_count = int(configuration["worker_count"])
	# EGL contexts are thread-local, so the native bridge must inspect the
	# context from Godot's render thread rather than trusting a shell probe.
	native_bridge.reset_render_probe()
	RenderingServer.call_on_render_thread(native_bridge.probe_render_context)
	var probe_deadline := Time.get_ticks_msec() + 5000
	var bridge_status: Dictionary = native_bridge.status()
	while (
		not bool(bridge_status.get("render_probe_complete", false))
		and Time.get_ticks_msec() < probe_deadline
	):
		await get_tree().process_frame
		bridge_status = native_bridge.status()
	if not bool(bridge_status.get("render_probe_compatible", false)):
		push_error(
			"native bridge EGL probe failed: %s"
			% str(bridge_status.get("render_probe_error", "timed out"))
		)
		return false
	print(
		"GODOT_NATIVE_DMABUF_READY method=%s profile=%s workers=%d slots_per_core=%d renderer=%s"
		% [
			native_bridge_method,
			native_bridge_core_profile,
			int(configuration["worker_count"]),
			int(configuration["slot_count_per_core"]),
			str(bridge_status.get("gl_renderer", "unknown")),
		]
	)
	if transport_id == "direct_dmabuf":
		_create_direct_output_textures(mode["hr"])
		if not await _warmup_direct_bridge():
			return false
	return true


## Allocate one Godot-owned HR texture per native ring slot.
##
## The extension renders directly into these textures. Their one-time zero fill
## is initialization, not per-frame materialization or upload.
func _create_direct_output_textures(output_size: Vector2i) -> void:
	direct_output_textures.clear()
	var total_slots := native_bridge_slots_per_core * native_bridge_worker_count
	for _slot_index in range(total_slots):
		var blank_image := Image.create(
			output_size.x,
			output_size.y,
			false,
			Image.FORMAT_RGBA8,
		)
		blank_image.fill(Color.BLACK)
		direct_output_textures.append(
			ImageTexture.create_from_image(blank_image)
		)


## Touch every direct ring slot before measurement.
##
## EGLImage import, shader compilation, RGA setup, and RKNN caches belong to
## warmup rather than the first measured frame. The same deterministic LR
## texture is reused because these outputs are intentionally discarded.
func _warmup_direct_bridge() -> bool:
	await RenderingServer.frame_post_draw
	for warmup_index in range(
		native_bridge_slots_per_core * native_bridge_worker_count
	):
		var topology_hint := "fixed"
		if native_bridge_core_profile == "preloaded_split_fused_012":
			topology_hint = (
				"split"
				if warmup_index < native_bridge_slots_per_core * 2
				else "fused"
			)
		var reservation: Dictionary = native_bridge.reserve_direct_frame(
			topology_hint
		)
		if not bool(reservation.get("ok", false)):
			push_error(
				"direct bridge warmup reservation failed: %s"
				% str(reservation.get("error", "unknown"))
			)
			return false
		var frame_token := int(reservation["frame_token"])
		RenderingServer.call_on_render_thread(
			native_bridge.capture_direct_frame.bind(
				frame_token,
				lr_viewport.get_viewport_rid(),
			)
		)
		var state: Dictionary = native_bridge.direct_frame_status(frame_token)
		while (
			bool(state.get("ok", false))
			and not bool(state.get("capture_complete", false))
		):
			await get_tree().process_frame
			state = native_bridge.direct_frame_status(frame_token)
		if not bool(state.get("ok", false)):
			push_error(
				"direct bridge warmup capture failed: %s"
				% str(state.get("error", "unknown"))
			)
			return false
		var inference: Dictionary = native_bridge.upscale_direct_frame(
			frame_token
		)
		if not bool(inference.get("ok", false)):
			push_error(
				"direct bridge warmup inference failed: %s"
				% str(inference.get("error", "unknown"))
			)
			return false
		var texture_index := int(reservation["output_texture_index"])
		RenderingServer.call_on_render_thread(
			native_bridge.compose_direct_frame.bind(
				frame_token,
				direct_output_textures[texture_index].get_rid(),
			)
		)
		state = native_bridge.direct_frame_status(frame_token)
		while (
			bool(state.get("ok", false))
			and not bool(state.get("composition_complete", false))
		):
			await get_tree().process_frame
			state = native_bridge.direct_frame_status(frame_token)
		var consumed: Dictionary = native_bridge.consume_direct_frame(
			frame_token
		)
		if not bool(consumed.get("ok", false)):
			push_error(
				"direct bridge warmup composition failed: %s"
				% str(consumed.get("error", "unknown"))
			)
			return false
	print(
		"GODOT_DIRECT_DMABUF_WARM slots=%d"
		% (native_bridge_slots_per_core * native_bridge_worker_count)
	)
	return true


## Reserve a native slot and schedule a render-thread GPU-to-DMA-BUF blit.
##
## The source is Godot's native GLES texture handle. No `get_image`,
## `PackedByteArray`, or CPU texture upload participates in this path.
func _begin_direct_bridge_request(
	frame_id: int,
	context: Dictionary,
) -> Error:
	if native_bridge == null:
		return ERR_UNCONFIGURED
	var topology_decision := {
		"action": "fixed",
		"reason": "fixed_topology_control",
		"remaining_slack_ms": (
			float(maximum_neural_age_frames) * 1000.0 / benchmark_fps
			- current_gpu_frame_ms
		),
		"pending_frames": benchmark_pending.size(),
		"selector_ms": 0.0,
	}
	var topology_hint := "fixed"
	if native_bridge_core_profile == "preloaded_split_fused_012":
		topology_decision = _predict_npu_topology()
		topology_hint = str(topology_decision["action"])
		context["npu_topology_decision"] = topology_decision
		if topology_hint == "bypass":
			return _complete_topology_bypass(
				frame_id,
				context,
				topology_decision,
				"topology_policy_bypass",
			)
	var reservation: Dictionary = native_bridge.reserve_direct_frame(
		topology_hint
	)
	if not bool(reservation.get("ok", false)):
		if (
			native_bridge_core_profile == "preloaded_split_fused_012"
			and bool(reservation.get("busy", false))
		):
			topology_decision["bridge_busy_reason"] = str(
				reservation.get("busy_reason", "unknown")
			)
			context["npu_topology_decision"] = topology_decision
			return _complete_topology_bypass(
				frame_id,
				context,
				topology_decision,
				"topology_busy_bypass",
			)
		return ERR_BUSY
	var texture_index := int(reservation["output_texture_index"])
	if texture_index < 0 or texture_index >= direct_output_textures.size():
		return ERR_INVALID_DATA
	var frame_token := int(reservation["frame_token"])
	context["roundtrip_start_usec"] = Time.get_ticks_usec()
	context["direct_frame_token"] = frame_token
	context["direct_output_texture_index"] = texture_index
	context["direct_worker_id"] = str(reservation["worker_id"])
	context["direct_slot_index"] = int(reservation["slot_index"])
	context["direct_core_mask"] = int(reservation["core_mask"])
	context["direct_topology_mode"] = str(reservation["topology_mode"])
	context["npu_topology_decision"] = topology_decision
	last_submitted_neural_frame = frame_id
	context["request_payload_bytes"] = 0
	benchmark_pending[frame_id] = context
	RenderingServer.call_on_render_thread(
		native_bridge.capture_direct_frame.bind(
			frame_token,
			lr_viewport.get_viewport_rid(),
		)
	)
	WorkerThreadPool.add_task(
		_direct_bridge_worker.bind(frame_id, frame_token),
		true,
		"Phase7DirectDmaBuf%d" % frame_id,
	)
	return OK


## Complete one age/deadline rejection with the current GPU classical frame.
##
## This path performs no NPU reservation. It therefore represents physically
## avoided work rather than a result that was computed and discarded later.
func _complete_refresh_bypass(
	frame_id: int,
	context: Dictionary,
	decision: Dictionary,
) -> Error:
	var route: Dictionary = context.get("metadata_decision", {})
	context["roundtrip_ms"] = 0.0
	context["response_received_usec"] = Time.get_ticks_usec()
	context["response_payload_bytes"] = 0
	context["response"] = {
		"valid": true,
		"image": null,
		"metadata": {
			"backend_id": "heterogeneous_progressive",
			"route_status": "refresh_policy_bypass",
			"selected_method_id": "bicubic",
			"raw_method_id": str(
				route.get("raw_method_id", native_bridge_method)
			),
			"selector_confidence": float(route.get("confidence", 1.0)),
			"selector_ms": float(route.get("selector_ms", 0.0)),
			"metadata_features_ms": float(
				route.get("metadata_features_ms", 0.0)
			),
			"metadata_model_ms": float(route.get("metadata_model_ms", 0.0)),
			"renderer_metadata_used": true,
			"control_reasons": (
				route.get("control_reasons", []).duplicate()
				+ [str(decision["reason"])]
			),
			"npu_worker_id": null,
			"npu_queue_depth": int(decision.get("pending_frames", 0)),
			"npu_queue_limit": pipeline_depth,
			"backend_queue_wait_ms": 0.0,
			"backend_queue_service_ms": 0.0,
			"backend_inference_ms": 0.0,
			"backend_materialize_ms": 0.0,
			"host_pixel_bytes_per_frame": 0,
			"refresh_policy_action": "bypass",
			"refresh_policy_reason": str(decision["reason"]),
			"refresh_policy_selector_ms": float(decision["selector_ms"]),
			"refresh_predicted_service_ms": float(
				decision.get("predicted_service_ms", 0.0)
			),
			"refresh_predicted_completion_age_ms": float(
				decision.get("predicted_completion_age_ms", 0.0)
			),
			"refresh_predicted_same_frame": bool(
				decision.get("predicted_same_frame", false)
			),
			"refresh_frames_since_commit": int(
				decision.get("frames_since_neural_commit", -1)
			),
			"refresh_renderer_priority_score": float(
				decision.get("renderer_priority_score", 0.0)
			),
			"refresh_renderer_priority": bool(
				decision.get("renderer_priority", false)
			),
			"refresh_effective_period_frames": int(
				decision.get("effective_refresh_period_frames", 0)
			),
		},
	}
	benchmark_completed[frame_id] = context
	return OK


## Complete one pre-dispatch topology rejection with the existing GPU fallback.
##
## This is a successful display result and a real NPU bypass, not a transport
## failure. Keeping it in the normal telemetry stream makes skipped work and
## timely neural delivery directly comparable.
func _complete_topology_bypass(
	frame_id: int,
	context: Dictionary,
	decision: Dictionary,
	route_status: String,
) -> Error:
	var route: Dictionary = context.get("metadata_decision", {})
	context["roundtrip_ms"] = 0.0
	context["response_received_usec"] = Time.get_ticks_usec()
	context["response_payload_bytes"] = 0
	context["response"] = {
		"valid": true,
		"image": null,
		"metadata": {
			"backend_id": "heterogeneous_progressive",
			"route_status": route_status,
			"selected_method_id": "bicubic",
			"raw_method_id": str(
				route.get("raw_method_id", native_bridge_method)
			),
			"selector_confidence": float(route.get("confidence", 1.0)),
			"selector_ms": float(route.get("selector_ms", 0.0)),
			"metadata_features_ms": float(
				route.get("metadata_features_ms", 0.0)
			),
			"metadata_model_ms": float(route.get("metadata_model_ms", 0.0)),
			"renderer_metadata_used": not route.is_empty(),
			"control_reasons": (
				route.get("control_reasons", []).duplicate()
				+ [str(decision["reason"])]
			),
			"npu_worker_id": null,
			"npu_queue_depth": int(decision["pending_frames"]),
			"npu_queue_limit": pipeline_depth,
			"backend_queue_wait_ms": 0.0,
			"backend_queue_service_ms": 0.0,
			"backend_inference_ms": 0.0,
			"backend_materialize_ms": 0.0,
			"host_pixel_bytes_per_frame": 0,
			"npu_topology_mode": "bypass",
			"npu_topology_reason": str(decision["reason"]),
			"npu_topology_selector_ms": float(decision["selector_ms"]),
			"npu_topology_remaining_slack_ms": float(
				decision["remaining_slack_ms"]
			),
			"npu_core_mask": 0,
		},
	}
	benchmark_completed[frame_id] = context
	return OK


## Wait for the short render-thread capture, then execute RGA and RKNN.
##
## Polling occurs on a finite Godot worker, never on the render or main thread.
func _direct_bridge_worker(frame_id: int, frame_token: int) -> void:
	var deadline_usec := Time.get_ticks_usec() + 5000000
	var state: Dictionary = native_bridge.direct_frame_status(frame_token)
	while (
		bool(state.get("ok", false))
		and not bool(state.get("capture_complete", false))
		and Time.get_ticks_usec() < deadline_usec
	):
		OS.delay_usec(100)
		state = native_bridge.direct_frame_status(frame_token)
	if not bool(state.get("ok", false)):
		call_deferred(
			"_complete_direct_bridge_response",
			frame_id,
			state,
			Time.get_ticks_usec(),
		)
		return
	if not bool(state.get("capture_complete", false)):
		call_deferred(
			"_complete_direct_bridge_response",
			frame_id,
			{"ok": false, "error": "direct GPU capture timed out"},
			Time.get_ticks_usec(),
		)
		return
	var inference: Dictionary = native_bridge.upscale_direct_frame(frame_token)
	call_deferred(
		"_begin_direct_composition",
		frame_id,
		frame_token,
		inference,
	)


## Schedule the raw residual composition into the frame's Godot-owned texture.
func _begin_direct_composition(
	frame_id: int,
	frame_token: int,
	inference: Dictionary,
) -> void:
	if not bool(inference.get("ok", false)):
		_complete_direct_bridge_response(
			frame_id,
			inference,
			Time.get_ticks_usec(),
		)
		return
	var context: Dictionary = benchmark_pending.get(frame_id, {})
	if direct_validation_readback:
		var validation: Dictionary = native_bridge.read_direct_validation(
			frame_token
		)
		if not bool(validation.get("ok", false)):
			_complete_direct_bridge_response(
				frame_id,
				validation,
				Time.get_ticks_usec(),
			)
			return
		context["direct_validation_input"] = validation["input_rgb"]
		context["direct_validation_residual"] = validation["residual_rgb"]
	var texture_index := int(context.get("direct_output_texture_index", -1))
	if texture_index < 0 or texture_index >= direct_output_textures.size():
		_complete_direct_bridge_response(
			frame_id,
			{"ok": false, "error": "direct output texture index is invalid"},
			Time.get_ticks_usec(),
		)
		return
	context["direct_inference"] = inference
	benchmark_pending[frame_id] = context
	RenderingServer.call_on_render_thread(
		native_bridge.compose_direct_frame.bind(
			frame_token,
			direct_output_textures[texture_index].get_rid(),
		)
	)
	WorkerThreadPool.add_task(
		_direct_composition_wait_worker.bind(frame_id, frame_token),
		true,
		"Phase7DirectCompose%d" % frame_id,
	)


## Wait off-thread until the GPU has completed and released the native slot.
func _direct_composition_wait_worker(
	frame_id: int,
	frame_token: int,
) -> void:
	var deadline_usec := Time.get_ticks_usec() + 5000000
	var state: Dictionary = native_bridge.direct_frame_status(frame_token)
	while (
		bool(state.get("ok", false))
		and not bool(state.get("composition_complete", false))
		and Time.get_ticks_usec() < deadline_usec
	):
		OS.delay_usec(100)
		state = native_bridge.direct_frame_status(frame_token)
	var result: Dictionary
	if not bool(state.get("ok", false)):
		result = native_bridge.consume_direct_frame(frame_token)
	elif not bool(state.get("composition_complete", false)):
		result = native_bridge.consume_direct_frame(frame_token)
		result["ok"] = false
		result["error"] = "direct GPU composition timed out"
	else:
		# Keep the slot and output texture reserved until the replay-ordered
		# recorder has presented this exact frame.
		result = state
	call_deferred(
		"_complete_direct_bridge_response",
		frame_id,
		result,
		Time.get_ticks_usec(),
	)


## Convert one payload-free direct result into the common telemetry contract.
func _complete_direct_bridge_response(
	frame_id: int,
	result: Dictionary,
	received_usec: int,
) -> void:
	var context: Dictionary = benchmark_pending.get(frame_id, {})
	benchmark_pending.erase(frame_id)
	context["roundtrip_ms"] = (
		received_usec
		- int(context.get("roundtrip_start_usec", received_usec))
	) / 1000.0
	context["response_received_usec"] = received_usec
	context["response_payload_bytes"] = 0
	if not bool(result.get("ok", false)):
		context["response"] = {
			"valid": false,
			"error": str(result.get("error", "direct bridge failed")),
		}
	else:
		var texture_index := int(context["direct_output_texture_index"])
		var route: Dictionary = context.get("metadata_decision", {})
		var topology: Dictionary = context.get("npu_topology_decision", {})
		var refresh: Dictionary = context.get("neural_refresh_decision", {})
		var validation_lr_image: Image = null
		var validation_residual_image: Image = null
		if direct_validation_readback:
			var lr_size: Vector2i = MODES[mode_id]["lr"]
			var hr_size: Vector2i = MODES[mode_id]["hr"]
			validation_lr_image = Image.create_from_data(
				lr_size.x,
				lr_size.y,
				false,
				Image.FORMAT_RGB8,
				context["direct_validation_input"],
			)
			validation_residual_image = Image.create_from_data(
				hr_size.x,
				hr_size.y,
				false,
				Image.FORMAT_RGB8,
				context["direct_validation_residual"],
			)
		context["response"] = {
			"valid": true,
			"image": null,
			"texture": direct_output_textures[texture_index],
			"validation_lr_image": validation_lr_image,
			"validation_residual_image": validation_residual_image,
			"metadata": {
				"backend_id": "heterogeneous_progressive",
				"has_neural_image": true,
				"route_status": "accepted_neural",
				"selected_method_id": str(
					route.get("method_id", native_bridge_method)
				),
				"raw_method_id": str(
					route.get("raw_method_id", native_bridge_method)
				),
				"selector_confidence": float(
					route.get("confidence", 1.0)
				),
				"selector_ms": float(route.get("selector_ms", 0.0)),
				"metadata_features_ms": float(
					route.get("metadata_features_ms", 0.0)
				),
				"metadata_model_ms": float(
					route.get("metadata_model_ms", 0.0)
				),
				"renderer_metadata_used": not route.is_empty(),
				"control_reasons": route.get(
					"control_reasons",
					["forced_neural_control"],
				),
				"upgraded_to_configured_graph": bool(
					route.get("upgraded_to_configured_graph", false)
				),
				"npu_worker_id": str(result["worker_id"]),
				"npu_queue_depth": int(
					topology.get("pending_frames", 0)
				),
				"npu_queue_limit": pipeline_depth,
				"backend_queue_wait_ms": 0.0,
				"backend_queue_service_ms": float(context["roundtrip_ms"]),
				"backend_inference_ms": float(result["npu_inference_ms"]),
				"backend_materialize_ms": 0.0,
				"backend_rga_resize_ms": 0.0,
				"backend_residual_pack_ms": float(
					result.get("residual_publish_ms", 0.0)
				),
				"backend_native_total_ms": float(result["native_total_ms"]),
				"backend_gpu_capture_ms": float(result["gpu_capture_ms"]),
				"backend_rga_input_convert_ms": float(result["rga_input_convert_ms"]),
				"backend_gpu_compose_ms": float(result["gpu_compose_ms"]),
				"neural_payload_kind": "direct_dmabuf_fused_texture",
				"residual_scale": float(result["output_scale"]),
				"residual_zero_point": int(result["output_zero_point"]),
				"dmabuf_slot_index": int(result["slot_index"]),
				"dmabuf_sequence_id": int(result["sequence_id"]),
				"direct_frame_token": int(context["direct_frame_token"]),
				"reconstruction_backend": "godot_egl_dmabuf_rknn_gles",
				"host_pixel_bytes_per_frame": 0,
				"npu_topology_mode": str(
					result.get(
						"topology_mode",
						context.get("direct_topology_mode", "fixed"),
					)
				),
				"npu_topology_reason": str(
					topology.get("reason", "fixed_topology_control")
				),
				"npu_topology_selector_ms": float(
					topology.get("selector_ms", 0.0)
				),
				"npu_topology_remaining_slack_ms": float(
					topology.get("remaining_slack_ms", 0.0)
				),
				"npu_core_mask": int(
					result.get(
						"core_mask",
						context.get("direct_core_mask", 0),
					)
				),
				"refresh_policy_action": str(
					refresh.get("action", "disabled")
				),
				"refresh_policy_reason": str(
					refresh.get("reason", "disabled_control")
				),
				"refresh_policy_selector_ms": float(
					refresh.get("selector_ms", 0.0)
				),
				"refresh_predicted_service_ms": float(
					refresh.get("predicted_service_ms", 0.0)
				),
				"refresh_predicted_completion_age_ms": float(
					refresh.get("predicted_completion_age_ms", 0.0)
				),
				"refresh_predicted_same_frame": bool(
					refresh.get("predicted_same_frame", false)
				),
				"refresh_frames_since_commit": int(
					refresh.get("frames_since_neural_commit", -1)
				),
				"refresh_renderer_priority_score": float(
					refresh.get("renderer_priority_score", 0.0)
				),
				"refresh_renderer_priority": bool(
					refresh.get("renderer_priority", false)
				),
				"refresh_effective_period_frames": int(
					refresh.get("effective_refresh_period_frames", 0)
				),
			},
		}
	benchmark_completed[frame_id] = context
	benchmark_response_ready.emit(frame_id)


## Submit one LR byte array directly to the in-process ARM64 extension.
##
## WorkerThreadPool keeps both NPU contexts busy while the main thread
## continues rendering. The returned PackedByteArray still represents one
## final host/GPU upload; the Python process and TCP copies are gone.
func _begin_native_bridge_request(
	frame_id: int,
	body: PackedByteArray,
	context: Dictionary,
) -> Error:
	if native_bridge == null:
		return ERR_UNCONFIGURED
	context["roundtrip_start_usec"] = Time.get_ticks_usec()
	benchmark_pending[frame_id] = context
	WorkerThreadPool.add_task(
		_native_bridge_worker.bind(frame_id, body),
		true,
		"Phase7NativeDmaBuf%d" % frame_id,
	)
	return OK


## Execute one complete native bridge operation away from Godot's render loop.
func _native_bridge_worker(frame_id: int, body: PackedByteArray) -> void:
	var result: Dictionary = native_bridge.upscale_residual(body)
	call_deferred(
		"_complete_native_bridge_response",
		frame_id,
		result,
		Time.get_ticks_usec(),
	)


## Convert the in-process native result into the existing telemetry contract.
func _complete_native_bridge_response(
	frame_id: int,
	result: Dictionary,
	received_usec: int,
) -> void:
	var context: Dictionary = benchmark_pending.get(frame_id, {})
	benchmark_pending.erase(frame_id)
	context["roundtrip_ms"] = (
		received_usec
		- int(context.get("roundtrip_start_usec", received_usec))
	) / 1000.0
	context["response_received_usec"] = received_usec
	if not bool(result.get("ok", false)):
		context["response_payload_bytes"] = 0
		context["response"] = {
			"valid": false,
			"error": str(result.get("error", "native bridge failed")),
		}
	else:
		var mode: Dictionary = MODES[mode_id]
		var payload: PackedByteArray = result["payload"]
		var image := Image.create_from_data(
			int(mode["hr"].x),
			int(mode["hr"].y),
			false,
			Image.FORMAT_RGB8,
			payload,
		)
		context["response_payload_bytes"] = payload.size()
		context["response"] = {
			"valid": true,
			"image": image,
			"metadata": {
				"backend_id": "heterogeneous_progressive",
				"has_neural_image": true,
				"route_status": "accepted_neural",
				"selected_method_id": native_bridge_method,
				"raw_method_id": native_bridge_method,
				"selector_ms": 0.0,
				"npu_worker_id": str(result["worker_id"]),
				"npu_queue_depth": 0,
				"npu_queue_limit": pipeline_depth,
				"backend_queue_wait_ms": 0.0,
				"backend_queue_service_ms": float(result["bridge_total_ms"]),
				"backend_inference_ms": float(result["npu_inference_ms"]),
				"backend_materialize_ms": float(result["output_copy_ms"]),
				"backend_rga_resize_ms": 0.0,
				"backend_residual_pack_ms": float(result["residual_pack_ms"]),
				"backend_native_total_ms": float(result["native_total_ms"]),
				"neural_payload_kind": "pixelshuffled_int8_residual_biased_128",
				"residual_scale": float(result["output_scale"]),
				"residual_zero_point": int(result["output_zero_point"]),
				"dmabuf_slot_index": int(result["slot_index"]),
				"dmabuf_sequence_id": int(result["sequence_id"]),
				"reconstruction_backend": "godot_inprocess_dmabuf_gpu_residual",
			},
		}
	benchmark_completed[frame_id] = context
	benchmark_response_ready.emit(frame_id)


## Connect one persistent binary stream per bounded pipeline slot.
##
## Each stream carries at most one outstanding frame, preserving finite memory
## ownership while allowing two NPU contexts and a newest-only pending slot to
## overlap without opening a fresh HTTP connection for every image.
func _initialize_persistent_streams() -> bool:
	persistent_stream_slots.clear()
	for slot_index in range(pipeline_depth):
		var peer := StreamPeerTCP.new()
		var connect_error := peer.connect_to_host(stream_host, stream_port)
		if connect_error != OK:
			push_error(
				"persistent stream %d connect failed: %d"
				% [slot_index, connect_error]
			)
			return false
		var deadline_msec := Time.get_ticks_msec() + 30000
		while peer.get_status() == StreamPeerTCP.STATUS_CONNECTING:
			peer.poll()
			if Time.get_ticks_msec() >= deadline_msec:
				push_error("persistent stream connection timed out")
				return false
			await get_tree().process_frame
		if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
			push_error("persistent stream did not reach connected state")
			return false
		peer.set_no_delay(true)
		persistent_stream_slots.append({
			"peer": peer,
			"frame_id": -1,
			"response_bytes": PackedByteArray(),
			"expected_response_bytes": -1,
		})
	print(
		"GODOT_PERSISTENT_STREAM_READY slots=%d endpoint=%s:%d"
		% [persistent_stream_slots.size(), stream_host, stream_port]
	)
	return true


## Serialize one compact control object plus raw RGB into an available stream.
func _begin_persistent_stream_request(
	frame_id: int,
	body: PackedByteArray,
	context: Dictionary,
) -> Error:
	var selected_slot: Dictionary = {}
	for slot in persistent_stream_slots:
		if int(slot["frame_id"]) < 0:
			selected_slot = slot
			break
	if selected_slot.is_empty():
		return ERR_BUSY

	var mode: Dictionary = MODES[mode_id]
	var deadline_ms := (
		float(maximum_neural_age_frames) * 1000.0 / benchmark_fps
	)
	var request_metadata := {
		"protocol": PROTOCOL_ID,
		"transport_id": "raw_rgb",
		"run_id": run_id,
		"frame_id": frame_id,
		"lr_width": int(mode["lr"].x),
		"lr_height": int(mode["lr"].y),
		"deadline_ms": deadline_ms,
		"temperature_c": temperature_c,
		"temperature_limit_c": temperature_limit_c,
		"temperature_critical_c": temperature_critical_c,
		"power_budget_w": power_budget_w,
		"observed_power_w": observed_power_w,
		"previous_frame_ms": previous_frame_ms,
		"gpu_frame_ms": current_gpu_frame_ms,
		"deadline_slack_ms": maxf(0.0, deadline_ms - current_gpu_frame_ms),
		"renderer_metadata": _renderer_metadata(),
	}
	var metadata_bytes := JSON.stringify(request_metadata).to_utf8_buffer()
	var frame_bytes := PackedByteArray()
	_append_u32_be(frame_bytes, metadata_bytes.size())
	_append_u32_be(frame_bytes, body.size())
	frame_bytes.append_array(metadata_bytes)
	frame_bytes.append_array(body)

	context["roundtrip_start_usec"] = Time.get_ticks_usec()
	benchmark_pending[frame_id] = context
	selected_slot["frame_id"] = frame_id
	selected_slot["response_bytes"] = PackedByteArray()
	selected_slot["expected_response_bytes"] = -1
	var slot_index := persistent_stream_slots.find(selected_slot)
	selected_slot["worker_task_id"] = WorkerThreadPool.add_task(
		_persistent_stream_worker.bind(
			slot_index,
			frame_id,
			frame_bytes,
			selected_slot["peer"],
		),
		true,
		"Phase7StreamSlot%d" % slot_index,
	)
	return OK


## Own one complete request/response exchange away from the render thread.
##
## Each worker has exclusive access to one persistent stream until its result
## is handed back. This timestamps actual byte arrival instead of delaying it
## until the next render-loop poll, while the finite slot count still bounds
## memory and outstanding NPU work.
func _persistent_stream_worker(
	slot_index: int,
	frame_id: int,
	frame_bytes: PackedByteArray,
	peer: StreamPeerTCP,
) -> void:
	var send_error := peer.put_data(frame_bytes)
	if send_error != OK:
		call_deferred(
			"_complete_persistent_stream_response",
			slot_index,
			frame_id,
			PackedByteArray(),
			Time.get_ticks_usec(),
			"persistent stream send failed: %d" % send_error,
		)
		return
	var prefix_result := peer.get_data(4)
	if int(prefix_result[0]) != OK:
		call_deferred(
			"_complete_persistent_stream_response",
			slot_index,
			frame_id,
			PackedByteArray(),
			Time.get_ticks_usec(),
			"persistent stream prefix read failed: %d" % int(prefix_result[0]),
		)
		return
	var expected := _read_u32_be(prefix_result[1], 0)
	if expected < 1 or expected > 4000000:
		call_deferred(
			"_complete_persistent_stream_response",
			slot_index,
			frame_id,
			PackedByteArray(),
			Time.get_ticks_usec(),
			"persistent stream response length is invalid",
		)
		return
	var body_result := peer.get_data(expected)
	var received_usec := Time.get_ticks_usec()
	if int(body_result[0]) != OK:
		call_deferred(
			"_complete_persistent_stream_response",
			slot_index,
			frame_id,
			PackedByteArray(),
			received_usec,
			"persistent stream body read failed: %d" % int(body_result[0]),
		)
		return
	call_deferred(
		"_complete_persistent_stream_response",
		slot_index,
		frame_id,
		body_result[1],
		received_usec,
		"",
	)


## Return a worker-owned response to deterministic main-thread bookkeeping.
func _complete_persistent_stream_response(
	slot_index: int,
	frame_id: int,
	body: PackedByteArray,
	received_usec: int,
	error_message: String,
) -> void:
	var slot: Dictionary = persistent_stream_slots[slot_index]
	var context: Dictionary = benchmark_pending.get(frame_id, {})
	benchmark_pending.erase(frame_id)
	context["roundtrip_ms"] = (
		received_usec
		- int(context.get("roundtrip_start_usec", received_usec))
	) / 1000.0
	context["response_received_usec"] = received_usec
	context["response_payload_bytes"] = body.size()
	context["response"] = (
		_decode_response(body)
		if error_message.is_empty()
		else {"valid": false, "error": error_message}
	)
	benchmark_completed[frame_id] = context
	slot["frame_id"] = -1
	slot["worker_task_id"] = -1
	benchmark_response_ready.emit(frame_id)


## Append one unsigned 32-bit big-endian protocol field.
func _append_u32_be(destination: PackedByteArray, value: int) -> void:
	destination.append((value >> 24) & 0xFF)
	destination.append((value >> 16) & 0xFF)
	destination.append((value >> 8) & 0xFF)
	destination.append(value & 0xFF)


## Parse one unsigned 32-bit big-endian protocol field.
func _read_u32_be(source: PackedByteArray, offset: int) -> int:
	if offset < 0 or offset + 4 > source.size():
		return -1
	return (
		(int(source[offset]) << 24)
		| (int(source[offset + 1]) << 16)
		| (int(source[offset + 2]) << 8)
		| int(source[offset + 3])
	)


## Decode metadata plus the selected copied output representation.
func _decode_response(body: PackedByteArray) -> Dictionary:
	if body.size() < 4:
		return {"valid": false, "error": "response body is too short"}
	var metadata_length := (int(body[0]) << 24) | (int(body[1]) << 16) | (int(body[2]) << 8) | int(body[3])
	if metadata_length < 2 or 4 + metadata_length > body.size():
		return {"valid": false, "error": "response metadata length is invalid"}
	var metadata_bytes := body.slice(4, 4 + metadata_length)
	var parsed: Variant = JSON.parse_string(metadata_bytes.get_string_from_utf8())
	if not parsed is Dictionary:
		return {"valid": false, "error": "response metadata is not a JSON object"}
	var has_neural_image := bool(parsed.get("has_neural_image", true))
	if not has_neural_image:
		if 4 + metadata_length != body.size():
			return {"valid": false, "error": "fallback response contains unexpected image bytes"}
		return {"valid": true, "metadata": parsed, "image": null}
	var image := Image.new()
	var image_payload := body.slice(4 + metadata_length)
	if str(parsed.get("transport_id", "png")) == "raw_rgb":
		var width := int(parsed.get("hr_width", 0))
		var height := int(parsed.get("hr_height", 0))
		if width < 1 or height < 1 or image_payload.size() != width * height * 3:
			return {"valid": false, "error": "raw RGB response dimensions are invalid"}
		image = Image.create_from_data(width, height, false, Image.FORMAT_RGB8, image_payload)
	else:
		var image_error := image.load_png_from_buffer(image_payload)
		if image_error != OK:
			return {"valid": false, "error": "response PNG decode failed: %d" % image_error}
	return {"valid": true, "metadata": parsed, "image": image}


## Keep the native HUD explicit about measured versus unavailable values.
func _update_hud() -> void:
	if hud_label == null:
		return
	var mode: Dictionary = MODES[mode_id]
	var latency_text := "pending"
	var routing_text := ""
	if not last_metadata.is_empty():
		if last_metadata.has("error"):
			latency_text = "ERROR: %s" % str(last_metadata["error"])
		else:
			latency_text = "infer %.2f ms | PSNR %s" % [
				float(last_metadata.get("backend_inference_ms", 0.0)),
				"%.2f dB" % float(last_metadata["psnr_db"]) if last_metadata.get("psnr_db") != null else "n/a",
			]
			if last_metadata.has("executed_method_counts"):
				routing_text = " | tiles %s" % JSON.stringify(last_metadata["executed_method_counts"])
			elif last_metadata.has("route_status"):
				routing_text = " | %s -> %s | core %s" % [
					str(last_metadata.get("selected_method_id", "fallback")),
					str(last_metadata["route_status"]),
					str(last_metadata.get("npu_worker_id", "GPU")),
				]
	hud_label.text = "%s | %s | %s%s | native HUD/composition" % [str(mode["label"]), backend_id, latency_text, routing_text]
