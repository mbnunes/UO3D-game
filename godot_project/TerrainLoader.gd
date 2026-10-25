class_name TerrainLoader
extends Node3D

## TerrainLoader.gd - Hierarchical Sector Dynamic Chunk Streaming for Godot 4.x
##
## Streams terrain chunks dynamically based on camera distance across a continuous world.
## Supports hierarchical sector subdirectories (e.g. terrain_chunks/sector_02_03/chunk_21_25.glb)
## allowing instant startup and zero editor lag even for 7,168 chunks.

@export_group("Streaming Settings")
## Path to root folder containing terrain chunks (or sector subdirectories)
@export_dir var chunks_directory: String = "res://terrain_chunks/"

## Format to load: "glb", "tres", "obj", or "auto"
@export_enum("auto", "glb", "tres", "obj") var chunk_format: String = "glb"

## If true, uses hierarchical sector subfolders: sector_SX_SY/chunk_CX_CY.glb
@export var hierarchical_sectors: bool = true

## Number of chunks per sector along each axis (default: 8, meaning 8x8 chunks = 512x512 tiles)
@export var sector_size: int = 8

## Distance from camera in world units to load chunks
@export var view_distance: float = 384.0

## Distance beyond view_distance before an inactive chunk is unloaded
@export var unload_margin: float = 64.0

## Camera or Node3D to track for chunk streaming. If null, automatically detects active Camera3D.
@export var target_camera: Node3D

## Maximum number of chunks to load/instantiate per frame to prevent stutter
@export_range(1, 16) var max_chunk_loads_per_frame: int = 3

## Total map bounds in chunks (default for Britannia map0: 112 cols x 64 rows)
@export var world_chunks_x: int = 112
@export var world_chunks_y: int = 64

@export_group("Collision & Physics")
## If true, creates a StaticBody3D with ConcavePolygonShape3D collision for each chunk
@export var generate_collision: bool = true

## Collision layer for the terrain static bodies
@export_flags_3d_physics var collision_layer: int = 1

## Collision mask for the terrain static bodies
@export_flags_3d_physics var collision_mask: int = 1

@export_group("Buildings Streaming")
## If true, loads 3D architectural buildings dynamically per chunk
@export var load_chunk_buildings_enabled: bool = true
## If true, loads standalone Lord British Castle test model (keep false when streaming chunk buildings)
@export var load_castle_british_test: bool = false
## Path to Lord British Castle model
@export_file("*.glb") var castle_british_path: String = "res://buildings/lord_british_castle.glb"

@export_group("Visuals & Materials")
## If true, retains the authentic baked UO textures embedded in the mesh
@export var use_baked_textures: bool = true

## Material or ShaderMaterial to assign to chunks (only overrides if use_baked_textures is false)
@export var custom_material: Material

## Cast shadows for terrain chunks
@export var shadow_casting: GeometryInstance3D.ShadowCastingSetting = GeometryInstance3D.SHADOW_CASTING_SETTING_ON


# Internal state
class PendingChunk:
	var chunk_x: int
	var chunk_y: int
	var file_path: String
	var center_pos: Vector3
	var world_pos: Vector3

var _loaded_chunks: Dictionary = {}  # Vector2i(cx, cy) -> Node3D
var _load_queue: Array[PendingChunk] = []
var _queued_keys: Dictionary = {}    # Vector2i(cx, cy) -> bool
var _chunk_size_meters: float = 64.0
var _time_since_last_check: float = 0.0
var _atlas_texture: Texture2D = null
var _buildings_atlas_texture: Texture2D = null
const CHECK_INTERVAL: float = 0.15


func _get_buildings_atlas_texture() -> Texture2D:
	if _buildings_atlas_texture:
		return _buildings_atlas_texture
	var bld_atlas_path := "res://buildings/uo_buildings_atlas.png"
	var global_path := ProjectSettings.globalize_path(bld_atlas_path)
	if FileAccess.file_exists(bld_atlas_path) or FileAccess.file_exists(global_path):
		var img := Image.load_from_file(global_path if FileAccess.file_exists(global_path) else bld_atlas_path)
		if img:
			_buildings_atlas_texture = ImageTexture.create_from_image(img)
	if not _buildings_atlas_texture and ResourceLoader.exists(bld_atlas_path):
		_buildings_atlas_texture = load(bld_atlas_path) as Texture2D
	return _buildings_atlas_texture


func _get_atlas_texture() -> Texture2D:
	if _atlas_texture:
		return _atlas_texture
	var atlas_path := chunks_directory + "uo_land_atlas.png"
	if ResourceLoader.exists(atlas_path):
		_atlas_texture = load(atlas_path) as Texture2D
	if not _atlas_texture and FileAccess.file_exists(atlas_path):
		var img := Image.load_from_file(atlas_path)
		if img:
			_atlas_texture = ImageTexture.create_from_image(img)
	return _atlas_texture


func _ready() -> void:
	if not chunks_directory.ends_with("/"):
		chunks_directory += "/"
	_read_manifest()
	_load_castle_british()
	_update_streaming(true)


func _process(delta: float) -> void:
	_process_load_queue()

	_time_since_last_check += delta
	if _time_since_last_check >= CHECK_INTERVAL:
		_time_since_last_check = 0.0
		_update_streaming(false)


func _read_manifest() -> void:
	var manifest_path := chunks_directory + "manifest.json"
	if not FileAccess.file_exists(manifest_path):
		manifest_path = chunks_directory + "terrain_manifest.json"

	if FileAccess.file_exists(manifest_path):
		var file := FileAccess.open(manifest_path, FileAccess.READ)
		if file:
			var json = JSON.new()
			if json.parse(file.get_as_text()) == OK and json.data is Dictionary:
				var m_data: Dictionary = json.data
				if m_data.has("chunk_size_meters"):
					_chunk_size_meters = float(m_data["chunk_size_meters"])
				if m_data.has("sector_size"):
					sector_size = int(m_data["sector_size"])
				if m_data.has("hierarchical"):
					hierarchical_sectors = bool(m_data["hierarchical"])
				if m_data.has("world_chunks_x"):
					world_chunks_x = int(m_data["world_chunks_x"])
				if m_data.has("world_chunks_y"):
					world_chunks_y = int(m_data["world_chunks_y"])


func switch_map(map_id: int) -> void:
	# Unload all currently loaded terrain chunks
	for key in _loaded_chunks.keys():
		var chunk_node: Node3D = _loaded_chunks[key]
		if is_instance_valid(chunk_node):
			chunk_node.queue_free()
	_loaded_chunks.clear()
	_load_queue.clear()
	_queued_keys.clear()

	_atlas_texture = null

	var map_dirs := {
		0: "res://terrain_chunks_atlas/",
		1: "res://terrain_chunks_atlas_map1/",
		2: "res://terrain_chunks_atlas_map2/",
		3: "res://terrain_chunks_atlas_map3/",
		4: "res://terrain_chunks_atlas_map4/",
		5: "res://terrain_chunks_atlas_map5/",
	}

	if map_dirs.has(map_id):
		chunks_directory = map_dirs[map_id]

	_read_manifest()
	_update_streaming(true)


func _find_camera() -> Node3D:
	if is_instance_valid(target_camera):
		return target_camera
	var cam: Camera3D = get_viewport().get_camera_3d()
	if cam:
		return cam
	return self


func _resolve_chunk_path(cx: int, cy: int) -> String:
	var base_name := "chunk_%d_%d" % [cx, cy]
	var ext := "glb" if chunk_format in ["glb", "auto"] else chunk_format

	if hierarchical_sectors and sector_size > 0:
		var sx := cx / sector_size
		var sy := cy / sector_size
		var p := "%ssector_%02d_%02d/%s.%s" % [chunks_directory, sx, sy, base_name, ext]
		if FileAccess.file_exists(p):
			return p
	else:
		var p := "%s%s.%s" % [chunks_directory, base_name, ext]
		if FileAccess.file_exists(p):
			return p

	# Fallbacks for other formats
	for fallback_ext in ["glb", "tres", "obj"]:
		if hierarchical_sectors and sector_size > 0:
			var sx := cx / sector_size
			var sy := cy / sector_size
			var p := "%ssector_%02d_%02d/%s.%s" % [chunks_directory, sx, sy, base_name, fallback_ext]
			if FileAccess.file_exists(p):
				return p
		else:
			var p := "%s%s.%s" % [chunks_directory, base_name, fallback_ext]
			if FileAccess.file_exists(p):
				return p

	# Fallback: universal ocean chunk for water coordinates
	var ocean_fallback := chunks_directory + "ocean_chunk.glb"
	if FileAccess.file_exists(ocean_fallback):
		return ocean_fallback

	return ""


func _update_streaming(force_immediate: bool = false) -> void:
	var cam := _find_camera()
	if not cam:
		return

	var cam_pos := cam.global_position
	var view_dist_sq := view_distance * view_distance
	var unload_dist_sq := (view_distance + unload_margin) * (view_distance + unload_margin)

	var cam_cx := int(floor(cam_pos.x / _chunk_size_meters))
	var cam_cy := int(floor(cam_pos.z / _chunk_size_meters))
	var radius := int(ceil(view_distance / _chunk_size_meters))

	# 1. Enqueue chunks in range
	for dy in range(-radius, radius + 1):
		var cy := cam_cy + dy
		if cy < 0 or cy >= world_chunks_y:
			continue
		for dx in range(-radius, radius + 1):
			var cx := cam_cx + dx
			if cx < 0 or cx >= world_chunks_x:
				continue

			var key := Vector2i(cx, cy)
			var center_x := (cx + 0.5) * _chunk_size_meters
			var center_z := (cy + 0.5) * _chunk_size_meters
			var dist_sq := (center_x - cam_pos.x) ** 2 + (center_z - cam_pos.z) ** 2

			if dist_sq <= view_dist_sq:
				if not _loaded_chunks.has(key) and not _queued_keys.has(key):
					var p_path := _resolve_chunk_path(cx, cy)
					if not p_path.is_empty():
						var p := PendingChunk.new()
						p.chunk_x = cx
						p.chunk_y = cy
						p.file_path = p_path
						p.center_pos = Vector3(center_x, 0, center_z)
						p.world_pos = Vector3(cx * _chunk_size_meters, 0, cy * _chunk_size_meters)
						if force_immediate:
							_instantiate_chunk(p)
						else:
							_load_queue.append(p)
							_queued_keys[key] = true

	# 2. Unload chunks out of range
	var to_unload: Array[Vector2i] = []
	for key: Vector2i in _loaded_chunks:
		var center_x := (key.x + 0.5) * _chunk_size_meters
		var center_z := (key.y + 0.5) * _chunk_size_meters
		var dist_sq := (center_x - cam_pos.x) ** 2 + (center_z - cam_pos.z) ** 2
		if dist_sq > unload_dist_sq:
			to_unload.append(key)

	for key in to_unload:
		var node: Node3D = _loaded_chunks[key]
		if is_instance_valid(node):
			node.queue_free()
		_loaded_chunks.erase(key)

	# 3. Sort load queue: closest chunks load first
	if not _load_queue.is_empty():
		_load_queue.sort_custom(func(a: PendingChunk, b: PendingChunk) -> bool:
			var da := (a.center_pos.x - cam_pos.x) ** 2 + (a.center_pos.z - cam_pos.z) ** 2
			var db := (b.center_pos.x - cam_pos.x) ** 2 + (b.center_pos.z - cam_pos.z) ** 2
			return da < db
		)


func _process_load_queue() -> void:
	var loads := 0
	while not _load_queue.is_empty() and loads < max_chunk_loads_per_frame:
		var p: PendingChunk = _load_queue.pop_front()
		if p:
			var key := Vector2i(p.chunk_x, p.chunk_y)
			_queued_keys.erase(key)
			if not _loaded_chunks.has(key):
				_instantiate_chunk(p)
				loads += 1


func _instantiate_chunk(p: PendingChunk) -> void:
	var key := Vector2i(p.chunk_x, p.chunk_y)
	if _loaded_chunks.has(key):
		return

	var ext := p.file_path.get_extension().to_lower()
	var chunk_root: Node3D = null
	var mesh_inst: MeshInstance3D = null

	if ext == "glb":
		var gltf := GLTFDocument.new()
		var state := GLTFState.new()
		if gltf.append_from_file(p.file_path, state) == OK:
			chunk_root = gltf.generate_scene(state)

		if chunk_root:
			mesh_inst = _find_mesh_instance(chunk_root)
			if chunk_root.position == Vector3.ZERO:
				chunk_root.position = p.world_pos
	elif ext in ["tres", "obj"]:
		var mesh_res = load(p.file_path)
		if mesh_res is Mesh:
			mesh_inst = MeshInstance3D.new()
			mesh_inst.mesh = mesh_res
			chunk_root = Node3D.new()
			chunk_root.add_child(mesh_inst)
			chunk_root.position = p.world_pos

	if not chunk_root:
		return

	chunk_root.name = "Chunk_%d_%d" % [p.chunk_x, p.chunk_y]

	if mesh_inst:
		mesh_inst.cast_shadow = shadow_casting
		if not use_baked_textures and custom_material:
			mesh_inst.material_override = custom_material
		elif use_baked_textures and mesh_inst.mesh:
			var mat = mesh_inst.get_active_material(0)
			if mat is StandardMaterial3D and not mat.albedo_texture:
				var atlas_tex := _get_atlas_texture()
				if atlas_tex:
					mat.albedo_texture = atlas_tex
					mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST

		if generate_collision and mesh_inst.mesh:
			_attach_collision(chunk_root, mesh_inst)

	# Load and attach 3D buildings for this chunk if available
	_load_chunk_buildings(chunk_root, p.chunk_x, p.chunk_y)
	_load_custom_buildings(chunk_root, p.chunk_x, p.chunk_y)

	add_child(chunk_root)
	_loaded_chunks[key] = chunk_root


func _attach_collision(parent_node: Node3D, mesh_inst: MeshInstance3D) -> void:
	var shape: ConcavePolygonShape3D = mesh_inst.mesh.create_trimesh_shape()
	if not shape:
		return

	var static_body := StaticBody3D.new()
	static_body.name = "StaticBody"
	static_body.collision_layer = collision_layer
	static_body.collision_mask = collision_mask

	var col_shape := CollisionShape3D.new()
	col_shape.name = "CollisionShape"
	col_shape.shape = shape
	col_shape.transform = mesh_inst.transform
	static_body.add_child(col_shape)
	parent_node.add_child(static_body)


func _find_mesh_instance(node: Node) -> MeshInstance3D:
	if node is MeshInstance3D:
		return node
	for child in node.get_children():
		var found := _find_mesh_instance(child)
		if found:
			return found
	return null


func _load_chunk_buildings(parent_chunk: Node3D, cx: int, cy: int) -> void:
	if not load_chunk_buildings_enabled:
		return
	var bld_path := "res://buildings/chunk_%d_%d_buildings.glb" % [cx, cy]
	if not FileAccess.file_exists(bld_path):
		return

	var gltf := GLTFDocument.new()
	var state := GLTFState.new()
	if gltf.append_from_file(bld_path, state) != OK:
		return

	var bld_node: Node3D = gltf.generate_scene(state)
	if bld_node:
		bld_node.name = "Buildings"
		var bld_mesh := _find_mesh_instance(bld_node)
		if bld_mesh and bld_mesh.mesh:
			bld_mesh.cast_shadow = shadow_casting
			if generate_collision:
				_attach_collision(bld_node, bld_mesh)
		parent_chunk.add_child(bld_node)


var _custom_manifest: Dictionary = {}
var _custom_manifest_read: bool = false

func _load_custom_manifest_data() -> void:
	if _custom_manifest_read:
		return
	_custom_manifest_read = true
	var path := "res://custom_buildings/custom_buildings.json"
	if not FileAccess.file_exists(path):
		return
	var f := FileAccess.open(path, FileAccess.READ)
	if f:
		var json_str := f.get_as_text()
		var parsed = JSON.parse_string(json_str)
		if parsed is Array:
			for item in parsed:
				var c_arr = item.get("chunk", [])
				if c_arr.size() == 2:
					var c_key := Vector2i(int(c_arr[0]), int(c_arr[1]))
					if not _custom_manifest.has(c_key):
						_custom_manifest[c_key] = []
					_custom_manifest[c_key].append(item)


func _load_custom_buildings(parent_chunk: Node3D, cx: int, cy: int) -> void:
	_load_custom_manifest_data()
	var c_key := Vector2i(cx, cy)
	if not _custom_manifest.has(c_key):
		return

	for item: Dictionary in _custom_manifest[c_key]:
		var m_path: String = item.get("model_path", "")
		if not FileAccess.file_exists(m_path):
			continue
		var gltf := GLTFDocument.new()
		var state := GLTFState.new()
		if gltf.append_from_file(m_path, state) != OK:
			continue
		var c_node: Node3D = gltf.generate_scene(state)
		if c_node:
			c_node.name = item.get("building_id", "CustomBuilding")
			var pos_arr = item.get("position", [0.0, 0.0, 0.0])
			c_node.position = Vector3(float(pos_arr[0]), float(pos_arr[1]), float(pos_arr[2]))
			var c_mesh := _find_mesh_instance(c_node)
			if c_mesh and c_mesh.mesh:
				c_mesh.cast_shadow = shadow_casting
				if generate_collision:
					_attach_collision(c_node, c_mesh)
			parent_chunk.add_child(c_node)


func _load_castle_british() -> void:
	if not load_castle_british_test:
		return

	var path := castle_british_path
	var global_path := ProjectSettings.globalize_path(path)
	if not FileAccess.file_exists(path) and not FileAccess.file_exists(global_path):
		push_warning("[TerrainLoader] Arquivo do castelo não encontrado: %s" % path)
		return

	var actual_path := global_path if FileAccess.file_exists(global_path) else path
	var gltf := GLTFDocument.new()
	var state := GLTFState.new()
	if gltf.append_from_file(actual_path, state) != OK:
		push_error("[TerrainLoader] Erro ao carregar GLB do castelo: %s" % actual_path)
		return

	var castle_node: Node3D = gltf.generate_scene(state)
	if castle_node:
		castle_node.name = "LordBritishCastle"
		castle_node.position = Vector3.ZERO
		var mesh_inst := _find_mesh_instance(castle_node)
		if mesh_inst and mesh_inst.mesh:
			mesh_inst.cast_shadow = shadow_casting
			if generate_collision:
				_attach_collision(castle_node, mesh_inst)
		add_child(castle_node)
		print("[TerrainLoader] Castelo do Lord British carregado com sucesso (3D Sólido Clay).")

