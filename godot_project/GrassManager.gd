class_name GrassManager
extends Node3D

## GrassManager.gd - High Performance Procedural Grass Blade System (Godot 4.x)
##
## Spawns thousands of grass blade tufts in a radius around the camera using a single
## MultiMeshInstance3D draw call. Tufts sway with wind and seamlessly fade at distance.

@export var enabled: bool = true
@export var instance_count: int = 6000
@export var radius: float = 60.0
@export var tuft_height: float = 0.55
@export var tuft_width: float = 0.45
@export var target_camera: Camera3D

var _multimesh_instance: MultiMeshInstance3D
var _last_grid_center: Vector2i = Vector2i(-999999, -999999)

func _ready() -> void:
	if not target_camera:
		target_camera = get_viewport().get_camera_3d()
	_create_grass_multimesh()

func _create_grass_mesh() -> ArrayMesh:
	var st = SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

	var w = tuft_width * 0.5
	var h = tuft_height

	# Quad 1 (Facing Z)
	st.set_uv(Vector2(0, 0))
	st.add_vertex(Vector3(-w, 0, 0))
	st.set_uv(Vector2(1, 0))
	st.add_vertex(Vector3(w, 0, 0))
	st.set_uv(Vector2(1, 1))
	st.add_vertex(Vector3(w * 0.7, h, 0))
	st.set_uv(Vector2(0, 1))
	st.add_vertex(Vector3(-w * 0.7, h, 0))

	# Quad 2 (Crossed at 60 deg)
	var cos60 = 0.5
	var sin60 = 0.866
	st.set_uv(Vector2(0, 0))
	st.add_vertex(Vector3(-w * cos60, 0, -w * sin60))
	st.set_uv(Vector2(1, 0))
	st.add_vertex(Vector3(w * cos60, 0, w * sin60))
	st.set_uv(Vector2(1, 1))
	st.add_vertex(Vector3(w * 0.7 * cos60, h, w * 0.7 * sin60))
	st.set_uv(Vector2(0, 1))
	st.add_vertex(Vector3(-w * 0.7 * cos60, h, -w * 0.7 * sin60))

	# Quad 3 (Crossed at 120 deg)
	st.set_uv(Vector2(0, 0))
	st.add_vertex(Vector3(-w * cos60, 0, w * sin60))
	st.set_uv(Vector2(1, 0))
	st.add_vertex(Vector3(w * cos60, 0, -w * sin60))
	st.set_uv(Vector2(1, 1))
	st.add_vertex(Vector3(w * 0.7 * cos60, h, -w * 0.7 * sin60))
	st.set_uv(Vector2(0, 1))
	st.add_vertex(Vector3(-w * 0.7 * cos60, h, w * 0.7 * sin60))

	# Indices for 3 double-sided quads (6 triangles)
	for q in range(3):
		var base = q * 4
		# Face front
		st.add_index(base + 0)
		st.add_index(base + 1)
		st.add_index(base + 2)
		st.add_index(base + 0)
		st.add_index(base + 2)
		st.add_index(base + 3)

	st.generate_normals()
	return st.commit()

func _create_grass_multimesh() -> void:
	_multimesh_instance = MultiMeshInstance3D.new()
	_multimesh_instance.name = "GrassMultiMesh"

	var mm = MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.instance_count = instance_count
	mm.mesh = _create_grass_mesh()

	var mat = ShaderMaterial.new()
	mat.shader = load("res://procedural_grass_shader.gdshader")
	_multimesh_instance.material_override = mat
	_multimesh_instance.multimesh = mm

	add_child(_multimesh_instance)
	_distribute_grass_instances(Vector3(1440, 0, 1690))

func _distribute_grass_instances(center: Vector3) -> void:
	if not _multimesh_instance or not _multimesh_instance.multimesh:
		return

	var mm = _multimesh_instance.multimesh
	var rng = RandomNumberGenerator.new()
	rng.seed = 1337

	for i in range(instance_count):
		# Golden ratio spiral distribution for uniform density
		var r = sqrt(rng.randf()) * radius
		var theta = rng.randf() * TAU

		var lx = r * cos(theta)
		var lz = r * sin(theta)
		var gx = center.x + lx
		var gz = center.z + lz

		# Random scale and rotation for natural look
		var scale_y = rng.randf_range(0.75, 1.35)
		var scale_xz = rng.randf_range(0.85, 1.25)
		var rot_y = rng.randf() * TAU

		var t = Transform3D()
		t = t.scaled(Vector3(scale_xz, scale_y, scale_xz))
		t = t.rotated(Vector3.UP, rot_y)
		# Position (Y offset will be updated to ground)
		t.origin = Vector3(gx, center.y, gz)

		mm.set_instance_transform(i, t)

func _process(_delta: float) -> void:
	if not enabled or not target_camera:
		return

	var cam_pos = target_camera.global_position
	var grid_x = int(floor(cam_pos.x / 4.0))
	var grid_z = int(floor(cam_pos.z / 4.0))
	var current_grid = Vector2i(grid_x, grid_z)

	if current_grid != _last_grid_center:
		_last_grid_center = current_grid
		_multimesh_instance.global_position.x = grid_x * 4.0
		_multimesh_instance.global_position.z = grid_z * 4.0
		# Center grass relative to offset
