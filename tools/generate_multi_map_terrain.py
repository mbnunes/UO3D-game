#!/usr/bin/env python3
"""
generate_multi_map_terrain.py - Generates 3D terrain meshes with Texture Atlas for Maps 1..5 in Godot 4.
Supports Trammel (Map 1), Ilshenar (Map 2), Malas (Map 3), Tokuno (Map 4), and Ter Mur (Map 5).
"""

import sys
import os
import io
import math
import mmap
import struct
import json
import time
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from PIL import Image

UOC_DIR = "/opt/hd_jogos/UOC"
TILEDATA_FILE = os.path.join(UOC_DIR, "tiledata.mul")
TEXIDX_FILE = os.path.join(UOC_DIR, "texidx.mul")
TEXMAPS_FILE = os.path.join(UOC_DIR, "texmaps.mul")
BASE_OUTPUT_DIR = "/home/mnunes/uo3d_map/godot_project"

MAP_CONFIGS = {
    0: {"name": "Felucca",  "file": "map0.mul", "w_tiles": 7168, "h_tiles": 4096, "w_blocks": 896, "h_blocks": 512, "chunks_x": 112, "chunks_y": 64, "folder": "terrain_chunks_atlas"},
    1: {"name": "Trammel",  "file": "map1.mul", "w_tiles": 7168, "h_tiles": 4096, "w_blocks": 896, "h_blocks": 512, "chunks_x": 112, "chunks_y": 64, "folder": "terrain_chunks_atlas_map1"},
    2: {"name": "Ilshenar", "file": "map2.mul", "w_tiles": 2304, "h_tiles": 1600, "w_blocks": 288, "h_blocks": 200, "chunks_x": 36,  "chunks_y": 25, "folder": "terrain_chunks_atlas_map2"},
    3: {"name": "Malas",    "file": "map3.mul", "w_tiles": 2560, "h_tiles": 2048, "w_blocks": 320, "h_blocks": 256, "chunks_x": 40,  "chunks_y": 32, "folder": "terrain_chunks_atlas_map3"},
    4: {"name": "Tokuno",   "file": "map4.mul", "w_tiles": 1448, "h_tiles": 1448, "w_blocks": 181, "h_blocks": 181, "chunks_x": 23,  "chunks_y": 23, "folder": "terrain_chunks_atlas_map4"},
    5: {"name": "TerMur",   "file": "map5.mul", "w_tiles": 1280, "h_tiles": 4096, "w_blocks": 160, "h_blocks": 512, "chunks_x": 20,  "chunks_y": 64, "folder": "terrain_chunks_atlas_map5"},
}

WATER_TILE_IDS = {168, 169, 170, 171, 310, 311}
SLOTS_PER_SIDE = 40
CELL_RES = 64
ATLAS_DIM = SLOTS_PER_SIDE * CELL_RES

H_SCALE = 1.0
V_SCALE = 0.12
CHUNK_TILES = 64
SECTOR_SIZE = 8

_WORKER_MM = None
_WORKER_TD = None
_WORKER_TEX_TO_SLOT = None
_WORKER_ENTRY_SIZE = 26
_WORKER_FLAGS_SIZE = 4
_WORKER_GROUP_SIZE = 4 + 32 * 26
_WORKER_CFG = None
_WORKER_OUTPUT_DIR = None


def build_atlas(map_id, out_dir):
    cfg = MAP_CONFIGS[map_id]
    map_path = os.path.join(UOC_DIR, cfg["file"])
    print(f"[*] Reading tiledata.mul and scanning {cfg['file']} for land textures ({cfg['name']})...")
    with open(TILEDATA_FILE, "rb") as f:
        td = f.read()

    entry_size = 30 if b"VOID!!!!!!" in td[40:60] else 26
    flags_size = 8 if entry_size == 30 else 4
    group_size = 4 + 32 * entry_size

    def get_tex_id(tid):
        if tid == 0:
            return 0
        g = tid // 32
        e = tid % 32
        off = g * group_size + 4 + e * entry_size
        if off + flags_size + 2 <= len(td):
            tex_id = struct.unpack_from("<H", td, off + flags_size)[0]
            if tex_id == 0 and (168 <= tid <= 171):
                return 310
            return tex_id
        return 0

    with open(map_path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        total_blocks = cfg["w_blocks"] * cfg["h_blocks"]
        used_tiles = set()
        for b in range(0, total_blocks, 4):
            off = b * 196 + 4
            for i in range(64):
                tid = struct.unpack_from("<H", mm, off + i * 3)[0]
                used_tiles.add(tid)
        mm.close()

    tex_ids = sorted({get_tex_id(tid) for tid in used_tiles if get_tex_id(tid) > 0})
    if 310 not in tex_ids:
        tex_ids.append(310)
    tex_ids = sorted(tex_ids)

    print(f"[*] Found {len(tex_ids)} unique textures used in {cfg['file']}.")

    atlas_img = Image.new("RGB", (ATLAS_DIM, ATLAS_DIM), (15, 75, 110))
    with open(TEXIDX_FILE, "rb") as f_idx, open(TEXMAPS_FILE, "rb") as f_map:
        mm_idx = mmap.mmap(f_idx.fileno(), 0, access=mmap.ACCESS_READ)
        mm_map = mmap.mmap(f_map.fileno(), 0, access=mmap.ACCESS_READ)

        for slot_idx, tex_id in enumerate(tex_ids):
            col = slot_idx % SLOTS_PER_SIDE
            row = slot_idx // SLOTS_PER_SIDE
            px = col * CELL_RES
            py = row * CELL_RES

            idx_off = tex_id * 12
            if idx_off + 12 <= len(mm_idx):
                lookup, size, extra = struct.unpack_from("<iii", mm_idx, idx_off)
                if lookup >= 0 and size > 0 and lookup + size <= len(mm_map):
                    dim = 128 if (size == 32768 or extra == 1) else 64
                    raw_pixels = mm_map[lookup:lookup + size]
                    rgb = bytearray(dim * dim * 3)
                    for i in range(dim * dim):
                        p = struct.unpack_from("<H", raw_pixels, i * 2)[0]
                        rgb[i * 3 + 0] = ((p >> 10) & 0x1F) * 255 // 31
                        rgb[i * 3 + 1] = ((p >> 5) & 0x1F) * 255 // 31
                        rgb[i * 3 + 2] = (p & 0x1F) * 255 // 31
                    cell_img = Image.frombytes("RGB", (dim, dim), bytes(rgb))
                    if dim != CELL_RES:
                        cell_img = cell_img.resize((CELL_RES, CELL_RES), Image.Resampling.BILINEAR)
                    atlas_img.paste(cell_img, (px, py))

        mm_idx.close()
        mm_map.close()

    os.makedirs(out_dir, exist_ok=True)
    atlas_path = os.path.join(out_dir, "uo_land_atlas.png")
    print(f"[*] Saving texture atlas to {atlas_path}...")
    atlas_img.save(atlas_path, format="PNG", optimize=True)
    print(f"[✓] Atlas saved: {os.path.getsize(atlas_path) / (1024*1024):.2f} MB ({ATLAS_DIM}x{ATLAS_DIM})")

    tex_to_slot = {tid: i for i, tid in enumerate(tex_ids)}
    return tex_to_slot


def create_glb_bytes(vertices, normals, uvs, indices, aabb_min, aabb_max, relative_atlas_path="../uo_land_atlas.png"):
    num_vertices = len(vertices)

    pos_bytes = bytearray()
    for v in vertices:
        pos_bytes.extend(struct.pack("<fff", v[0], v[1], v[2]))

    norm_bytes = bytearray()
    for n in normals:
        norm_bytes.extend(struct.pack("<fff", n[0], n[1], n[2]))

    uv_bytes = bytearray()
    for uv in uvs:
        uv_bytes.extend(struct.pack("<ff", uv[0], uv[1]))

    idx_bytes = bytearray()
    for idx in indices:
        idx_bytes.extend(struct.pack("<I", idx))

    def pad4(b):
        pad = (4 - (len(b) % 4)) % 4
        return b + b"\x00" * pad

    bin_buffer = bytearray()
    pos_offset = len(bin_buffer)
    bin_buffer.extend(pad4(pos_bytes))
    norm_offset = len(bin_buffer)
    bin_buffer.extend(pad4(norm_bytes))
    uv_offset = len(bin_buffer)
    bin_buffer.extend(pad4(uv_bytes))
    idx_offset = len(bin_buffer)
    bin_buffer.extend(pad4(idx_bytes))

    gltf_json = {
        "asset": {"version": "2.0", "generator": "UO3D Multi-Map Atlas Terrain Pipeline"},
        "scene": 0,
        "scenes": [{"name": "TerrainScene", "nodes": [0]}],
        "nodes": [{"name": "TerrainNode", "mesh": 0}],
        "materials": [{
            "name": "TerrainAtlasMaterial",
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": 0},
                "metallicFactor": 0.0,
                "roughnessFactor": 0.95
            },
            "doubleSided": False
        }],
        "textures": [{"source": 0, "sampler": 0}],
        "images": [{"uri": relative_atlas_path}],
        "samplers": [{
            "magFilter": 9728,
            "minFilter": 9728,
            "wrapS": 33071,
            "wrapT": 33071
        }],
        "meshes": [{
            "name": "TerrainMesh",
            "primitives": [{
                "attributes": {
                    "POSITION": 0,
                    "NORMAL": 1,
                    "TEXCOORD_0": 2
                },
                "indices": 3,
                "material": 0
            }]
        }],
        "buffers": [{"byteLength": len(bin_buffer)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": pos_offset, "byteLength": len(pos_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": norm_offset, "byteLength": len(norm_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": uv_offset, "byteLength": len(uv_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": idx_offset, "byteLength": len(idx_bytes), "target": 34963}
        ],
        "accessors": [
            {"bufferView": 0, "byteOffset": 0, "componentType": 5126, "count": num_vertices, "type": "VEC3", "min": list(aabb_min), "max": list(aabb_max)},
            {"bufferView": 1, "byteOffset": 0, "componentType": 5126, "count": num_vertices, "type": "VEC3"},
            {"bufferView": 2, "byteOffset": 0, "componentType": 5126, "count": num_vertices, "type": "VEC2"},
            {"bufferView": 3, "byteOffset": 0, "componentType": 5125, "count": len(indices), "type": "SCALAR"}
        ]
    }

    json_bytes = json.dumps(gltf_json, separators=(",", ":")).encode("utf-8")
    pad_json = (4 - (len(json_bytes) % 4)) % 4
    json_bytes += b" " * pad_json

    total_len = 12 + 8 + len(json_bytes) + 8 + len(bin_buffer)
    out = bytearray()
    out.extend(struct.pack("<4sII", b"glTF", 2, total_len))
    out.extend(struct.pack("<II", len(json_bytes), 0x4E4F534A))
    out.extend(json_bytes)
    out.extend(struct.pack("<II", len(bin_buffer), 0x004E4942))
    out.extend(bin_buffer)
    return bytes(out)


def generate_ocean_chunk(tex_to_slot, out_dir):
    water_slot = tex_to_slot.get(310, 0)
    col = water_slot % SLOTS_PER_SIDE
    row = water_slot // SLOTS_PER_SIDE

    inv_slots = 1.0 / SLOTS_PER_SIDE
    delta = 0.5 / ATLAS_DIM
    u0 = col * inv_slots + delta
    u1 = (col + 1) * inv_slots - delta
    v0 = row * inv_slots + delta
    v1 = (row + 1) * inv_slots - delta

    vertices = []
    normals = []
    uvs = []
    indices = []
    water_z = -5.0 * V_SCALE

    for j in range(CHUNK_TILES):
        for i in range(CHUNK_TILES):
            base_v = len(vertices)
            vertices.append((i * H_SCALE, water_z, j * H_SCALE))
            vertices.append(((i + 1) * H_SCALE, water_z, j * H_SCALE))
            vertices.append((i * H_SCALE, water_z, (j + 1) * H_SCALE))
            vertices.append(((i + 1) * H_SCALE, water_z, (j + 1) * H_SCALE))

            uvs.extend([(u0, v0), (u1, v0), (u0, v1), (u1, v1)])
            for _ in range(4):
                normals.append((0.0, 1.0, 0.0))

            indices.extend([base_v + 0, base_v + 2, base_v + 1, base_v + 1, base_v + 2, base_v + 3])

    glb_bytes = create_glb_bytes(
        vertices, normals, uvs, indices,
        aabb_min=(0.0, water_z, 0.0),
        aabb_max=(CHUNK_TILES * H_SCALE, water_z, CHUNK_TILES * H_SCALE),
        relative_atlas_path="uo_land_atlas.png"
    )
    ocean_path = os.path.join(out_dir, "ocean_chunk.glb")
    with open(ocean_path, "wb") as f:
        f.write(glb_bytes)
    print(f"[✓] ocean_chunk.glb created ({os.path.getsize(ocean_path) / 1024:.1f} KB)")


def _init_worker(map_id, tex_to_slot_map, out_dir):
    global _WORKER_MM, _WORKER_TD, _WORKER_TEX_TO_SLOT, _WORKER_ENTRY_SIZE, _WORKER_FLAGS_SIZE, _WORKER_GROUP_SIZE, _WORKER_CFG, _WORKER_OUTPUT_DIR
    _WORKER_CFG = MAP_CONFIGS[map_id]
    _WORKER_OUTPUT_DIR = out_dir

    map_path = os.path.join(UOC_DIR, _WORKER_CFG["file"])
    f_map = open(map_path, "rb")
    _WORKER_MM = mmap.mmap(f_map.fileno(), 0, access=mmap.ACCESS_READ)
    with open(TILEDATA_FILE, "rb") as f_td:
        _WORKER_TD = f_td.read()

    _WORKER_ENTRY_SIZE = 30 if b"VOID!!!!!!" in _WORKER_TD[40:60] else 26
    _WORKER_FLAGS_SIZE = 8 if _WORKER_ENTRY_SIZE == 30 else 4
    _WORKER_GROUP_SIZE = 4 + 32 * _WORKER_ENTRY_SIZE
    _WORKER_TEX_TO_SLOT = tex_to_slot_map


def _process_chunk_task(task):
    cx, cy = task
    x0 = cx * CHUNK_TILES
    y0 = cy * CHUNK_TILES

    mm = _WORKER_MM
    td = _WORKER_TD
    es = _WORKER_ENTRY_SIZE
    fs = _WORKER_FLAGS_SIZE
    gs = _WORKER_GROUP_SIZE
    tex_to_slot = _WORKER_TEX_TO_SLOT
    cfg = _WORKER_CFG

    w_tiles = cfg["w_tiles"]
    h_tiles = cfg["h_tiles"]
    h_blocks = cfg["h_blocks"]

    def get_tile(wx, wy):
        cx_c = 0 if wx < 0 else (w_tiles - 1 if wx >= w_tiles else wx)
        cy_c = 0 if wy < 0 else (h_tiles - 1 if wy >= h_tiles else wy)
        bx = cx_c >> 3
        by = cy_c >> 3
        tx = cx_c & 7
        ty = cy_c & 7
        idx = (bx * h_blocks) + by
        offset = (idx * 196) + 4 + ((ty * 8) + tx) * 3
        return struct.unpack_from("<Hb", mm, offset)

    # 1. Quick uniform water test
    is_water = True
    for sy in (y0, y0 + 32, y0 + 63):
        for sx in (x0, x0 + 32, x0 + 63):
            tid, z = get_tile(sx, sy)
            if z != -5 or (tid not in WATER_TILE_IDS):
                is_water = False
                break
        if not is_water:
            break

    if is_water:
        for j in range(0, CHUNK_TILES, 4):
            for i in range(0, CHUNK_TILES, 4):
                tid, z = get_tile(x0 + i, y0 + j)
                if z != -5 or (tid not in WATER_TILE_IDS):
                    is_water = False
                    break
            if not is_water:
                break

    if is_water:
        return (cx, cy, "water", 0)

    # 2. Build Land Chunk
    sector_x = cx // SECTOR_SIZE
    sector_y = cy // SECTOR_SIZE
    sector_dir = os.path.join(_WORKER_OUTPUT_DIR, f"sector_{sector_x:02d}_{sector_y:02d}")
    os.makedirs(sector_dir, exist_ok=True)
    out_path = os.path.join(sector_dir, f"chunk_{cx}_{cy}.glb")

    inv_slots = 1.0 / SLOTS_PER_SIDE
    delta = 0.5 / ATLAS_DIM

    norm_factor_y = 4.0 * (H_SCALE ** 2)
    h_scale_2 = 2.0 * H_SCALE

    def calc_normal(wx, wy):
        ez = get_tile(wx + 1, wy)[1] * V_SCALE
        wz = get_tile(wx - 1, wy)[1] * V_SCALE
        sz = get_tile(wx, wy + 1)[1] * V_SCALE
        nz = get_tile(wx, wy - 1)[1] * V_SCALE
        nx = -(ez - wz) * h_scale_2
        ny = norm_factor_y
        nz = -(sz - nz) * h_scale_2
        l = math.sqrt(nx*nx + ny*ny + nz*nz)
        if l > 1e-6:
            inv = 1.0 / l
            return (nx * inv, ny * inv, nz * inv)
        return (0.0, 1.0, 0.0)

    vertices = []
    normals = []
    uvs = []
    indices = []

    min_x = 1e9; max_x = -1e9
    min_y = 1e9; max_y = -1e9
    min_z = 1e9; max_z = -1e9

    for j in range(CHUNK_TILES):
        wy = y0 + j
        for i in range(CHUNK_TILES):
            wx = x0 + i

            tid, z00_raw = get_tile(wx, wy)
            z10_raw = get_tile(wx + 1, wy)[1]
            z01_raw = get_tile(wx, wy + 1)[1]
            z11_raw = get_tile(wx + 1, wy + 1)[1]

            z00 = z00_raw * V_SCALE
            z10 = z10_raw * V_SCALE
            z01 = z01_raw * V_SCALE
            z11 = z11_raw * V_SCALE

            # UV coordinates in Atlas
            tex_id = 0
            if tid > 0:
                g = tid // 32
                e = tid % 32
                off = g * gs + 4 + e * es
                if off + fs + 2 <= len(td):
                    tex_id = struct.unpack_from("<H", td, off + fs)[0]
                    if tex_id == 0 and (168 <= tid <= 171):
                        tex_id = 310

            slot = tex_to_slot.get(tex_id, tex_to_slot.get(310, 0))
            col = slot % SLOTS_PER_SIDE
            row = slot // SLOTS_PER_SIDE

            u0 = col * inv_slots + delta
            u1 = (col + 1) * inv_slots - delta
            v0 = row * inv_slots + delta
            v1 = (row + 1) * inv_slots - delta

            v0_pos = (i * H_SCALE, z00, j * H_SCALE)
            v1_pos = ((i + 1) * H_SCALE, z10, j * H_SCALE)
            v2_pos = (i * H_SCALE, z01, (j + 1) * H_SCALE)
            v3_pos = ((i + 1) * H_SCALE, z11, (j + 1) * H_SCALE)

            for vp in (v0_pos, v1_pos, v2_pos, v3_pos):
                if vp[0] < min_x: min_x = vp[0]
                if vp[0] > max_x: max_x = vp[0]
                if vp[1] < min_y: min_y = vp[1]
                if vp[1] > max_y: max_y = vp[1]
                if vp[2] < min_z: min_z = vp[2]
                if vp[2] > max_z: max_z = vp[2]

            base_v = len(vertices)
            vertices.extend([v0_pos, v1_pos, v2_pos, v3_pos])
            uvs.extend([(u0, v0), (u1, v0), (u0, v1), (u1, v1)])

            normals.append(calc_normal(wx, wy))
            normals.append(calc_normal(wx + 1, wy))
            normals.append(calc_normal(wx, wy + 1))
            normals.append(calc_normal(wx + 1, wy + 1))

            indices.extend([base_v + 0, base_v + 2, base_v + 1, base_v + 1, base_v + 2, base_v + 3])

    glb_data = create_glb_bytes(
        vertices, normals, uvs, indices,
        aabb_min=(min_x, min_y, min_z),
        aabb_max=(max_x, max_y, max_z),
        relative_atlas_path="../uo_land_atlas.png"
    )
    with open(out_path, "wb") as f:
        f.write(glb_data)

    return (cx, cy, "land", len(glb_data))


def generate_map(map_id):
    cfg = MAP_CONFIGS[map_id]
    out_dir = os.path.join(BASE_OUTPUT_DIR, cfg["folder"])
    print("\n" + "=" * 64)
    print(f"=== Generating 3D Terrain for Map {map_id}: {cfg['name']} ===")
    print(f"  Dimensions: {cfg['w_tiles']}x{cfg['h_tiles']} tiles ({cfg['chunks_x']}x{cfg['chunks_y']} chunks)")
    print(f"  Output Dir: {out_dir}")
    print("=" * 64)

    t_start = time.time()
    tex_to_slot = build_atlas(map_id, out_dir)
    generate_ocean_chunk(tex_to_slot, out_dir)

    all_tasks = [(cx, cy) for cy in range(cfg["chunks_y"]) for cx in range(cfg["chunks_x"])]
    total = len(all_tasks)
    print(f"[*] Processing all {total} chunks across 16 CPU workers...")

    water_count = 0
    land_count = 0
    total_bytes = 0
    chunk_manifest = {}

    with ProcessPoolExecutor(max_workers=16, initializer=_init_worker, initargs=(map_id, tex_to_slot, out_dir)) as executor:
        futures = {executor.submit(_process_chunk_task, t): t for t in all_tasks}
        completed = 0
        last_print = time.time()

        for future in as_completed(futures):
            cx, cy, ctype, sz = future.result()
            completed += 1
            if ctype == "water":
                water_count += 1
                chunk_manifest[f"{cx}_{cy}"] = "water"
            else:
                land_count += 1
                total_bytes += sz
                sx = cx // SECTOR_SIZE
                sy = cy // SECTOR_SIZE
                chunk_manifest[f"{cx}_{cy}"] = f"sector_{sx:02d}_{sy:02d}/chunk_{cx}_{cy}.glb"

            if time.time() - last_print >= 2.0 or completed == total:
                elapsed = time.time() - t_start
                rate = completed / max(elapsed, 0.1)
                print(f"  [{completed:4d}/{total:4d}] {completed*100/total:5.1f}% | Land: {land_count:4d}, Water: {water_count:4d} ({rate:.1f} chunks/s)")
                last_print = time.time()

    manifest_data = {
        "map_id": map_id,
        "name": cfg["name"],
        "world_chunks_x": cfg["chunks_x"],
        "world_chunks_y": cfg["chunks_y"],
        "chunk_tiles": CHUNK_TILES,
        "sector_size": SECTOR_SIZE,
        "h_scale": H_SCALE,
        "v_scale": V_SCALE,
        "total_chunks": total,
        "land_chunks": land_count,
        "water_chunks": water_count,
        "total_land_size_mb": total_bytes / (1024 * 1024),
        "chunks": chunk_manifest
    }
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f, indent=2)

    total_time = time.time() - t_start
    print(f"\n[✓✓✓] Map {map_id} ({cfg['name']}) Finished in {total_time:.2f}s!")
    print(f"      Land Chunks: {land_count} ({total_bytes / (1024*1024):.1f} MB), Water Chunks: {water_count}")


def main():
    parser = argparse.ArgumentParser(description="Generate 3D Terrain Chunks for UO Maps 1..5")
    parser.add_argument("--map", type=int, choices=[1, 2, 3, 4, 5], help="Specific map ID to generate (1=Trammel, 2=Ilshenar, 3=Malas, 4=Tokuno, 5=TerMur)")
    parser.add_argument("--all", action="store_true", help="Generate all maps 1 through 5 in sequence")
    args = parser.parse_args()

    if args.all:
        for m in (2, 3, 4, 5, 1):
            generate_map(m)
    elif args.map is not None:
        generate_map(args.map)
    else:
        print("Usage: python3 generate_multi_map_terrain.py --map <1..5>  OR  --all")


if __name__ == "__main__":
    main()
