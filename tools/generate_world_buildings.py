"""
Ultima Online Britannia World 3D Architectural Pipeline (Multiprocessing)
Generates watertight, pure 3D architecture for all cities and settlements across Britannia.
Uses 16 CPU cores in parallel to generate ~1,000 architectural chunks in seconds.
"""

import sys
import os
import math
import struct
import json
import time
from multiprocessing import Pool, set_start_method, cpu_count

TILEDATA_FILE = "/opt/hd_jogos/UOC/tiledata.mul"
STAIDX_FILE = "/opt/hd_jogos/UOC/staidx0.mul"
STATICS_FILE = "/opt/hd_jogos/UOC/statics0.mul"
WALLS_TXT = "/opt/hd_jogos/UOC/walls.txt"
OUTPUT_DIR = "/home/mnunes/uo3d_map/godot_project/buildings"

V_SCALE = 0.12
H_SCALE = 1.0
WALL_THICKNESS = 0.35
CHUNK_TILES = 64

WORLD_WIDTH_CHUNKS = 112
WORLD_HEIGHT_CHUNKS = 64

# True Pitched Roof Slopes & Ridges
ROOF_SLOPE_SOUTH = {1443, 1449, 1488, 1450, 1460, 1462}
ROOF_SLOPE_NORTH = {1442, 1447, 1487, 1454, 1466}
ROOF_SLOPE_EAST  = {1431, 1446, 1476, 1481, 1456, 1467}
ROOF_SLOPE_WEST  = {1430, 1444, 1475, 1482, 1457, 1471}

ROOF_RIDGE_EW    = {1441, 1448, 1486, 1464, 1468}
ROOF_RIDGE_NS    = {1429, 1445, 1474, 1406, 1458, 1470}

ROOF_VALLEY_RISE_NE = {1434, 1479}
ROOF_VALLEY_FALL_SE = {1432, 1477}
ROOF_VALLEY_CAP     = {1439, 1483}

ROOF_HIP_SOUTH   = {1435, 1480, 1451}
ROOF_HIP_NORTH   = {1433, 1478, 1453}
ROOF_HIP_CAP     = {1440}

# Flat slate/stone slabs (Mausoleums, crypts, flat ceilings)
FLAT_SLATE_ROOF = {1407, 1408, 1409, 1410, 1411, 1412, 1413, 1404, 1405}

ALL_ROOF_IDS = (ROOF_SLOPE_SOUTH | ROOF_SLOPE_NORTH | ROOF_SLOPE_EAST | ROOF_SLOPE_WEST |
                ROOF_RIDGE_EW | ROOF_RIDGE_NS | ROOF_VALLEY_RISE_NE | ROOF_VALLEY_FALL_SE |
                ROOF_VALLEY_CAP | ROOF_HIP_SOUTH | ROOF_HIP_NORTH | ROOF_HIP_CAP | FLAT_SLATE_ROOF)

GABLE_TRIM_IDS = {24, 25, 66, 67, 82, 83, 84, 85, 86, 193, 194, 221, 222, 230, 231, 330, 331, 2264, 2265}

# Fences and Gates (Hollow 3D Bars & Rails)
IRON_FENCE_NS   = {2121}
IRON_FENCE_EW   = {2123}
IRON_FENCE_POST = {2122}

WOOD_FENCE_NS   = {2103, 2142, 2145, 2148}
WOOD_FENCE_EW   = {2102, 2141, 2144, 2147}
WOOD_FENCE_POST = {2101, 2140, 2143, 2149}

ALL_FENCE_IDS = (IRON_FENCE_NS | IRON_FENCE_EW | IRON_FENCE_POST |
                 WOOD_FENCE_NS | WOOD_FENCE_EW | WOOD_FENCE_POST)

# Bridge Structures & Stone Rails
WOODEN_BRIDGE_FLOORS = {1993, 1994, 1995, 1996, 1997, 1998, 1999, 2000}
BRIDGE_STONE_BLOCKS  = {1872, 1822, 1801, 1894, 1895}
BRIDGE_PARAPET_WALLS = {49, 120}
BRIDGE_SOUTH_RAILS   = {2294, 2295, 2297, 2299, 2283, 2285, 2289}
BRIDGE_EAST_RAILS    = {2293, 2296, 2298, 2300, 2284, 2286, 2290}

CASTLE_SOUTH_WALLS = {128, 129, 720, 722, 726, 727}
CASTLE_EAST_WALLS  = {130, 132, 723, 725, 728, 729}
CASTLE_CORNERS     = {724}
CASTLE_POSTS       = {721}

ARCH_IDS = {134, 135, 138, 139, 206, 207, 208, 209, 213, 214, 224, 70, 73}
WINDOW_IDS = {131, 133, 59, 60, 93, 94, 186, 187, 202, 203}


def load_wall_classifications():
    south_walls = set(CASTLE_SOUTH_WALLS) | set(BRIDGE_SOUTH_RAILS)
    east_walls = set(CASTLE_EAST_WALLS) | set(BRIDGE_EAST_RAILS)
    corners = set(CASTLE_CORNERS)
    posts = set(CASTLE_POSTS)
    if os.path.exists(WALLS_TXT):
        with open(WALLS_TXT, "r") as f:
            for line in f.readlines()[2:]:
                p = line.strip().split("\t")
                if len(p) >= 11:
                    for c in (3, 4, 5, 11, 12, 15):
                        v = int(p[c])
                        if v > 0: south_walls.add(v)
                    for c in (7, 8, 9, 13, 14, 16):
                        v = int(p[c])
                        if v > 0: east_walls.add(v)
                    c_val = int(p[6])
                    if c_val > 0: corners.add(c_val)
                    p_val = int(p[10])
                    if p_val > 0: posts.add(p_val)
    return south_walls, east_walls, corners, posts


def write_glb(output_path, vertices, normals, indices):
    num_vertices = len(vertices)
    if num_vertices == 0 or len(indices) == 0:
        return

    min_pos = [min(v[i] for v in vertices) for i in range(3)]
    max_pos = [max(v[i] for v in vertices) for i in range(3)]

    pos_bytes = bytearray()
    for v in vertices:
        pos_bytes.extend(struct.pack("<fff", v[0], v[1], v[2]))

    norm_bytes = bytearray()
    for n in normals:
        norm_bytes.extend(struct.pack("<fff", n[0], n[1], n[2]))

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
    idx_offset = len(bin_buffer)
    bin_buffer.extend(pad4(idx_bytes))

    gltf_json = {
        "asset": {"version": "2.0", "generator": "UO3D Britannia Pure Architecture Pipeline"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "BritanniaBuildingsMesh"}],
        "materials": [{
            "name": "ClayStoneMaterial",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.92, 0.92, 0.92, 1.0],
                "metallicFactor": 0.05,
                "roughnessFactor": 0.85
            },
            "doubleSided": True
        }],
        "meshes": [{
            "name": "BritanniaBuildingsMesh",
            "primitives": [{
                "attributes": {
                    "POSITION": 0,
                    "NORMAL": 1
                },
                "indices": 2,
                "material": 0
            }]
        }],
        "buffers": [{
            "byteLength": len(bin_buffer)
        }],
        "bufferViews": [
            {
                "buffer": 0,
                "byteOffset": pos_offset,
                "byteLength": len(pos_bytes),
                "target": 34962
            },
            {
                "buffer": 0,
                "byteOffset": norm_offset,
                "byteLength": len(norm_bytes),
                "target": 34962
            },
            {
                "buffer": 0,
                "byteOffset": idx_offset,
                "byteLength": len(idx_bytes),
                "target": 34963
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "byteOffset": 0,
                "componentType": 5126,
                "count": num_vertices,
                "type": "VEC3",
                "min": min_pos,
                "max": max_pos
            },
            {
                "bufferView": 1,
                "byteOffset": 0,
                "componentType": 5126,
                "count": num_vertices,
                "type": "VEC3"
            },
            {
                "bufferView": 2,
                "byteOffset": 0,
                "componentType": 5125,
                "count": len(indices),
                "type": "SCALAR"
            }
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

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(out)


# Globals for multiprocessing workers (inherited via fork)
G_TD = None
G_STAIDX = None
G_STATICS = None
G_WORLD_WALLS = None
G_SOUTH_WALLS = None
G_EAST_WALLS = None
G_CORNERS = None
G_POSTS = None


def get_item_info_fast(item_id):
    land_size = 493568
    item_size = 41
    grp_size = 4 + 32 * item_size
    g = item_id // 32
    e = item_id % 32
    off = land_size + g * grp_size + 4 + e * item_size
    if off + 21 <= len(G_TD):
        fl = struct.unpack_from("<Q", G_TD, off)[0]
        height = G_TD[off + 20]
        name = G_TD[off+21:off+41].split(b"\x00")[0].decode("ascii", errors="replace").lower()
        return fl, height, name
    return 0, 0, ""


def process_world_chunk(args):
    cx, cy = args
    x0_world = cx * CHUNK_TILES
    y0_world = cy * CHUNK_TILES
    bx0 = cx * 8
    by0 = cy * 8

    raw_chunk_items = []
    stairs_by_coord = {}
    roof_corner_y = {}
    roof_tiles_coords = set()
    bridge_blocks_by_coord = {}
    parapet_blocks_by_coord = {}

    for by in range(by0, by0 + 8):
        for bx in range(bx0, bx0 + 8):
            b_idx = bx * 512 + by
            lookup = b_idx * 12
            offset, length, _ = struct.unpack_from("<iii", G_STAIDX, lookup)
            if offset >= 0 and length > 0:
                for i in range(length // 7):
                    item_id, x, y, z, hue = struct.unpack_from("<HBBbH", G_STATICS, offset + i * 7)
                    wx = bx * 8 + x
                    wy = by * 8 + y
                    fl, h, name = get_item_info_fast(item_id)

                    if (fl & 0x20000) or any(w in name for w in (
                        "tree", "water", "grasses", "leaves", "brambles", "vines", "flowers",
                        "snowdrops", "campion", "foxglove", "orfluer", "table", "chair", "throne",
                        "bench", "stool", "bed", "counter", "case", "desk", "chest", "box", "crate",
                        "barrel", "keg", "banner", "flag", "torch", "sconce", "statue", "fountain",
                        "altar", "forge", "anvil", "carpet", "rug", "tapestry", "hedge", "clock",
                        "mirror", "shield", "portrait", "painting", "debris", "rubble", "rock"
                    )):
                        if item_id not in (1872, 1822, 1801, 1846, 1847, 1848, 1849, 1850, 1851, 1873, 1874, 1875, 1876, 1823, 1826, 1827, 1828, 1829):
                            continue

                    is_stair = ("stair" in name) or ("step" in name) or ((fl & 0x400) != 0 and "ladder" not in name and item_id not in BRIDGE_STONE_BLOCKS)
                    if is_stair and item_id not in BRIDGE_STONE_BLOCKS:
                        direction = (fl >> 30) & 3
                        if item_id in (1873, 1849, 1823, 1826): direction = 0
                        elif item_id in (1876, 1829, 1852): direction = 1
                        elif item_id in (1874, 1846, 1850, 1827): direction = 2
                        elif item_id in (1875, 1847, 1851, 1828): direction = 3
                        if (wx, wy) not in stairs_by_coord:
                            stairs_by_coord[(wx, wy)] = []
                        stairs_by_coord[(wx, wy)].append((z, h, direction))

                    is_pitched_roof = (("roof" in name) or ("shingle" in name) or (item_id in ALL_ROOF_IDS)) and (item_id not in FLAT_SLATE_ROOF)
                    if is_pitched_roof:
                        r_lx = wx - x0_world
                        r_ly = wy - y0_world
                        r_yb = z * V_SCALE
                        step = 3.0 * V_SCALE
                        roof_tiles_coords.add((wx, wy))

                        if item_id in ROOF_SLOPE_SOUTH:
                            cnw, cne, csw, cse = r_yb, r_yb, r_yb + step, r_yb + step
                        elif item_id in ROOF_SLOPE_NORTH:
                            cnw, cne, csw, cse = r_yb + step, r_yb + step, r_yb, r_yb
                        elif item_id in ROOF_SLOPE_EAST:
                            cnw, cne, csw, cse = r_yb, r_yb + step, r_yb, r_yb + step
                        elif item_id in ROOF_SLOPE_WEST:
                            cnw, cne, csw, cse = r_yb + step, r_yb, r_yb + step, r_yb
                        elif item_id in ROOF_RIDGE_EW:
                            cnw, cne, csw, cse = r_yb, r_yb, r_yb, r_yb
                        elif item_id in ROOF_RIDGE_NS:
                            cnw, cne, csw, cse = r_yb, r_yb, r_yb, r_yb
                        elif item_id in ROOF_HIP_SOUTH:
                            cnw, cne, csw, cse = r_yb, r_yb, r_yb + step, r_yb + step
                        elif item_id in ROOF_HIP_NORTH:
                            cnw, cne, csw, cse = r_yb + step, r_yb + step, r_yb, r_yb
                        else:
                            cnw = cne = csw = cse = r_yb

                        for c_coord, elev in [
                            ((r_lx, r_ly), cnw),
                            ((r_lx + 1, r_ly), cne),
                            ((r_lx, r_ly + 1), csw),
                            ((r_lx + 1, r_ly + 1), cse)
                        ]:
                            if c_coord not in roof_corner_y or elev > roof_corner_y[c_coord]:
                                roof_corner_y[c_coord] = elev

                    if item_id in BRIDGE_STONE_BLOCKS:
                        bridge_blocks_by_coord[(wx, wy)] = z
                    if item_id in BRIDGE_PARAPET_WALLS:
                        parapet_blocks_by_coord[(wx, wy)] = z

                    raw_chunk_items.append((item_id, wx, wy, z, h, fl, name))

    if not raw_chunk_items:
        return (cx, cy, 0, 0)

    # Stair flight lowest elevation index
    stair_flight_base_z = {}
    for (wx, wy), s_list in stairs_by_coord.items():
        curr_z = min(s[0] for s in s_list)
        min_z = curr_z
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                nc = (wx + dx, wy + dy)
                if nc in stairs_by_coord:
                    for nz, nh, nd in stairs_by_coord[nc]:
                        if abs(nz - curr_z) <= 25 and nz < min_z:
                            min_z = nz
        stair_flight_base_z[(wx, wy)] = min_z

    chunk_items = []
    for item_id, wx, wy, z, h, fl, name in raw_chunk_items:
        is_stair = ("stair" in name) or ("step" in name) or ((fl & 0x400) != 0 and "ladder" not in name and item_id not in BRIDGE_STONE_BLOCKS)

        if item_id in (1822, 1872, 1801, 1848):
            is_near_stair = False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if (wx + dx, wy + dy) in stairs_by_coord:
                        is_near_stair = True
                        break
                if is_near_stair:
                    break
            if is_near_stair:
                continue

        if item_id in GABLE_TRIM_IDS and (z >= 20 or (wx, wy) in roof_tiles_coords):
            continue

        is_fence = (item_id in ALL_FENCE_IDS) or ("fence" in name) or ("bars" in name)
        is_roof = ("roof" in name) or ("shingle" in name) or (item_id in ALL_ROOF_IDS)
        is_arch = (item_id in ARCH_IDS) or ("arch" in name)
        is_window = (item_id in WINDOW_IDS) or ("window" in name and ((fl & 0x10) != 0))
        is_column = ("pillar" in name) or ("column" in name) or ("pier" in name)
        is_wall = ((fl & 0x10) != 0) or ("wall" in name) or (item_id in G_SOUTH_WALLS) or (item_id in G_EAST_WALLS) or (item_id in G_CORNERS) or (item_id in G_POSTS)
        is_bridge = (item_id in WOODEN_BRIDGE_FLOORS) or (item_id in BRIDGE_STONE_BLOCKS) or (item_id in BRIDGE_PARAPET_WALLS) or ("bridge" in name)
        is_floor = ((("cobblestone" in name) or ("paver" in name) or ("board" in name) or ("plank" in name) or
                     ("floor" in name) or (name == "stone roof") or (item_id in WOODEN_BRIDGE_FLOORS)) and
                    not any(w in name for w in ("carpet", "rug", "table", "chair", "case", "desk", "bench", "counter")))

        if not (is_fence or is_roof or is_arch or is_window or is_column or is_stair or is_wall or is_bridge or is_floor):
            continue

        lx = wx - x0_world
        ly = wy - y0_world
        chunk_items.append((item_id, wx, wy, lx, ly, z, h, fl, name, is_fence, is_roof, is_arch, is_window, is_column, is_stair, is_wall, is_bridge, is_floor))

    if not chunk_items:
        return (cx, cy, 0, 0)

    vertices = []
    normals = []
    indices = []

    def add_quad(p0, p1, p2, p3, n):
        base = len(vertices)
        vertices.extend([p0, p1, p2, p3])
        normals.extend([n, n, n, n])
        indices.extend([base + 0, base + 2, base + 1, base + 1, base + 2, base + 3])

    def add_tri(p0, p1, p2, n):
        base = len(vertices)
        vertices.extend([p0, p1, p2])
        normals.extend([n, n, n])
        indices.extend([base + 0, base + 1, base + 2])

    def add_box(bx0, bx1, by0, by1, bz0, bz1):
        add_quad((bx0, by1, bz0), (bx1, by1, bz0), (bx0, by1, bz1), (bx1, by1, bz1), (0.0, 1.0, 0.0))
        add_quad((bx0, by0, bz1), (bx1, by0, bz1), (bx0, by0, bz0), (bx1, by0, bz0), (0.0, -1.0, 0.0))
        add_quad((bx0, by0, bz0), (bx1, by0, bz0), (bx0, by1, bz0), (bx1, by1, bz0), (0.0, 0.0, -1.0))
        add_quad((bx1, by0, bz1), (bx0, by0, bz1), (bx1, by1, bz1), (bx0, by1, bz1), (0.0, 0.0, 1.0))
        add_quad((bx0, by0, bz1), (bx0, by0, bz0), (bx0, by1, bz1), (bx0, by1, bz0), (-1.0, 0.0, 0.0))
        add_quad((bx1, by0, bz0), (bx1, by0, bz1), (bx1, by1, bz0), (bx1, by1, bz1), (1.0, 0.0, 0.0))

    def add_sloped_wall_south(bx0, bx1, by_bot, yt0, yt1, wz0, wz1):
        if abs(yt0 - yt1) < 0.01:
            add_box(bx0, bx1, by_bot, max(yt0, by_bot), wz0, wz1)
            return
        add_quad((bx0, yt0, wz0), (bx1, yt1, wz0), (bx0, yt0, wz1), (bx1, yt1, wz1), (0.0, 1.0, 0.0))
        add_quad((bx0, by_bot, wz1), (bx1, by_bot, wz1), (bx0, by_bot, wz0), (bx1, by_bot, wz0), (0.0, -1.0, 0.0))
        add_quad((bx0, by_bot, wz0), (bx1, by_bot, wz0), (bx0, yt0, wz0), (bx1, yt1, wz0), (0.0, 0.0, -1.0))
        add_quad((bx1, by_bot, wz1), (bx0, by_bot, wz1), (bx1, yt1, wz1), (bx0, yt0, wz1), (0.0, 0.0, 1.0))
        add_quad((bx0, by_bot, wz1), (bx0, by_bot, wz0), (bx0, yt0, wz1), (bx0, yt0, wz0), (-1.0, 0.0, 0.0))
        add_quad((bx1, by_bot, wz0), (bx1, by_bot, wz1), (bx1, yt1, wz0), (bx1, yt1, wz1), (1.0, 0.0, 0.0))

    def add_sloped_wall_east(bz0, bz1, by_bot, yt0, yt1, wx0, wx1):
        if abs(yt0 - yt1) < 0.01:
            add_box(wx0, wx1, by_bot, max(yt0, by_bot), bz0, bz1)
            return
        add_quad((wx0, yt0, bz0), (wx1, yt0, bz0), (wx0, yt1, bz1), (wx1, yt1, bz1), (0.0, 1.0, 0.0))
        add_quad((wx0, by_bot, bz1), (wx1, by_bot, bz1), (wx0, by_bot, bz0), (wx1, by_bot, bz0), (0.0, -1.0, 0.0))
        add_quad((wx0, by_bot, bz0), (wx1, by_bot, bz0), (wx0, yt0, bz0), (wx1, yt0, bz0), (0.0, 0.0, -1.0))
        add_quad((wx1, by_bot, bz1), (wx0, by_bot, bz1), (wx1, yt1, bz1), (wx0, yt1, bz1), (0.0, 0.0, 1.0))
        add_quad((wx0, by_bot, bz1), (wx0, by_bot, bz0), (wx0, yt1, bz1), (wx0, yt0, bz0), (-1.0, 0.0, 0.0))
        add_quad((wx1, by_bot, bz0), (wx1, by_bot, bz1), (wx1, yt0, bz0), (wx1, yt1, bz1), (1.0, 0.0, 0.0))

    def add_stair_steps(x0, x1, z0, z1, y_base, y_high, y_flank_base, direction, has_side_neg=True, has_side_pos=True):
        num_steps = 4
        h_step = (y_high - y_base) / num_steps
        if direction == 0:  # Ascends North (-Z)
            for k in range(num_steps):
                sz1 = z1 - k * 0.25
                sz0 = z1 - (k + 1) * 0.25
                yk = y_base + (k + 1) * h_step
                y_prev = y_base + k * h_step
                add_quad((x0, yk, sz0), (x1, yk, sz0), (x0, yk, sz1), (x1, yk, sz1), (0.0, 1.0, 0.0))
                add_quad((x0, yk, sz1), (x1, yk, sz1), (x0, y_prev, sz1), (x1, y_prev, sz1), (0.0, 0.0, 1.0))
                if has_side_neg:
                    add_quad((x0, yk, sz0), (x0, yk, sz1), (x0, y_flank_base, sz0), (x0, y_flank_base, sz1), (-1.0, 0.0, 0.0))
                if has_side_pos:
                    add_quad((x1, yk, sz1), (x1, yk, sz0), (x1, y_flank_base, sz1), (x1, y_flank_base, sz0), (1.0, 0.0, 0.0))
            add_quad((x1, y_high, z0), (x0, y_high, z0), (x1, y_base, z0), (x0, y_base, z0), (0.0, 0.0, -1.0))

        elif direction == 1:  # Ascends East (+X)
            for k in range(num_steps):
                sx0 = x0 + k * 0.25
                sx1 = x0 + (k + 1) * 0.25
                yk = y_base + (k + 1) * h_step
                y_prev = y_base + k * h_step
                add_quad((sx0, yk, z0), (sx1, yk, z0), (sx0, yk, z1), (sx1, yk, z1), (0.0, 1.0, 0.0))
                add_quad((sx0, yk, z0), (sx0, yk, z1), (sx0, y_prev, z0), (sx0, y_prev, z1), (-1.0, 0.0, 0.0))
                if has_side_neg:
                    add_quad((sx1, yk, z0), (sx0, yk, z0), (sx1, y_flank_base, z0), (sx0, y_flank_base, z0), (0.0, 0.0, -1.0))
                if has_side_pos:
                    add_quad((sx0, yk, z1), (sx1, yk, z1), (sx0, y_flank_base, z1), (sx1, y_flank_base, z1), (0.0, 0.0, 1.0))
            add_quad((x1, y_high, z0), (x1, y_high, z1), (x1, y_base, z0), (x1, y_base, z1), (1.0, 0.0, 0.0))

        elif direction == 2:  # Ascends West (-X)
            for k in range(num_steps):
                sx1 = x1 - k * 0.25
                sx0 = x1 - (k + 1) * 0.25
                yk = y_base + (k + 1) * h_step
                y_prev = y_base + k * h_step
                add_quad((sx0, yk, z0), (sx1, yk, z0), (sx0, yk, z1), (sx1, yk, z1), (0.0, 1.0, 0.0))
                add_quad((sx1, yk, z0), (sx1, yk, z1), (sx1, y_prev, z0), (sx1, y_prev, z1), (1.0, 0.0, 0.0))
                if has_side_neg:
                    add_quad((sx0, yk, z0), (sx1, yk, z0), (sx0, y_flank_base, z0), (sx1, y_flank_base, z0), (0.0, 0.0, -1.0))
                if has_side_pos:
                    add_quad((sx1, yk, z1), (sx0, yk, z1), (sx1, y_flank_base, z1), (sx0, y_flank_base, z1), (0.0, 0.0, 1.0))
            add_quad((x0, y_high, z1), (x0, y_high, z0), (x0, y_base, z1), (x0, y_base, z0), (-1.0, 0.0, 0.0))

        else:  # Ascends South (+Z)
            for k in range(num_steps):
                sz0 = z0 + k * 0.25
                sz1 = z0 + (k + 1) * 0.25
                yk = y_base + (k + 1) * h_step
                y_prev = y_base + k * h_step
                add_quad((x0, yk, sz0), (x1, yk, sz0), (x0, yk, sz1), (x1, yk, sz1), (0.0, 1.0, 0.0))
                add_quad((x1, yk, sz0), (x0, yk, sz0), (x1, y_prev, sz0), (x0, y_prev, sz0), (0.0, 0.0, -1.0))
                if has_side_neg:
                    add_quad((x0, yk, sz1), (x0, yk, sz0), (x0, y_flank_base, sz1), (x0, y_flank_base, sz0), (-1.0, 0.0, 0.0))
                if has_side_pos:
                    add_quad((x1, yk, sz0), (x1, yk, sz1), (x1, y_flank_base, sz0), (x1, y_flank_base, sz1), (1.0, 0.0, 0.0))
            add_quad((x0, y_high, z1), (x1, y_high, z1), (x0, y_base, z1), (x1, y_base, z1), (0.0, 0.0, 1.0))

    def add_gothic_spearhead(bx, y_top, bz, bar_w, h_spear=0.08):
        tip = (bx, y_top + h_spear, bz)
        p0 = (bx - bar_w, y_top, bz - bar_w)
        p1 = (bx + bar_w, y_top, bz - bar_w)
        p2 = (bx + bar_w, y_top, bz + bar_w)
        p3 = (bx - bar_w, y_top, bz + bar_w)
        add_tri(p0, p1, tip, (0.0, 0.707, -0.707))
        add_tri(p1, p2, tip, (0.707, 0.707, 0.0))
        add_tri(p2, p3, tip, (0.0, 0.707, 0.707))
        add_tri(p3, p0, tip, (-0.707, 0.707, 0.0))

    def add_hollow_fence(x0, x1, z0, z1, y_base, y_top, is_along_x, is_iron):
        bar_w = 0.015 if is_iron else 0.03
        num_pickets = 4
        if is_along_x:
            wz = z1 - 0.04
            add_box(x0, x1, y_base + 0.05, y_base + 0.10, wz - 0.02, wz + 0.02)
            add_box(x0, x1, y_top - 0.08, y_top - 0.03, wz - 0.02, wz + 0.02)
            step_x = (x1 - x0) / num_pickets
            for i in range(num_pickets):
                bx = x0 + (i + 0.5) * step_x
                add_box(bx - bar_w, bx + bar_w, y_base, y_top, wz - bar_w, wz + bar_w)
                if is_iron:
                    add_gothic_spearhead(bx, y_top, wz, bar_w)
        else:
            wx_pos = x1 - 0.04
            add_box(wx_pos - 0.02, wx_pos + 0.02, y_base + 0.05, y_base + 0.10, z0, z1)
            add_box(wx_pos - 0.02, wx_pos + 0.02, y_top - 0.08, y_top - 0.03, z0, z1)
            step_z = (z1 - z0) / num_pickets
            for i in range(num_pickets):
                bz = z0 + (i + 0.5) * step_z
                add_box(wx_pos - bar_w, wx_pos + bar_w, y_base, y_top, bz - bar_w, bz + bar_w)
                if is_iron:
                    add_gothic_spearhead(wx_pos, y_top, bz, bar_w)

    for item in chunk_items:
        item_id, wx, wy, lx, ly, z, eff_h, fl, name, is_fence, is_roof, is_arch, is_window, is_column, is_stair, is_wall, is_bridge, is_floor = item

        y_base = z * V_SCALE
        y_top = (z + eff_h) * V_SCALE
        x0 = lx * H_SCALE
        x1 = (lx + 1.0) * H_SCALE
        z0 = ly * H_SCALE
        z1 = (ly + 1.0) * H_SCALE

        if is_fence:
            is_iron = ("iron" in name) or ("metal" in name) or (item_id in (2121, 2122, 2123))
            is_post_fence = (item_id in (2122, 2101, 2140, 2143, 2149)) or ("post" in name)
            if is_post_fence:
                pw = 0.04 if is_iron else 0.08
                add_box(x1 - pw, x1 + pw, y_base, y_top + 0.05, z1 - pw, z1 + pw)
            else:
                is_along_x = (item_id in IRON_FENCE_EW) or (item_id in WOOD_FENCE_EW) or ("south" in name)
                add_hollow_fence(x0, x1, z0, z1, y_base, y_top, is_along_x, is_iron)
            continue

        if is_bridge:
            if item_id in WOODEN_BRIDGE_FLOORS or ("bridge" in name and not is_wall):
                add_box(x0, x1, y_base, y_base + 0.15, z0, z1)
                continue

            if item_id in BRIDGE_PARAPET_WALLS or (item_id in (222, 221) and (wx, wy) in bridge_blocks_by_coord):
                has_x_neighbor = ((wx - 1, wy) in bridge_blocks_by_coord) or ((wx + 1, wy) in bridge_blocks_by_coord) or ((wx - 1, wy) in parapet_blocks_by_coord) or ((wx + 1, wy) in parapet_blocks_by_coord)
                para_h = max(eff_h, 3) * V_SCALE
                if has_x_neighbor:
                    add_box(x0, x1, y_base, y_base + para_h, z1 - 0.25, z1)
                else:
                    add_box(x1 - 0.25, x1, y_base, y_base + para_h, z0, z1)
                continue

            if item_id in BRIDGE_STONE_BLOCKS:
                if (wx, wy) in stairs_by_coord:
                    continue
                add_box(x0 + 0.05, x1 - 0.05, y_base, y_top, z0 + 0.05, z1 - 0.05)
                continue

        if is_floor and not is_wall and not is_stair and not is_arch:
            fy = y_base + 0.02
            add_quad((x0, fy, z0), (x1, fy, z0), (x0, fy, z1), (x1, fy, z1), (0.0, 1.0, 0.0))
            continue

        if is_arch:
            is_south = item_id in (134, 138, 208, 209, 70) or "south" in name
            arch_h = max(eff_h, 18)
            y_lintel_bot = (z + arch_h * 0.70) * V_SCALE
            y_lintel_top = (z + arch_h) * V_SCALE
            if is_south:
                wz0 = z1 - WALL_THICKNESS
                wz1 = z1
                add_box(x0, x1, y_lintel_bot, y_lintel_top, wz0, wz1)
                add_box(x0, x0 + 0.20, y_base, y_lintel_bot, wz0, wz1)
                add_box(x1 - 0.20, x1, y_base, y_lintel_bot, wz0, wz1)
            else:
                wx0 = x1 - WALL_THICKNESS
                wx1 = x1
                add_box(wx0, wx1, y_lintel_bot, y_lintel_top, z0, z1)
                add_box(wx0, wx1, y_base, y_lintel_bot, z0, z0 + 0.20)
                add_box(wx0, wx1, y_base, y_lintel_bot, z1 - 0.20, z1)
            continue

        if is_window:
            is_south = item_id in (131, 59, 93, 186, 202) or item_id in G_SOUTH_WALLS or (item_id not in G_EAST_WALLS)
            y_sill = (z + eff_h * 0.35) * V_SCALE
            y_lintel = (z + eff_h * 0.75) * V_SCALE
            if is_south:
                wz0 = z1 - WALL_THICKNESS
                wz1 = z1
                add_box(x0, x1, y_base, y_sill, wz0, wz1)
                add_box(x0, x1, y_lintel, y_top, wz0, wz1)
                add_box(x0, x0 + 0.25, y_sill, y_lintel, wz0, wz1)
                add_box(x1 - 0.25, x1, y_sill, y_lintel, wz0, wz1)
            else:
                wx0 = x1 - WALL_THICKNESS
                wx1 = x1
                add_box(wx0, wx1, y_base, y_sill, z0, z1)
                add_box(wx0, wx1, y_lintel, y_top, z0, z1)
                add_box(wx0, wx1, y_sill, y_lintel, z0, z0 + 0.25)
                add_box(wx0, wx1, y_sill, y_lintel, z1 - 0.25, z1)
            continue

        if is_stair and item_id not in BRIDGE_STONE_BLOCKS:
            stair_h = max(eff_h, 5) * V_SCALE
            y_high = y_base + stair_h
            min_flight_z = stair_flight_base_z.get((wx, wy), z)
            y_flank_base = min_flight_z * V_SCALE

            direction = (fl >> 30) & 3
            if item_id in (1873, 1849, 1823, 1826): direction = 0
            elif item_id in (1876, 1829, 1852): direction = 1
            elif item_id in (1874, 1846, 1850, 1827): direction = 2
            elif item_id in (1875, 1847, 1851, 1828): direction = 3

            if direction in (1, 2):
                neg_coord = (wx, wy - 1)
                pos_coord = (wx, wy + 1)
            else:
                neg_coord = (wx - 1, wy)
                pos_coord = (wx + 1, wy)

            has_side_neg = not (neg_coord in stairs_by_coord)
            has_side_pos = not (pos_coord in stairs_by_coord)

            add_stair_steps(x0, x1, z0, z1, y_base, y_high, y_flank_base, direction, has_side_neg, has_side_pos)
            continue

        if is_column:
            add_box(x0, x1, y_base, y_top, z0, z1)
            continue

        if is_roof:
            step = 3.0 * V_SCALE

            if item_id in FLAT_SLATE_ROOF or (name == "stone roof"):
                fy = y_base + 0.02
                add_quad((x0, fy, z0), (x1, fy, z0), (x0, fy, z1), (x1, fy, z1), (0.0, 1.0, 0.0))

            elif item_id in ROOF_VALLEY_RISE_NE:
                p_nw = (x0, y_base, z0)
                p_se = (x1, y_base + step, z1)
                p_sw = (x0, y_base + step, z1)
                p_ne = (x1, y_base + step, z0)
                add_tri(p_nw, p_sw, p_se, (-0.287, 0.958, 0.0))
                add_tri(p_nw, p_se, p_ne, (0.0, 0.958, -0.287))

            elif item_id in ROOF_VALLEY_FALL_SE:
                p_ne = (x1, y_base + step, z0)
                p_sw = (x0, y_base, z1)
                p_nw = (x0, y_base + step, z0)
                p_se = (x1, y_base + step, z1)
                add_tri(p_nw, p_sw, p_ne, (0.0, 0.958, -0.287))
                add_tri(p_ne, p_sw, p_se, (0.287, 0.958, 0.0))

            elif item_id in ROOF_SLOPE_SOUTH:
                add_quad((x0, y_base, z0), (x1, y_base, z0), (x0, y_base + step, z1), (x1, y_base + step, z1), (0.0, 0.958, 0.287))

            elif item_id in ROOF_SLOPE_NORTH:
                add_quad((x0, y_base + step, z0), (x1, y_base + step, z0), (x0, y_base, z1), (x1, y_base, z1), (0.0, 0.958, -0.287))

            elif item_id in ROOF_SLOPE_EAST:
                add_quad((x0, y_base, z0), (x1, y_base + step, z0), (x0, y_base, z1), (x1, y_base + step, z1), (-0.287, 0.958, 0.0))

            elif item_id in ROOF_SLOPE_WEST:
                add_quad((x0, y_base + step, z0), (x1, y_base, z0), (x0, y_base + step, z1), (x1, y_base, z1), (0.287, 0.958, 0.0))

            elif item_id in ROOF_RIDGE_NS:
                xc = (x0 + x1) / 2.0
                add_quad((x0, y_base, z0), (xc, y_base + step, z0), (x0, y_base, z1), (xc, y_base + step, z1), (-0.287, 0.958, 0.0))
                add_quad((xc, y_base + step, z0), (x1, y_base, z0), (xc, y_base + step, z1), (x1, y_base, z1), (0.287, 0.958, 0.0))

            elif item_id in ROOF_RIDGE_EW:
                zc = (z0 + z1) / 2.0
                add_quad((x0, y_base, z0), (x1, y_base, z0), (x0, y_base + step, zc), (x1, y_base + step, zc), (0.0, 0.958, -0.287))
                add_quad((x0, y_base + step, zc), (x1, y_base + step, zc), (x0, y_base, z1), (x1, y_base, z1), (0.0, 0.958, 0.287))

            elif item_id in ROOF_HIP_SOUTH:
                zc = (z0 + z1) / 2.0
                xc = (x0 + x1) / 2.0
                add_tri((x0, y_base, z0), (xc, y_base + step, zc), (x1, y_base, z0), (0.0, 0.958, -0.287))
                add_tri((x0, y_base, z0), (x0, y_base + step, z1), (xc, y_base + step, zc), (-0.287, 0.958, 0.0))
                add_tri((x1, y_base, z0), (xc, y_base + step, zc), (x1, y_base + step, z1), (0.287, 0.958, 0.0))
                add_quad((x0, y_base + step, z1), (x1, y_base + step, z1), (x0, y_base, z1), (x1, y_base, z1), (0.0, 0.958, 0.287))

            elif item_id in ROOF_HIP_NORTH:
                zc = (z0 + z1) / 2.0
                xc = (x0 + x1) / 2.0
                add_tri((x0, y_base, z1), (x1, y_base, z1), (xc, y_base + step, zc), (0.0, 0.958, 0.287))
                add_tri((x0, y_base, z1), (xc, y_base + step, zc), (x0, y_base + step, z0), (-0.287, 0.958, 0.0))
                add_tri((x1, y_base, z1), (x1, y_base + step, z0), (xc, y_base + step, zc), (0.287, 0.958, 0.0))
                add_quad((x0, y_base + step, z0), (x0, y_base, z0), (x1, y_base + step, z0), (x1, y_base, z0), (0.0, 0.958, -0.287))

            elif item_id in (ROOF_VALLEY_CAP | ROOF_HIP_CAP):
                xc = (x0 + x1) / 2.0
                zc = (z0 + z1) / 2.0
                yt = y_base + step
                add_tri((x0, y_base, z0), (x1, y_base, z0), (xc, yt, zc), (0.0, 0.958, -0.287))
                add_tri((x1, y_base, z0), (x1, y_base, z1), (xc, yt, zc), (0.287, 0.958, 0.0))
                add_tri((x1, y_base, z1), (x0, y_base, z1), (xc, yt, zc), (0.0, 0.958, 0.287))
                add_tri((x0, y_base, z1), (x0, y_base, z0), (xc, yt, zc), (-0.287, 0.958, 0.0))

            else:
                add_quad((x0, y_base, z0), (x1, y_base, z0), (x0, y_base, z1), (x1, y_base, z1), (0.0, 1.0, 0.0))
            continue

        if is_wall:
            is_post = (item_id in G_POSTS)
            is_corner = (item_id in G_CORNERS)
            is_south = (item_id in G_SOUTH_WALLS) or (item_id not in G_EAST_WALLS and not is_corner and not is_post)
            is_east = (item_id in G_EAST_WALLS) or is_corner

            wz0 = z1 - WALL_THICKNESS
            wz1 = z1
            wx0 = x1 - WALL_THICKNESS
            wx1 = x1

            has_west_wall = any(abs(nz - z) <= 6 for (niid, nz) in G_WORLD_WALLS.get((wx - 1, wy), []))
            has_north_wall = any(abs(nz - z) <= 6 for (niid, nz) in G_WORLD_WALLS.get((wx, wy - 1), []))
            has_this_tile_east = any(abs(nz - z) <= 6 and (niid in G_EAST_WALLS or niid in G_CORNERS) for (niid, nz) in G_WORLD_WALLS.get((wx, wy), []) if niid != item_id)
            has_south_neighbor_east = any(abs(nz - z) <= 6 and (niid in G_EAST_WALLS or niid in G_CORNERS) for (niid, nz) in G_WORLD_WALLS.get((wx, wy + 1), []))
            has_this_tile_south = any(abs(nz - z) <= 6 and (niid in G_SOUTH_WALLS or niid in G_CORNERS) for (niid, nz) in G_WORLD_WALLS.get((wx, wy), []) if niid != item_id)
            has_east_neighbor_south = any(abs(nz - z) <= 6 and (niid in G_SOUTH_WALLS or niid in G_CORNERS) for (niid, nz) in G_WORLD_WALLS.get((wx + 1, wy), []))

            if is_post:
                add_box(wx0, wx1, y_base, y_top, wz0, wz1)
                yr = roof_corner_y.get((lx + 1, ly + 1), None)
                if yr is not None and yr > y_top + 0.02:
                    add_box(wx0, wx1, y_top, yr - 0.02, wz0, wz1)

                if has_west_wall:
                    add_box(x0, wx0, y_base, y_top, wz0, wz1)
                    yr0 = roof_corner_y.get((lx, ly + 1), None)
                    yr1 = roof_corner_y.get((lx + 1, ly + 1), None)
                    if yr0 is None and yr1 is not None: yr0 = yr1
                    if yr1 is None and yr0 is not None: yr1 = yr0
                    if yr0 is not None and yr1 is not None and (yr0 > y_top + 0.02 or yr1 > y_top + 0.02):
                        yt0 = max(y_top, yr0 - 0.02)
                        yt1 = max(y_top, yr1 - 0.02)
                        add_sloped_wall_south(x0, wx0, y_top, yt0, yt1, wz0, wz1)

                if has_north_wall:
                    add_box(wx0, wx1, y_base, y_top, z0, wz0)
                    yr0 = roof_corner_y.get((lx + 1, ly), None)
                    yr1 = roof_corner_y.get((lx + 1, ly + 1), None)
                    if yr0 is None and yr1 is not None: yr0 = yr1
                    if yr1 is None and yr0 is not None: yr1 = yr0
                    if yr0 is not None and yr1 is not None and (yr0 > y_top + 0.02 or yr1 > y_top + 0.02):
                        yt0 = max(y_top, yr0 - 0.02)
                        yt1 = max(y_top, yr1 - 0.02)
                        add_sloped_wall_east(z0, wz0, y_top, yt0, yt1, wx0, wx1)
                continue

            if is_south or is_corner:
                trim_west = (not has_west_wall) and (is_corner or has_this_tile_east or has_south_neighbor_east)
                start_x = wx0 if trim_west else x0

                add_box(start_x, x1, y_base, y_top, wz0, wz1)

                yr0 = roof_corner_y.get((lx, ly + 1), None)
                yr1 = roof_corner_y.get((lx + 1, ly + 1), None)
                if yr0 is None and yr1 is not None: yr0 = yr1
                if yr1 is None and yr0 is not None: yr1 = yr0
                if yr0 is not None and yr1 is not None:
                    if yr0 > y_top + 0.02 or yr1 > y_top + 0.02:
                        yt0 = max(y_top, yr0 - 0.02)
                        yt1 = max(y_top, yr1 - 0.02)
                        if trim_west and x1 > start_x:
                            t0 = (start_x - x0) / (x1 - x0)
                            yt0 = yt0 + (yt1 - yt0) * t0
                        add_sloped_wall_south(start_x, x1, y_top, yt0, yt1, wz0, wz1)

            if is_east or is_corner:
                trim_north = (not has_north_wall) and (is_corner or has_this_tile_south or has_east_neighbor_south)
                start_z = wz0 if trim_north else z0

                add_box(wx0, wx1, y_base, y_top, start_z, z1)

                yr0 = roof_corner_y.get((lx + 1, ly), None)
                yr1 = roof_corner_y.get((lx + 1, ly + 1), None)
                if yr0 is None and yr1 is not None: yr0 = yr1
                if yr1 is None and yr0 is not None: yr1 = yr0
                if yr0 is not None and yr1 is not None:
                    if yr0 > y_top + 0.02 or yr1 > y_top + 0.02:
                        yt0 = max(y_top, yr0 - 0.02)
                        yt1 = max(y_top, yr1 - 0.02)
                        if trim_north and z1 > start_z:
                            t0 = (start_z - z0) / (z1 - z0)
                            yt0 = yt0 + (yt1 - yt0) * t0
                        add_sloped_wall_east(start_z, z1, y_top, yt0, yt1, wx0, wx1)
            continue

    if not indices:
        return (cx, cy, 0, 0)

    glb_file = os.path.join(OUTPUT_DIR, f"chunk_{cx}_{cy}_buildings.glb")
    write_glb(glb_file, vertices, normals, indices)
    return (cx, cy, len(vertices), len(indices) // 3)


def main():
    global G_TD, G_STAIDX, G_STATICS, G_WORLD_WALLS, G_SOUTH_WALLS, G_EAST_WALLS, G_CORNERS, G_POSTS

    set_start_method("fork", force=True)
    t0 = time.time()
    print("================================================================")
    print("=== Ultima Online Britannia - World 3D Architecture Pipeline ===")
    print("================================================================")

    # 1. Load Classifications
    G_SOUTH_WALLS, G_EAST_WALLS, G_CORNERS, G_POSTS = load_wall_classifications()
    all_wall_ids = G_SOUTH_WALLS | G_EAST_WALLS | G_CORNERS | G_POSTS | ARCH_IDS | WINDOW_IDS

    # 2. Read UO Binary Files into Memory
    print("[1/4] Loading tiledata and statics binaries into shared memory...")
    with open(TILEDATA_FILE, "rb") as f_td:
        G_TD = f_td.read()
    with open(STAIDX_FILE, "rb") as f_idx:
        G_STAIDX = f_idx.read()
    with open(STATICS_FILE, "rb") as f_sta:
        G_STATICS = f_sta.read()

    # 3. Pre-index World Wall Topology (for seamless flush corners across all chunks)
    print("[2/4] Indexing world-wide wall topology for flush corners...")
    t_idx0 = time.time()
    G_WORLD_WALLS = {}
    total_blocks = len(G_STAIDX) // 12
    for b_idx in range(total_blocks):
        offset, length, _ = struct.unpack_from("<iii", G_STAIDX, b_idx * 12)
        if offset >= 0 and length > 0:
            bx = b_idx // 512
            by = b_idx % 512
            for i in range(length // 7):
                iid, x, y, z, _ = struct.unpack_from("<HBBbH", G_STATICS, offset + i * 7)
                if iid in all_wall_ids:
                    wx = bx * 8 + x
                    wy = by * 8 + y
                    G_WORLD_WALLS.setdefault((wx, wy), []).append((iid, z))
    print(f"      -> Indexed {len(G_WORLD_WALLS):,d} wall coordinates in {time.time() - t_idx0:.2f}s.")

    # 4. Discover all chunks with architecture
    print("[3/4] Scanning 7,168 chunks (112 x 64) for architecture...")
    t_scan0 = time.time()
    chunks_to_process = []

    arch_check_ids = all_wall_ids | ALL_ROOF_IDS | WOODEN_BRIDGE_FLOORS | BRIDGE_STONE_BLOCKS | BRIDGE_PARAPET_WALLS

    for cx in range(WORLD_WIDTH_CHUNKS):
        for cy in range(WORLD_HEIGHT_CHUNKS):
            has_arch = False
            for bx in range(cx * 8, (cx + 1) * 8):
                for by in range(cy * 8, (cy + 1) * 8):
                    b_idx = bx * 512 + by
                    offset, length, _ = struct.unpack_from("<iii", G_STAIDX, b_idx * 12)
                    if offset >= 0 and length > 0:
                        for i in range(length // 7):
                            iid, _, _, _, _ = struct.unpack_from("<HBBbH", G_STATICS, offset + i * 7)
                            if iid in arch_check_ids:
                                has_arch = True
                                break
                            fl, h, name = get_item_info_fast(iid)
                            if ((fl & 0x10) or (fl & 0x400)) and any(w in name for w in ("wall", "roof", "stair", "step", "pillar", "column", "arch", "fence")):
                                has_arch = True
                                break
                    if has_arch:
                        break
                if has_arch:
                    break
            if has_arch:
                chunks_to_process.append((cx, cy))

    print(f"      -> Found {len(chunks_to_process)} chunks with architecture (out of {WORLD_WIDTH_CHUNKS * WORLD_HEIGHT_CHUNKS} total) in {time.time() - t_scan0:.2f}s.")

    # 5. Multiprocessing Parallel Generation
    num_cpus = cpu_count()
    print(f"[4/4] Generating 3D buildings in parallel using {num_cpus} CPU cores...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    t_gen0 = time.time()

    total_chunks_written = 0
    total_triangles = 0

    with Pool(processes=num_cpus) as pool:
        for i, (cx, cy, verts, tris) in enumerate(pool.imap_unordered(process_world_chunk, chunks_to_process, chunksize=4), 1):
            if tris > 0:
                total_chunks_written += 1
                total_triangles += tris
            if i % 100 == 0 or i == len(chunks_to_process):
                pct = (i / len(chunks_to_process)) * 100.0
                elapsed = time.time() - t_gen0
                print(f"      [{pct:5.1f}%] Processed {i:4d}/{len(chunks_to_process)} chunks | {total_chunks_written} models generated | {total_triangles:,d} tris ({elapsed:.1f}s)")

    total_elapsed = time.time() - t0
    print("\n" + "=" * 64)
    print(f"=== BRITANNIA WORLD ARCHITECTURE GENERATION COMPLETE ===")
    print(f"  • Total Chunks Generated: {total_chunks_written} .glb models")
    print(f"  • Total Triangles:        {total_triangles:,d} tris")
    print(f"  • Output Directory:       {OUTPUT_DIR}")
    print(f"  • Total Pipeline Time:    {total_elapsed:.2f} seconds")
    print("================================================================")


if __name__ == "__main__":
    main()
