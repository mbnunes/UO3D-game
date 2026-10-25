#!/usr/bin/env python3
"""
export_all_community_assets.py

High-performance parallel exporter for UO3D community building packages.
Exports discrete building instances across all 6 Ultima Online maps:
  - Map 0: Felucca
  - Map 1: Trammel
  - Map 2: Ilshenar
  - Map 3: Malas
  - Map 4: Tokuno
  - Map 5: Ter Mur

For each building, creates:
  - model_base.glb             (glTF 3D mesh centered at origin 0,0,0)
  - model_base.obj             (Universal Wavefront OBJ format)
  - model_base.mtl             (Material definition)
  - reference_2d.png           (Complete exterior 2D isometric render with UOMAP HUD)
  - reference_2d_interior.png  (Interior floor plan cutaway without roof with UOMAP HUD)
  - info.json                  (Coordinates, bounds, dimensions, item IDs, UOMAP shortcuts)
  - textures_2d/*.png          (All original UO 2D art sprites as PNGs)
"""

import os
import sys
import json
import struct
import shutil
import time
from collections import defaultdict, deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont

from generate_world_buildings import (
    load_wall_classifications,
    write_glb,
    H_SCALE, V_SCALE,
    ROOF_SLOPE_SOUTH, ROOF_SLOPE_NORTH, ROOF_SLOPE_EAST, ROOF_SLOPE_WEST,
    ROOF_RIDGE_EW, ROOF_RIDGE_NS, ROOF_VALLEY_RISE_NE, ROOF_VALLEY_FALL_SE,
    ROOF_VALLEY_CAP, ROOF_HIP_SOUTH, ROOF_HIP_NORTH, ROOF_HIP_CAP,
    FLAT_SLATE_ROOF, ALL_ROOF_IDS,
    IRON_FENCE_NS, IRON_FENCE_EW, IRON_FENCE_POST,
    WOOD_FENCE_NS, WOOD_FENCE_EW, WOOD_FENCE_POST,
    ALL_FENCE_IDS, WOODEN_BRIDGE_FLOORS, BRIDGE_STONE_BLOCKS,
    ARCH_IDS, WINDOW_IDS
)

UO_DIR = "/opt/hd_jogos/UOC"
OUTPUT_ROOT = "/home/mnunes/uo3d_map/community_assets"

MAP_CONFIGS = [
    {
        "id": 0, "name": "felucca", "folder": "map0_felucca",
        "map_file": f"{UO_DIR}/map0.mul", "staidx_file": f"{UO_DIR}/staidx0.mul", "statics_file": f"{UO_DIR}/statics0.mul",
        "width_tiles": 7168, "height_tiles": 5120, "blocks_x": 896, "blocks_y": 640
    },
    {
        "id": 1, "name": "trammel", "folder": "map1_trammel",
        "map_file": f"{UO_DIR}/map1.mul", "staidx_file": f"{UO_DIR}/staidx1.mul", "statics_file": f"{UO_DIR}/statics1.mul",
        "width_tiles": 7168, "height_tiles": 5120, "blocks_x": 896, "blocks_y": 640
    },
    {
        "id": 2, "name": "ilshenar", "folder": "map2_ilshenar",
        "map_file": f"{UO_DIR}/map2.mul", "staidx_file": f"{UO_DIR}/staidx2.mul", "statics_file": f"{UO_DIR}/statics2.mul",
        "width_tiles": 2304, "height_tiles": 1600, "blocks_x": 288, "blocks_y": 200
    },
    {
        "id": 3, "name": "malas", "folder": "map3_malas",
        "map_file": f"{UO_DIR}/map3.mul", "staidx_file": f"{UO_DIR}/staidx3.mul", "statics_file": f"{UO_DIR}/statics3.mul",
        "width_tiles": 2560, "height_tiles": 2048, "blocks_x": 320, "blocks_y": 256
    },
    {
        "id": 4, "name": "tokuno", "folder": "map4_tokuno",
        "map_file": f"{UO_DIR}/map4.mul", "staidx_file": f"{UO_DIR}/staidx4.mul", "statics_file": f"{UO_DIR}/statics4.mul",
        "width_tiles": 1440, "height_tiles": 1440, "blocks_x": 180, "blocks_y": 180
    },
    {
        "id": 5, "name": "termur", "folder": "map5_termur",
        "map_file": f"{UO_DIR}/map5.mul", "staidx_file": f"{UO_DIR}/staidx5.mul", "statics_file": f"{UO_DIR}/statics5.mul",
        "width_tiles": 1280, "height_tiles": 4096, "blocks_x": 160, "blocks_y": 512
    }
]

# Cities & Regions definitions (bounding boxes in tiles)
MAP01_REGIONS = [
    {"name": "britain",      "bounds": (1280, 1680, 1480, 1850)},
    {"name": "trinsic",      "bounds": (1750, 2150, 2600, 2950)},
    {"name": "yew",          "bounds": (450, 850, 850, 1250)},
    {"name": "minoc",        "bounds": (2350, 2750, 350, 700)},
    {"name": "moonglow",     "bounds": (4300, 4650, 900, 1450)},
    {"name": "magincia",     "bounds": (3550, 3850, 2000, 2300)},
    {"name": "jhelom",       "bounds": (1300, 1550, 3700, 4050)},
    {"name": "skara_brae",   "bounds": (550, 850, 2100, 2400)},
    {"name": "vesper",       "bounds": (2700, 3050, 650, 1050)},
    {"name": "bucs_den",     "bounds": (2600, 2850, 2050, 2300)},
    {"name": "nujelm",       "bounds": (3500, 3850, 1100, 1450)},
    {"name": "ocllo",        "bounds": (3550, 3750, 2450, 2750)},
    {"name": "cove",         "bounds": (2200, 2350, 1100, 1300)},
    {"name": "serpent_hold", "bounds": (2850, 3100, 3350, 3650)},
    {"name": "wind",         "bounds": (1300, 1450, 1000, 1150)},
    {"name": "delucia",      "bounds": (5150, 5350, 3950, 4150)},
    {"name": "papua",        "bounds": (5650, 5850, 3100, 3350)}
]

MAP2_REGIONS = [
    {"name": "lakeshire", "bounds": (1150, 1300, 450, 600)},
    {"name": "montor",    "bounds": (1550, 1750, 250, 450)},
    {"name": "mistas",    "bounds": (750, 950, 950, 1150)},
    {"name": "ver_lore",  "bounds": (1400, 1600, 1100, 1300)}
]

MAP3_REGIONS = [
    {"name": "luna",  "bounds": (900, 1150, 450, 650)},
    {"name": "umbra", "bounds": (1950, 2150, 1250, 1450)}
]

MAP4_REGIONS = [
    {"name": "zento", "bounds": (650, 850, 1100, 1300)}
]

MAP5_REGIONS = [
    {"name": "royal_city", "bounds": (700, 1050, 2700, 3050)},
    {"name": "holy_city",  "bounds": (900, 1100, 3600, 3850)}
]

def get_region_name(wx, wy, map_id):
    if map_id in (0, 1):
        regs = MAP01_REGIONS
    elif map_id == 2:
        regs = MAP2_REGIONS
    elif map_id == 3:
        regs = MAP3_REGIONS
    elif map_id == 4:
        regs = MAP4_REGIONS
    elif map_id == 5:
        regs = MAP5_REGIONS
    else:
        regs = []

    for r in regs:
        x0, x1, y0, y1 = r["bounds"]
        if x0 <= wx <= x1 and y0 <= wy <= y1:
            return r["name"]
    return "wilderness"

# Global shared data
G_TD = None
G_ARTIDX = None
G_ARTMUL = None
G_MAP = None
G_STAIDX = None
G_STATICS = None
SOUTH_WALLS = None
EAST_WALLS = None
CORNERS = None
POSTS = None

def init_worker(td_bytes, artidx_bytes, artmul_bytes, map_bytes, staidx_bytes, statics_bytes, s_walls, e_walls, corners, posts):
    global G_TD, G_ARTIDX, G_ARTMUL, G_MAP, G_STAIDX, G_STATICS
    global SOUTH_WALLS, EAST_WALLS, CORNERS, POSTS
    G_TD = td_bytes
    G_ARTIDX = artidx_bytes
    G_ARTMUL = artmul_bytes
    G_MAP = map_bytes
    G_STAIDX = staidx_bytes
    G_STATICS = statics_bytes
    SOUTH_WALLS = s_walls
    EAST_WALLS = e_walls
    CORNERS = corners
    POSTS = posts

_LAND_CACHE = {}
def extract_land_sprite(tile_id):
    if tile_id in _LAND_CACHE: return _LAND_CACHE[tile_id]
    if tile_id * 12 + 12 > len(G_ARTIDX): 
        _LAND_CACHE[tile_id] = None
        return None
    lookup, length, _ = struct.unpack_from("<iii", G_ARTIDX, tile_id * 12)
    if lookup < 0 or length != 2048 or lookup + length > len(G_ARTMUL): 
        _LAND_CACHE[tile_id] = None
        return None
    data = G_ARTMUL[lookup:lookup+length]
    img = Image.new("RGBA", (44, 44), (0, 0, 0, 0))
    pix = img.load()
    pos = 0
    for y in range(44):
        if y < 22:
            x_start = 21 - y
            line_w = (y + 1) * 2
        else:
            x_start = y - 22
            line_w = (44 - y) * 2
        for x in range(line_w):
            c = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            r = ((c >> 10) & 0x1F) * 255 // 31
            g = ((c >> 5) & 0x1F) * 255 // 31
            b = (c & 0x1F) * 255 // 31
            pix[x_start + x, y] = (r, g, b, 255)
    _LAND_CACHE[tile_id] = img
    return img

_ART_CACHE = {}
def extract_art_sprite(item_id):
    if item_id in _ART_CACHE:
        return _ART_CACHE[item_id]
    idx = 0x4000 + item_id
    if idx * 12 + 12 > len(G_ARTIDX): 
        _ART_CACHE[item_id] = None
        return None
    lookup, length, _ = struct.unpack_from("<iii", G_ARTIDX, idx * 12)
    if lookup < 0 or length <= 0 or lookup + length > len(G_ARTMUL): 
        _ART_CACHE[item_id] = None
        return None
    data = G_ARTMUL[lookup:lookup+length]
    header, width, height = struct.unpack_from("<IHH", data, 0)
    offsets = struct.unpack_from(f"<{height}H", data, 8)
    base_data = 8 + height * 2
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pix = img.load()
    for y in range(height):
        pos = base_data + offsets[y] * 2
        cur_x = 0
        while pos + 4 <= len(data):
            x_ofs, run = struct.unpack_from("<HH", data, pos)
            pos += 4
            if x_ofs + run == 0: break
            cur_x += x_ofs
            for i in range(run):
                c = struct.unpack_from("<H", data, pos)[0]
                pos += 2
                r = ((c >> 10) & 0x1F) * 255 // 31
                g = ((c >> 5) & 0x1F) * 255 // 31
                b = (c & 0x1F) * 255 // 31
                if cur_x < width:
                    pix[cur_x, y] = (r, g, b, 255)
                cur_x += 1
    _ART_CACHE[item_id] = img
    return img

def get_land_tile_fast(wx, wy, blocks_y):
    bx = wx // 8
    by = wy // 8
    b_idx = bx * blocks_y + by
    off = b_idx * 196 + 4
    if off + 192 <= len(G_MAP):
        lx = wx % 8
        ly = wy % 8
        t_idx = ly * 8 + lx
        tid, z = struct.unpack_from("<Hb", G_MAP, off + t_idx * 3)
        return tid, z
    return 0, 0

def export_obj_and_mtl(obj_path, mtl_path, vertices, normals, indices):
    mtl_filename = os.path.basename(mtl_path)
    with open(mtl_path, "w") as f:
        f.write("# Material for UO3D Building Base\n")
        f.write("newmtl Building_Base\n")
        f.write("Ka 0.25 0.25 0.25\n")
        f.write("Kd 0.85 0.85 0.82\n")
        f.write("Ks 0.05 0.05 0.05\n")
        f.write("Ns 10.0\n")
        f.write("d 1.0\n")
        f.write("illum 2\n")

    with open(obj_path, "w") as f:
        f.write("# Wavefront OBJ exported by UO3D Community Exporter\n")
        f.write(f"mtllib {mtl_filename}\n")
        f.write("o BuildingMesh\n")
        for v in vertices:
            f.write(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
        for n in normals:
            f.write(f"vn {n[0]:.4f} {n[1]:.4f} {n[2]:.4f}\n")
        f.write("usemtl Building_Base\n")
        f.write("s 1\n")
        for i in range(0, len(indices), 3):
            i1 = indices[i] + 1
            i2 = indices[i+1] + 1
            i3 = indices[i+2] + 1
            f.write(f"f {i1}//{i1} {i2}//{i2} {i3}//{i3}\n")

def render_2d_reference(items, min_wx, max_wx, min_wy, max_wy, out_png_path, meta, blocks_y, is_interior=False):
    draw_elements = []

    # 1. Ground Land Tiles under the building
    for wy in range(min_wy - 1, max_wy + 2):
        for wx in range(min_wx - 1, max_wx + 2):
            tid, lz = get_land_tile_fast(wx, wy, blocks_y)
            l_img = extract_land_sprite(tid)
            if l_img:
                sx = (wx - wy) * 22
                sy = (wx + wy) * 22 - lz * 4
                draw_elements.append(((wx + wy, lz, -1, 0), sx - 22, sy, l_img))

    # 2. Building Statics
    for it in items:
        wx, wy, z, item_id, fl, h, name = it
        is_roof = ("roof" in name) or ("shingle" in name) or (item_id in ALL_ROOF_IDS) or (item_id in (1404, 1405, 1406, 1407, 1408, 1409, 1410, 1411, 1412, 1413))
        if is_interior:
            if is_roof:
                continue
            if z >= 20 and (fl & 0x200):
                continue

        s_img = extract_art_sprite(item_id)
        if s_img:
            sx = (wx - wy) * 22
            sy = (wx + wy) * 22 - z * 4
            draw_x = sx - s_img.width // 2
            draw_y = sy - s_img.height + 44
            is_surf = 0 if (fl & 0x200) else 1
            roof_prio = 2 if is_roof else 1
            priority = 0 if is_surf == 0 else roof_prio
            draw_elements.append(((wx + wy, z, priority, item_id), draw_x, draw_y, s_img))

    if not draw_elements:
        return

    draw_elements.sort(key=lambda d: d[0])

    min_dx = min(d[1] for d in draw_elements)
    max_dx = max(d[1] + d[3].width for d in draw_elements)
    min_dy = min(d[2] for d in draw_elements)
    max_dy = max(d[2] + d[3].height for d in draw_elements)

    pad_x = 20
    pad_y = 20
    banner_h = 74
    content_w = (max_dx - min_dx) + pad_x * 2
    content_h = (max_dy - min_dy) + pad_y * 2
    total_w = max(content_w, 680)
    total_h = content_h + banner_h

    canvas = Image.new("RGBA", (total_w, total_h), (22, 24, 28, 255))
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([(0, 0), (total_w, banner_h)], fill=(16, 18, 22, 255))
    draw.line([(0, banner_h), (total_w, banner_h)], fill=(194, 157, 91), width=2)
    font = ImageFont.load_default()

    b_name = meta["name"]
    map_lbl = meta["map_name"]
    cx = int(meta["world_bounds"]["center_x"])
    cy = int(meta["world_bounds"]["center_y"])
    cz = meta["world_bounds"]["base_z"]
    bx_str = f"X[{min_wx}..{max_wx}] Y[{min_wy}..{max_wy}] Z[{meta['world_bounds']['base_z']}..{meta['world_bounds']['max_z']}]"

    tag = "[INTERIOR / SEM TELHADO]" if is_interior else "[EXTERIOR COMPLETO]"
    tag_col = (140, 220, 180) if is_interior else (240, 215, 145)

    draw.text((16, 10), f"UO3D ASSET | {map_lbl} | {meta['region'].title()} - {b_name} {tag}", fill=tag_col, font=font)
    draw.text((16, 30), f"UOMAP / In-Game: {cx}, {cy}, {cz} | Bounds: {bx_str} | Dim: {meta['dimensions_meters']['width_x']}x{meta['dimensions_meters']['depth_z']}m", fill=(220, 220, 220), font=font)
    desc = "Disposicao interna de moveis, forjas, balcoes e salas" if is_interior else f">> UOMAP Dica: Pressione Ctrl+G e digite: {cx} {cy} para centralizar diretamente neste imovel!"
    draw.text((16, 50), desc, fill=(140, 185, 235), font=font)

    offset_x = (total_w - content_w) // 2 + pad_x - min_dx
    offset_y = banner_h + pad_y - min_dy

    for _, dx, dy, img in draw_elements:
        canvas.alpha_composite(img, (dx + offset_x, dy + offset_y))

    canvas.save(out_png_path)

def generate_building_3d_geometry(items, min_wx, max_wx, min_wy, max_wy, base_z):
    world_walls = set()
    roof_corner_y = {}
    roof_tiles_coords = set()
    stairs_by_coord = {}

    center_x = (min_wx + max_wx + 1) / 2.0
    center_z = (min_wy + max_wy + 1) / 2.0
    y_base_ground = base_z * V_SCALE

    chunk_items = []
    for item_tuple in items:
        wx, wy, z, item_id, fl, h, name = item_tuple

        is_stair = ("stair" in name) or ("step" in name) or ((fl & 0x400) != 0 and "ladder" not in name)
        if is_stair:
            direction = (fl >> 30) & 3
            if (wx, wy) not in stairs_by_coord:
                stairs_by_coord[(wx, wy)] = []
            stairs_by_coord[(wx, wy)].append((z, h, direction))

        STONE_ROOF_TERRACE = {1372, 1373, 1374, 1375, 1376, 1377}
        is_pitched_roof = (("roof" in name and name != "stone roof") or ("shingle" in name) or (item_id in ALL_ROOF_IDS)) and (item_id not in FLAT_SLATE_ROOF) and (item_id not in STONE_ROOF_TERRACE)
        if is_pitched_roof:
            r_yb = (z * V_SCALE) - y_base_ground
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
            elif item_id in ROOF_RIDGE_EW or item_id in ROOF_RIDGE_NS:
                cnw, cne, csw, cse = r_yb, r_yb, r_yb, r_yb
            elif item_id in ROOF_VALLEY_RISE_NE:
                cnw, cne, csw, cse = r_yb, r_yb + step, r_yb, r_yb
            elif item_id in ROOF_VALLEY_FALL_SE:
                cnw, cne, csw, cse = r_yb, r_yb, r_yb, r_yb + step
            elif item_id in ROOF_VALLEY_CAP:
                cnw, cne, csw, cse = r_yb, r_yb + step, r_yb, r_yb + step
            elif item_id in ROOF_HIP_SOUTH:
                cnw, cne, csw, cse = r_yb, r_yb, r_yb + step, r_yb + step
            elif item_id in ROOF_HIP_NORTH:
                cnw, cne, csw, cse = r_yb + step, r_yb + step, r_yb, r_yb
            elif item_id in ROOF_HIP_CAP:
                cnw, cne, csw, cse = r_yb + step, r_yb + step, r_yb + step, r_yb + step
            else:
                cnw, cne, csw, cse = r_yb, r_yb, r_yb + step, r_yb + step
            roof_corner_y[(wx, wy)] = (cnw, cne, csw, cse)

        is_fence = (item_id in ALL_FENCE_IDS) or ("fence" in name) or ("bars" in name)
        is_roof = (("roof" in name and name != "stone roof") or ("shingle" in name) or (item_id in ALL_ROOF_IDS)) and (item_id not in STONE_ROOF_TERRACE)
        is_arch = (item_id in ARCH_IDS) or ("arch" in name) or ("archway" in name)
        is_window = (item_id in WINDOW_IDS) or ("window" in name)
        is_column = ("pillar" in name) or ("column" in name) or ("pier" in name)
        is_post = (item_id in POSTS) or ("post" in name)
        is_wall = ((fl & 0x10) != 0) or ("wall" in name) or (item_id in SOUTH_WALLS) or (item_id in EAST_WALLS) or (item_id in CORNERS) or is_post or is_window or is_arch
        is_floor = ((("cobblestone" in name) or ("paver" in name) or ("board" in name) or ("plank" in name) or
                     ("floor" in name) or (name == "stone roof") or (item_id in STONE_ROOF_TERRACE) or (item_id in WOODEN_BRIDGE_FLOORS)) and
                    not any(w in name for w in ("carpet", "rug", "table", "chair", "case", "desk", "bench", "counter")))

        if ((fl & 0x10) != 0) or ("wall" in name) or is_wall:
            world_walls.add((wx, wy))

        if not (is_fence or is_roof or is_arch or is_window or is_column or is_stair or is_wall or is_floor):
            continue

        chunk_items.append((item_id, wx, wy, z, h, fl, name, is_fence, is_roof, is_arch, is_window, is_column, is_stair, is_wall, is_floor, is_post))

    vertices = []
    normals = []
    indices = []

    def add_quad(p0, p1, p2, p3, n):
        base = len(vertices)
        vertices.extend([p0, p1, p2, p3])
        normals.extend([n, n, n, n])
        indices.extend([base + 0, base + 2, base + 1, base + 1, base + 2, base + 3])

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

    for it in chunk_items:
        item_id, wx, wy, z, h, fl, name, is_fence, is_roof, is_arch, is_window, is_column, is_stair, is_wall, is_floor, is_post = it

        wx0 = (wx - center_x) * H_SCALE
        wx1 = wx0 + H_SCALE
        wz0 = (wy - center_z) * H_SCALE
        wz1 = wz0 + H_SCALE
        yb  = (z * V_SCALE) - y_base_ground
        yt  = yb + max(h, 1) * V_SCALE
        wall_thick = 0.35 * H_SCALE

        if is_stair:
            continue

        elif is_window:
            is_south = item_id in (131, 59, 93, 186, 202, 340) or (item_id in SOUTH_WALLS) or ("south" in name) or (item_id not in EAST_WALLS)
            y_sill = yb + max(h, 1) * 0.35 * V_SCALE
            y_lintel = yb + max(h, 1) * 0.75 * V_SCALE
            if is_south:
                add_box(wx0, wx1, yb, y_sill, wz0, wz0 + wall_thick)
                add_box(wx0, wx1, y_lintel, yt, wz0, wz0 + wall_thick)
                add_box(wx0, wx0 + 0.25, y_sill, y_lintel, wz0, wz0 + wall_thick)
                add_box(wx1 - 0.25, wx1, y_sill, y_lintel, wz0, wz0 + wall_thick)
            else:
                add_box(wx0, wx0 + wall_thick, yb, y_sill, wz0, wz1)
                add_box(wx0, wx0 + wall_thick, y_lintel, yt, wz0, wz1)
                add_box(wx0, wx0 + wall_thick, y_sill, y_lintel, wz0, wz0 + 0.25)
                add_box(wx0, wx0 + wall_thick, y_sill, y_lintel, wz1 - 0.25, wz1)

        elif is_arch:
            is_south = ("south" in name) or (item_id in SOUTH_WALLS) or (item_id not in EAST_WALLS)
            y_lintel = yb + max(h, 1) * 0.75 * V_SCALE
            if is_south:
                add_box(wx0, wx1, y_lintel, yt, wz0, wz0 + wall_thick)
                add_box(wx0, wx0 + 0.25, yb, y_lintel, wz0, wz0 + wall_thick)
                add_box(wx1 - 0.25, wx1, yb, y_lintel, wz0, wz0 + wall_thick)
            else:
                add_box(wx0, wx0 + wall_thick, y_lintel, yt, wz0, wz1)
                add_box(wx0, wx0 + wall_thick, yb, y_lintel, wz0, wz0 + 0.25)
                add_box(wx0, wx0 + wall_thick, yb, y_lintel, wz1 - 0.25, wz1)

        elif is_roof:
            step = 3.0 * V_SCALE
            thick = 0.12 * V_SCALE
            if item_id in FLAT_SLATE_ROOF:
                add_box(wx0, wx1, yb, yb + thick, wz0, wz1)
            elif item_id in ROOF_SLOPE_SOUTH:
                p_nw = (wx0, yb, wz0); p_ne = (wx1, yb, wz0)
                p_sw = (wx0, yb + step, wz1); p_se = (wx1, yb + step, wz1)
                add_quad(p_nw, p_ne, p_sw, p_se, (0.0, 0.7071, 0.7071))
                add_quad((wx0, yb - thick, wz0), (wx1, yb - thick, wz0), (wx0, yb + step - thick, wz1), (wx1, yb + step - thick, wz1), (0.0, -0.7071, -0.7071))
            elif item_id in ROOF_SLOPE_NORTH:
                p_nw = (wx0, yb + step, wz0); p_ne = (wx1, yb + step, wz0)
                p_sw = (wx0, yb, wz1); p_se = (wx1, yb, wz1)
                add_quad(p_sw, p_se, p_nw, p_ne, (0.0, 0.7071, -0.7071))
                add_quad((wx0, yb - thick, wz1), (wx1, yb - thick, wz1), (wx0, yb + step - thick, wz0), (wx1, yb + step - thick, wz0), (0.0, -0.7071, 0.7071))
            elif item_id in ROOF_SLOPE_EAST:
                p_nw = (wx0, yb, wz0); p_sw = (wx0, yb, wz1)
                p_ne = (wx1, yb + step, wz0); p_se = (wx1, yb + step, wz1)
                add_quad(p_nw, p_ne, p_sw, p_se, (0.7071, 0.7071, 0.0))
                add_quad((wx0, yb - thick, wz0), (wx1, yb + step - thick, wz0), (wx0, yb - thick, wz1), (wx1, yb + step - thick, wz1), (-0.7071, -0.7071, 0.0))
            elif item_id in ROOF_SLOPE_WEST:
                p_nw = (wx0, yb + step, wz0); p_sw = (wx0, yb + step, wz1)
                p_ne = (wx1, yb, wz0); p_se = (wx1, yb, wz1)
                add_quad(p_ne, p_nw, p_se, p_sw, (-0.7071, 0.7071, 0.0))
                add_quad((wx1, yb - thick, wz0), (wx0, yb + step - thick, wz0), (wx1, yb - thick, wz1), (wx0, yb + step - thick, wz1), (0.7071, -0.7071, 0.0))
            elif item_id in ROOF_RIDGE_EW:
                p_mid_w = (wx0, yb + step, wz0 + 0.5 * H_SCALE)
                p_mid_e = (wx1, yb + step, wz0 + 0.5 * H_SCALE)
                add_quad((wx0, yb, wz0), (wx1, yb, wz0), p_mid_w, p_mid_e, (0.0, 0.7071, -0.7071))
                add_quad(p_mid_w, p_mid_e, (wx0, yb, wz1), (wx1, yb, wz1), (0.0, 0.7071, 0.7071))
            elif item_id in ROOF_RIDGE_NS:
                p_mid_n = (wx0 + 0.5 * H_SCALE, yb + step, wz0)
                p_mid_s = (wx0 + 0.5 * H_SCALE, yb + step, wz1)
                add_quad((wx0, yb, wz0), p_mid_n, (wx0, yb, wz1), p_mid_s, (-0.7071, 0.7071, 0.0))
                add_quad(p_mid_n, (wx1, yb, wz0), p_mid_s, (wx1, yb, wz1), (0.7071, 0.7071, 0.0))
            else:
                add_quad((wx0, yb, wz0), (wx1, yb, wz0), (wx0, yb + step, wz1), (wx1, yb + step, wz1), (0.0, 0.7071, 0.7071))

        elif is_wall:
            is_south = (item_id in SOUTH_WALLS) or ("south" in name)
            is_east  = (item_id in EAST_WALLS) or ("east" in name)
            is_corner = (item_id in CORNERS) or ("corner" in name)

            if is_south and not is_east:
                has_roof = (wx, wy) in roof_corner_y
                if has_roof:
                    cnw, cne, csw, cse = roof_corner_y[(wx, wy)]
                    add_sloped_wall_south(wx0, wx1, yb, cnw, cne, wz0, wz0 + wall_thick)
                else:
                    add_box(wx0, wx1, yb, yt, wz0, wz0 + wall_thick)
            elif is_east and not is_south:
                has_roof = (wx, wy) in roof_corner_y
                if has_roof:
                    cnw, cne, csw, cse = roof_corner_y[(wx, wy)]
                    add_sloped_wall_east(wz0, wz1, yb, cnw, csw, wx0, wx0 + wall_thick)
                else:
                    add_box(wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
            elif is_corner:
                add_box(wx0, wx0 + wall_thick, yb, yt, wz0, wz1)
                add_box(wx0 + wall_thick, wx1, yb, yt, wz0, wz0 + wall_thick)
            elif is_post:
                has_s_wall = (wx, wy + 1) in world_walls
                has_e_wall = (wx + 1, wy) in world_walls
                s_extent = wz1 if has_s_wall else (wz0 + wall_thick)
                e_extent = wx1 if has_e_wall else (wx0 + wall_thick)
                add_box(wx0, wx0 + wall_thick, yb, yt, wz0, s_extent)
                if has_e_wall:
                    add_box(wx0 + wall_thick, e_extent, yb, yt, wz0, wz0 + wall_thick)
            else:
                add_box(wx0, wx1, yb, yt, wz0, wz0 + wall_thick)

        elif is_floor:
            f_thick = 0.08 * V_SCALE
            add_box(wx0, wx1, yb - f_thick, yb, wz0, wz1)

        elif is_column:
            c_thick = 0.4 * H_SCALE
            add_box(wx0 + 0.3 * H_SCALE, wx0 + 0.3 * H_SCALE + c_thick, yb, yt, wz0 + 0.3 * H_SCALE, wz0 + 0.3 * H_SCALE + c_thick)

        elif is_fence:
            post_thick = 0.12 * H_SCALE
            add_box(wx0, wx0 + post_thick, yb, yt, wz0, wz0 + post_thick)

    return vertices, normals, indices

def process_single_building(task_data):
    (building_id, folder_name, b_name, map_id, map_folder, map_name, region_name, 
     min_x, max_x, min_y, max_y, items_in_c, cluster_tile_count, blocks_y) = task_data

    building_dir = os.path.join(OUTPUT_ROOT, map_folder, region_name, folder_name)
    textures_dir = os.path.join(building_dir, "textures_2d")
    os.makedirs(textures_dir, exist_ok=True)

    zs = [it[2] for it in items_in_c]
    min_z, max_z = min(zs), max(zs)
    dim_x = max_x - min_x + 1
    dim_y = max_y - min_y + 1
    center_x = (min_x + max_x + 1) / 2.0
    center_y = (min_y + max_y + 1) / 2.0

    # 1. 3D Model Geometry
    vertices, normals, indices = generate_building_3d_geometry(items_in_c, min_x, max_x, min_y, max_y, min_z)
    glb_path = os.path.join(building_dir, "model_base.glb")
    write_glb(glb_path, vertices, normals, indices)

    obj_path = os.path.join(building_dir, "model_base.obj")
    mtl_path = os.path.join(building_dir, "model_base.mtl")
    export_obj_and_mtl(obj_path, mtl_path, vertices, normals, indices)

    # 2. Extract 2D Textures
    unique_items = {}
    for it in items_in_c:
        item_id = it[3]
        item_name = it[6]
        if item_id not in unique_items:
            clean_name = "".join(c if c.isalnum() else "_" for c in item_name).strip("_")
            filename = f"{clean_name}_{item_id:04d}.png"
            unique_items[item_id] = {
                "id": item_id,
                "name": item_name,
                "texture_file": filename
            }
            img = extract_art_sprite(item_id)
            if img:
                img.save(os.path.join(textures_dir, filename))

    # 3. info.json
    info_data = {
        "building_id": folder_name,
        "name": b_name,
        "map": map_folder,
        "map_index": map_id,
        "map_name": map_name,
        "region": region_name,
        "uomap_navigation": {
            "shortcut": "Ctrl+G",
            "goto_coords": f"{int(center_x)} {int(center_y)}",
            "center_x": int(center_x),
            "center_y": int(center_y),
            "base_z": min_z,
            "map_name": f"{map_name.title()} (Map {map_id})"
        },
        "world_bounds": {
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "base_z": min_z,
            "max_z": max_z,
            "center_x": center_x,
            "center_y": center_y,
            "center_z_elevation": min_z * V_SCALE
        },
        "dimensions_meters": {
            "width_x": round(dim_x * H_SCALE, 2),
            "depth_z": round(dim_y * H_SCALE, 2),
            "height_y": round(max(1.0, (max_z - min_z + 20) * V_SCALE), 2)
        },
        "stats": {
            "tile_count": cluster_tile_count,
            "item_count": len(items_in_c),
            "triangles_count": len(indices) // 3,
            "unique_textures_count": len(unique_items)
        },
        "unique_items": sorted(list(unique_items.values()), key=lambda x: x["id"])
    }

    with open(os.path.join(building_dir, "info.json"), "w", encoding="utf-8") as f:
        json.dump(info_data, f, indent=2, ensure_ascii=False)

    # 4. 2D Reference Previews
    ref_png = os.path.join(building_dir, "reference_2d.png")
    render_2d_reference(items_in_c, min_x, max_x, min_y, max_y, ref_png, info_data, blocks_y, is_interior=False)

    ref_interior = os.path.join(building_dir, "reference_2d_interior.png")
    render_2d_reference(items_in_c, min_x, max_x, min_y, max_y, ref_interior, info_data, blocks_y, is_interior=True)

    return {
        "map_id": map_id,
        "region": region_name,
        "building_id": folder_name,
        "name": b_name,
        "path": f"{map_folder}/{region_name}/{folder_name}",
        "uomap_coords": f"{int(center_x)} {int(center_y)}",
        "tiles": cluster_tile_count,
        "tris": len(indices) // 3,
        "textures": len(unique_items)
    }

def run_export():
    t_start_total = time.time()
    print("=" * 70)
    print("  UO3D Community Architecture Exporter — All Maps (0 to 5)")
    print("=" * 70)

    # Read shared static art and tiledata
    print("[*] Reading tiledata.mul, artidx.mul, and art.mul...")
    with open(f"{UO_DIR}/tiledata.mul", "rb") as f: td_bytes = f.read()
    with open(f"{UO_DIR}/artidx.mul", "rb") as f: artidx_bytes = f.read()
    with open(f"{UO_DIR}/art.mul", "rb") as f: artmul_bytes = f.read()

    s_walls, e_walls, corners, posts = load_wall_classifications()

    total_exported_all_maps = 0
    all_maps_manifest = {}

    for cfg in MAP_CONFIGS:
        map_id = cfg["id"]
        map_name = cfg["name"].title()
        map_folder = cfg["folder"]
        blocks_x = cfg["blocks_x"]
        blocks_y = cfg["blocks_y"]

        if not (os.path.exists(cfg["map_file"]) and os.path.exists(cfg["staidx_file"]) and os.path.exists(cfg["statics_file"])):
            print(f"[!] Skipping Map {map_id} ({map_name}): mul files not found.")
            continue

        print(f"\n>>> Processing Map {map_id}: {map_name} ({cfg['width_tiles']}x{cfg['height_tiles']} tiles)...")
        t0 = time.time()

        with open(cfg["map_file"], "rb") as f: map_bytes = f.read()
        with open(cfg["staidx_file"], "rb") as f: staidx_bytes = f.read()
        with open(cfg["statics_file"], "rb") as f: statics_bytes = f.read()

        # Helper to read item info quickly
        def get_item_info_fast(item_id):
            land_size = 493568
            item_size = 41
            grp_size = 4 + 32 * item_size
            g = item_id // 32
            e = item_id % 32
            off = land_size + g * grp_size + 4 + e * item_size
            if off + 21 <= len(td_bytes):
                fl = struct.unpack_from("<Q", td_bytes, off)[0]
                height = td_bytes[off + 20]
                name = td_bytes[off+21:off+41].split(b"\x00")[0].decode("ascii", errors="replace").lower()
                return fl, height, name
            return 0, 0, ""

        # Scan active statics and cluster buildings
        print(f"[*] Scanning statics for Map {map_id} ({map_name})...")
        arch_tiles = defaultdict(list)
        all_raw_statics = defaultdict(list)

        total_blocks = blocks_x * blocks_y
        for b_idx in range(total_blocks):
            lookup = b_idx * 12
            if lookup + 12 <= len(staidx_bytes):
                offset, length, _ = struct.unpack_from("<iii", staidx_bytes, lookup)
                if offset >= 0 and length > 0:
                    bx = b_idx // blocks_y
                    by = b_idx % blocks_y
                    for i in range(length // 7):
                        item_id, x, y, z, hue = struct.unpack_from("<HBBbH", statics_bytes, offset + i * 7)
                        wx = bx * 8 + x
                        wy = by * 8 + y
                        fl, h, name = get_item_info_fast(item_id)
                        all_raw_statics[(wx, wy)].append((wx, wy, z, item_id, fl, h, name))

                        is_struct = ((fl & 0x200) or ("wall" in name) or ("roof" in name) or 
                                     ("door" in name) or ("stair" in name) or ("window" in name) or 
                                     ("arch" in name) or ("post" in name) or ("column" in name) or 
                                     (item_id in ALL_ROOF_IDS) or (item_id in s_walls) or (item_id in e_walls))
                        if is_struct:
                            arch_tiles[(wx, wy)].append((wx, wy, z, item_id, fl, h, name))

        print(f"[*] Found {len(arch_tiles)} structural tiles. Running connected components clustering...")
        visited = set()
        candidate_tasks = []
        region_counters = defaultdict(int)

        for tile in arch_tiles:
            if tile in visited: continue
            cluster = []
            q = deque([tile])
            visited.add(tile)
            while q:
                curr = q.popleft()
                cluster.append(curr)
                cx, cy = curr
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nbr = (cx + dx, cy + dy)
                        if nbr in arch_tiles and nbr not in visited:
                            visited.add(nbr)
                            q.append(nbr)

            xs = [p[0] for p in cluster]
            ys = [p[1] for p in cluster]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            dim_x = max_x - min_x + 1
            dim_y = max_y - min_y + 1

            # Skip world bridges or giant connected city walks (> 60m)
            if dim_x > 60 or dim_y > 60 or dim_x < 2 or dim_y < 2:
                continue

            cluster_tiles_set = set(cluster)
            items_in_c = []
            for wy in range(min_y, max_y + 1):
                for wx in range(min_x, max_x + 1):
                    if (wx, wy) in cluster_tiles_set:
                        items_in_c.extend(all_raw_statics[(wx, wy)])

            roof_count = sum(1 for it in items_in_c if "roof" in it[6])
            wall_count = sum(1 for it in items_in_c if ("wall" in it[6] or "window" in it[6] or "arch" in it[6]))

            if len(cluster) >= 16 and (wall_count >= 8 or roof_count >= 8):
                mid_x = (min_x + max_x) // 2
                mid_y = (min_y + max_y) // 2
                reg_name = get_region_name(mid_x, mid_y, map_id)
                region_counters[reg_name] += 1
                b_num = region_counters[reg_name]

                folder_name = f"building_{b_num:03d}_{min_x}_{min_y}"
                b_name = f"{reg_name.replace('_', ' ').title()} Building #{b_num:03d}"

                task_data = (
                    b_num, folder_name, b_name, map_id, map_folder, map_name, reg_name,
                    min_x, max_x, min_y, max_y, items_in_c, len(cluster), blocks_y
                )
                candidate_tasks.append(task_data)

        print(f"[*] Found {len(candidate_tasks)} discrete buildings for Map {map_id} ({map_name}).")
        print(f"[*] Launching parallel multiprocessing with 16 CPU cores...")

        map_results = []
        with ProcessPoolExecutor(max_workers=16, initializer=init_worker,
                                 initargs=(td_bytes, artidx_bytes, artmul_bytes, map_bytes, staidx_bytes, statics_bytes, s_walls, e_walls, corners, posts)) as executor:
            futures = [executor.submit(process_single_building, task) for task in candidate_tasks]
            completed_cnt = 0
            for f in as_completed(futures):
                res = f.result()
                map_results.append(res)
                completed_cnt += 1
                if completed_cnt % 25 == 0 or completed_cnt == len(candidate_tasks):
                    pct = completed_cnt * 100 // len(candidate_tasks)
                    print(f"    [{completed_cnt:03d}/{len(candidate_tasks):03d}] ({pct}%) Map {map_id} ({map_name}) - Last: {res['region']}/{res['building_id']}")

        dt = time.time() - t0
        print(f"[+] Map {map_id} ({map_name}) finished in {dt:.1f}s: {len(map_results)} buildings exported.")
        total_exported_all_maps += len(map_results)
        all_maps_manifest[map_folder] = map_results

        # Write map-level manifest
        map_manifest_path = os.path.join(OUTPUT_ROOT, map_folder, "buildings_manifest.json")
        with open(map_manifest_path, "w", encoding="utf-8") as f:
            json.dump(map_results, f, indent=2, ensure_ascii=False)

    # Write root community assets summary
    summary_path = os.path.join(OUTPUT_ROOT, "community_assets_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_buildings": total_exported_all_maps,
            "export_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "maps": {k: len(v) for k, v in all_maps_manifest.items()}
        }, f, indent=2, ensure_ascii=False)

    dt_total = time.time() - t_start_total
    print("\n" + "=" * 70)
    print(f"🎉 COMPLETED! Exported {total_exported_all_maps} buildings across all maps in {dt_total:.1f}s")
    print(f"📁 Output Location: {OUTPUT_ROOT}")
    print("=" * 70)

if __name__ == "__main__":
    run_export()
