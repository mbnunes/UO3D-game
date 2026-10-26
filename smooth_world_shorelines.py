#!/usr/bin/env python3
"""
smooth_world_shorelines.py

Smooths river and ocean shoreline boundaries across all maps:
1. Detects sharp 90-degree convex and concave shoreline corners where land meets water.
2. Applies organic bevel displacements (dx, dz) to round off sharp square corners.
3. Computes continuous smooth normals across shared quad vertices to eliminate faceted polygon creases.
4. Preserves 100% watertight topology with zero mesh seams.
5. Highly parallelized with ProcessPoolExecutor across all CPU cores.
"""

import os
import glob
import struct
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

BASE_DIR = "/home/mnunes/uo3d_map/godot_project"

MAPS = [
    ("Felucca (Map 0)", os.path.join(BASE_DIR, "terrain_chunks_atlas"), [62, 230]),
    ("Trammel (Map 1)", os.path.join(BASE_DIR, "terrain_chunks_atlas_map1"), [62, 63, 230]),
    ("Ilshenar (Map 2)", os.path.join(BASE_DIR, "terrain_chunks_atlas_map2"), [33, 177, 1500]),
    ("Tokuno (Map 4)", os.path.join(BASE_DIR, "terrain_chunks_atlas_map4"), [144, 1500]),
    ("Ter Mur (Map 5)", os.path.join(BASE_DIR, "terrain_chunks_atlas_map5"), [184, 1500]),
]

BEVEL_AMOUNT = 0.28  # 28cm bevel on 1-meter square tiles


def process_chunk(args):
    path, water_slots = args
    try:
        with open(path, "rb") as fp:
            data = fp.read()
    except Exception as e:
        return (path, 0, f"Read error: {e}")

    if len(data) < 28 or data[:4] != b"glTF":
        return (path, 0, "Invalid GLB")

    chunk_len = struct.unpack("<II", data[12:20])[0]
    json_bytes = data[20:20+chunk_len]
    try:
        json_data = json.loads(json_bytes.decode("utf-8"))
    except Exception as e:
        return (path, 0, f"JSON error: {e}")

    bin_offset = 20 + chunk_len + 8
    bin_bytes = bytearray(data[bin_offset:])

    accessors = json_data.get("accessors", [])
    buffer_views = json_data.get("bufferViews", [])
    if len(accessors) < 3:
        return (path, 0, "Missing accessors")

    pos_offset = buffer_views[accessors[0]["bufferView"]]["byteOffset"]
    norm_offset = buffer_views[accessors[1]["bufferView"]]["byteOffset"]
    uv_offset = buffer_views[accessors[2]["bufferView"]]["byteOffset"]

    num_cells = accessors[0]["count"] // 4
    if num_cells < 4096:
        return (path, 0, "Non-standard chunk")

    # 1. Map water cells
    is_water = [[False]*64 for _ in range(64)]
    water_cells_found = 0
    for cy in range(64):
        for cx in range(64):
            cell = cy * 64 + cx
            u, v = struct.unpack_from("<2f", bin_bytes, uv_offset + cell * 4 * 8)
            col = int(round(u * 40 - 0.5))
            row = int(round(v * 40 - 0.5))
            slot = row * 40 + col
            y0 = struct.unpack_from("<3f", bin_bytes, pos_offset + cell * 4 * 12)[1]

            # Water criteria: slot matches water/riverbed or elevation <= -1.75m
            if slot in water_slots or y0 <= -1.75:
                is_water[cy][cx] = True
                water_cells_found += 1

    # Skip chunks that are 100% land or 100% water (no shoreline)
    if water_cells_found == 0 or water_cells_found == 4096:
        return (path, 0, "No shoreline")

    # 2. Bevel 90-degree shoreline corners
    corners_smoothed = 0
    for gz in range(1, 64):
        for gx in range(1, 64):
            tl = 1 if is_water[gz-1][gx-1] else 0
            tr = 1 if is_water[gz-1][gx] else 0
            bl = 1 if is_water[gz][gx-1] else 0
            br = 1 if is_water[gz][gx] else 0
            nw = tl + tr + bl + br

            dx, dz = 0.0, 0.0
            if nw == 1:
                # Convex 90-deg corner pointing into water: bevel away from the water cell
                dx = (1 if tl or bl else -1) * BEVEL_AMOUNT
                dz = (1 if tl or tr else -1) * BEVEL_AMOUNT
            elif nw == 3:
                # Concave 90-deg corner indented into land: bevel towards the water
                tl_l = 1 - tl; tr_l = 1 - tr; bl_l = 1 - bl; br_l = 1 - br
                dx = -(1 if tl_l or bl_l else -1) * BEVEL_AMOUNT
                dz = -(1 if tl_l or tr_l else -1) * BEVEL_AMOUNT

            if dx != 0.0 or dz != 0.0:
                corners_smoothed += 1
                v_indices = [
                    ((gz - 1) * 64 + (gx - 1)) * 4 + 3,
                    ((gz - 1) * 64 + gx) * 4 + 2,
                    (gz * 64 + (gx - 1)) * 4 + 1,
                    (gz * 64 + gx) * 4 + 0,
                ]
                for vi in v_indices:
                    x, y, z = struct.unpack_from("<3f", bin_bytes, pos_offset + vi * 12)
                    struct.pack_into("<3f", bin_bytes, pos_offset + vi * 12, x + dx, y, z + dz)

    # 3. Compute continuous smooth normals across all shoreline quads
    face_normals = [[(0.0, 1.0, 0.0)]*64 for _ in range(64)]
    for cy in range(64):
        for cx in range(64):
            base = (cy * 64 + cx) * 4
            p0 = struct.unpack_from("<3f", bin_bytes, pos_offset + (base + 0) * 12)
            p1 = struct.unpack_from("<3f", bin_bytes, pos_offset + (base + 1) * 12)
            p2 = struct.unpack_from("<3f", bin_bytes, pos_offset + (base + 2) * 12)
            e1 = (p1[0]-p0[0], p1[1]-p0[1], p1[2]-p0[2])
            e2 = (p2[0]-p0[0], p2[1]-p0[1], p2[2]-p0[2])
            nx = e1[1]*e2[2] - e1[2]*e2[1]
            ny = e1[2]*e2[0] - e1[0]*e2[2]
            nz = e1[0]*e2[1] - e1[1]*e2[0]
            l = math.sqrt(nx*nx + ny*ny + nz*nz)
            if l > 1e-6:
                face_normals[cy][cx] = (nx/l, ny/l, nz/l)

    for gz in range(65):
        for gx in range(65):
            acc_nx, acc_ny, acc_nz = 0.0, 0.0, 0.0
            cnt = 0
            for cy in [gz - 1, gz]:
                for cx in [gx - 1, gx]:
                    if 0 <= cy < 64 and 0 <= cx < 64:
                        fn = face_normals[cy][cx]
                        acc_nx += fn[0]; acc_ny += fn[1]; acc_nz += fn[2]
                        cnt += 1
            if cnt > 0:
                l = math.sqrt(acc_nx*acc_nx + acc_ny*acc_ny + acc_nz*acc_nz)
                avg_n = (acc_nx/l, acc_ny/l, acc_nz/l) if l > 1e-6 else (0.0, 1.0, 0.0)

                if gx > 0 and gz > 0:
                    struct.pack_into("<3f", bin_bytes, norm_offset + (((gz-1)*64 + (gx-1))*4 + 3)*12, *avg_n)
                if gx < 64 and gz > 0:
                    struct.pack_into("<3f", bin_bytes, norm_offset + (((gz-1)*64 + gx)*4 + 2)*12, *avg_n)
                if gx > 0 and gz < 64:
                    struct.pack_into("<3f", bin_bytes, norm_offset + ((gz*64 + (gx-1))*4 + 1)*12, *avg_n)
                if gx < 64 and gz < 64:
                    struct.pack_into("<3f", bin_bytes, norm_offset + ((gz*64 + gx)*4 + 0)*12, *avg_n)

    # Re-pack and write GLB
    json_str = json.dumps(json_data, separators=(",", ":"))
    pad = (4 - (len(json_str) % 4)) % 4
    json_str += " " * pad
    json_b = json_str.encode("utf-8")

    total_len = 12 + 8 + len(json_b) + 8 + len(bin_bytes)
    new_glb = bytearray()
    new_glb.extend(struct.pack("<4sII", b"glTF", 2, total_len))
    new_glb.extend(struct.pack("<II", len(json_b), 0x4E4F534A))
    new_glb.extend(json_b)
    new_glb.extend(struct.pack("<II", len(bin_bytes), 0x004E4942))
    new_glb.extend(bin_bytes)

    with open(path, "wb") as fp:
        fp.write(new_glb)

    return (path, corners_smoothed, "OK")


def process_map(map_name, folder, water_slots):
    print("=" * 70)
    print(f"=== Suavizando Bordas de Rios e Mares: {map_name} ===")
    print(f"=== Pasta: {folder} ===")
    print("=" * 70)

    chunks = sorted(glob.glob(os.path.join(folder, "**/chunk_*.glb"), recursive=True))
    print(f"[*] Encontrados {len(chunks)} chunks para análise.")

    t0 = time.time()
    total_chunks_smoothed = 0
    total_corners_smoothed = 0
    errors = 0

    workers = os.cpu_count() or 8
    tasks = [(c, water_slots) for c in chunks]

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_chunk, t): t[0] for t in tasks}
        for future in as_completed(futures):
            path, c_corners, status = future.result()
            if status == "OK":
                total_chunks_smoothed += 1
                total_corners_smoothed += c_corners
            elif status not in ["No shoreline", "Non-standard chunk"]:
                errors += 1
                print(f"[!] Erro em {os.path.basename(path)}: {status}")

    dt = time.time() - t0
    print(f"\n[✓] {map_name} concluído em {dt:.2f}s!")
    print(f"    Chunks de litoral/rio suavizados: {total_chunks_smoothed}")
    print(f"    Quinas e dentes 90° chanfrados/arredondados: {total_corners_smoothed:,}")
    print(f"    Normais Gouraud contínuas calculadas para todas as margens.")
    if errors > 0:
        print(f"    [!] Erros: {errors}")


def main():
    start_total = time.time()
    for map_name, folder, water_slots in MAPS:
        if os.path.exists(folder):
            process_map(map_name, folder, water_slots)

    # Clean Godot import cache so new smoothed meshes load immediately
    print("\n[*] Limpando cache do Godot (.godot/imported/)...")
    cache_dir = os.path.join(BASE_DIR, ".godot", "imported")
    if os.path.exists(cache_dir):
        count_removed = 0
        for f in glob.glob(os.path.join(cache_dir, "chunk_*.scn")):
            try:
                os.remove(f)
                count_removed += 1
            except Exception:
                pass
        print(f"[✓] Removidos {count_removed} arquivos .scn antigos do cache.")

    total_time = time.time() - start_total
    print(f"\n[✓✓✓] Sucesso Absoluto! Todos os litorais e rios suavizados em {total_time:.2f}s.")


if __name__ == "__main__":
    main()
