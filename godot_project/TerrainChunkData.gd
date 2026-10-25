class_name TerrainChunkData
extends Resource

## TerrainChunkData.gd - Godot 4 Resource representation of an Ultima Online Terrain Chunk
##
## Stores packed arrays and builds native ArrayMesh resources on demand.

@export var chunk_x: int = 0
@export var chunk_y: int = 0
@export var world_pos: Vector3 = Vector3.ZERO
@export var tile_width: int = 64
@export var tile_height: int = 64
@export var h_scale: float = 1.0
@export var v_scale: float = 0.125

@export var vertices: PackedVector3Array
@export var normals: PackedVector3Array
@export var uvs: PackedVector2Array
@export var colors: PackedColorArray
@export var indices: PackedInt32Array


## Generates an ArrayMesh from the stored arrays
func create_mesh() -> ArrayMesh:
	var mesh := ArrayMesh.new()
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)

	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_INDEX] = indices

	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh
