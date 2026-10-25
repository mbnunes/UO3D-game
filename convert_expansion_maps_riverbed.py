#!/usr/bin/env python3
"""
convert_expansion_maps_riverbed.py

Converts water tiles across Ilshenar (Map 2), Tokuno (Map 4), and Ter Mur (Map 5):
1. Replaces blue water tiles with uniform brown riverbed/seabed (Slot 1500 - TexID 76).
2. Sets water depth uniformly to the riverbed/seabed level (Z_water - 10, i.e. Y - 1.20m).
3. Eliminates blue shoreline slope steps by leveling transition vertices to the riverbed.
4. Also converts ocean_chunk.glb for universal ocean/void fallback.
5. Highly parallelized with ProcessPoolExecutor.
"""

import os
import glob
import struct
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

BASE_DIR = "/home/mnunes/uo3d_map/godot_project"

SLOTS_PER_SIDE = 40
ATLAS_DIM = 2560
inv_slots = 1.0 / SLOTS_PER_SIDE
delta = 0.5 / ATLAS_DIM

# Target Slot: 1500 (TexID 76 - Brown mud / riverbed)
target_slot = 1500
t_col = target_slot % SLOTS_PER_SIDE
t_row = target_slot // SLOTS_PER_SIDE
u0 = t_col * inv_slots + delta
u1 = (t_col + 1) * inv_slots - delta
v0 = t_row * inv_slots + delta
v1 = (t_row + 1) * inv_slots - delta

target_uvs = [
    (u0, v0),
    (u1, v0),
    (u0, v1),
    (u1, v1)
]

MAP_SETTINGS = {
    2: {
        "name": "Ilshenar (Map 2)",
        "folder": os.path.join(BASE_DIR, "terrain_chunks_atlas_map2"),
        "water_slot": 177,
        "default_water_y": -3.96, # Z = -33.0
        "default_bed_y": -5.16,   # Z = -43.0
        "delta_y": -1.20,
    },
    4: {
        "name": "Tokuno (Map 4)",
        "folder": os.path.join(BASE_DIR, "terrain_chunks_atlas_map4"),
        "water_slot": 144,
        "default_water_y": -0.60, # Z = -5.0
        "default_bed_y": -1.80,   # Z = -15.0
        "delta_y": -1.20,
    },
    5: {
        "name": "Ter Mur (Map 5)",
        "folder": os.path.join(BASE_DIR, "terrain_chunks_atlas_map5"),
        "water_slot": 184,
        "default_water_y": -6.00, # Z = -50.0
        "default_bed_y": -7.20,   # Z = -60.0
        "delta_y": -1.20,
    },
}


def process_chunk_task(args):
    path, water_slot, default_water_y, default_bed_y, delta_y = args
    try:
        with open(path, "rb") as fp:
            data = fp.read()
    except Exception as e:
        return (path, 0, 0, f"Read error: {e}")

    if len(data) < 28 or data[:4] != b"glTF":
        return (path, 0, 0, "Invalid GLB")

    chunk_len = struct.unpack("<II", data[12:20])[0]
    json_bytes = data[20:20+chunk_len]
    try:
        json_data = json.loads(json_bytes.decode("utf-8"))
    except Exception as e:
        return (path, 0, 0, f"JSON error: {e}")

    bin_offset = 20 + chunk_len + 8
    bin_bytes = bytearray(data[bin_offset:])

    accessors = json_data.get("accessors", [])
    buffer_views = json_data.get("bufferViews", [])
    if len(accessors) < 3:
        return (path, 0, 0, "Missing accessors")

    pos_acc = accessors[0]
    pos_offset = buffer_views[pos_acc["bufferView"]].get("byteOffset", 0)

    norm_acc = accessors[1]
    norm_offset = buffer_views[norm_acc["bufferView"]].get("byteOffset", 0)

    uv_acc = accessors[2]
    uv_offset = buffer_views[uv_acc["bufferView"]].get("byteOffset", 0)

    num_cells = pos_acc["count"] // 4
    if num_cells == 0:
        return (path, 0, 0, "0 cells")

    cells_converted = 0
    water_y_levels = set()
    water_vertices = set()

    for cell_idx in range(num_cells):
        vert_base = cell_idx * 4
        u, v = struct.unpack_from("<2f", bin_bytes, uv_offset + vert_base * 8)
        col = int(round(u * SLOTS_PER_SIDE - 0.5))
        row = int(round(v * SLOTS_PER_SIDE - 0.5))
        slot = row * SLOTS_PER_SIDE + col

        if slot == water_slot:
            cells_converted += 1
            for k in range(4):
                v_idx = vert_base + k
                water_vertices.add(v_idx)
                # 1. Update UV to target_slot (Slot 1500)
                struct.pack_into("<2f", bin_bytes, uv_offset + v_idx * 8, target_uvs[k][0], target_uvs[k][1])
                # 2. Update Y
                x, y, z = struct.unpack_from("<3f", bin_bytes, pos_offset + v_idx * 12)
                water_y_levels.add(round(y, 2))
                if abs(y - default_water_y) < 0.05:
                    new_y = default_bed_y
                else:
                    new_y = y + delta_y
                struct.pack_into("<3f", bin_bytes, pos_offset + v_idx * 12, x, new_y, z)
                # 3. Update normal to upward
                struct.pack_into("<3f", bin_bytes, norm_offset + v_idx * 12, 0.0, 1.0, 0.0)

    slopes_flattened = 0
    if cells_converted > 0:
        for i in range(pos_acc["count"]):
            if i in water_vertices:
                continue
            x, y, z = struct.unpack_from("<3f", bin_bytes, pos_offset + i * 12)
            for wy in water_y_levels:
                if abs(y - wy) < 0.05:
                    if abs(wy - default_water_y) < 0.05:
                        new_y = default_bed_y
                    else:
                        new_y = wy + delta_y
                    struct.pack_into("<3f", bin_bytes, pos_offset + i * 12, x, new_y, z)
                    slopes_flattened += 1
                    break

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

    return (path, cells_converted, slopes_flattened, "OK")


def process_map(map_id):
    cfg = MAP_SETTINGS[map_id]
    map_name = cfg["name"]
    folder = cfg["folder"]

    print("=" * 70)
    print(f"=== Converting Map: {map_name} ===")
    print(f"=== Path: {folder} ===")
    print("=" * 70)

    chunks = sorted(glob.glob(os.path.join(folder, "**/chunk_*.glb"), recursive=True))
    ocean_chunk = os.path.join(folder, "ocean_chunk.glb")
    if os.path.exists(ocean_chunk):
        chunks.append(ocean_chunk)

    print(f"[*] Found {len(chunks)} files to examine.")
    t0 = time.time()

    total_converted = 0
    total_water_cells = 0
    total_slopes = 0
    errors = 0

    workers = os.cpu_count() or 8
    tasks = [(c, cfg["water_slot"], cfg["default_water_y"], cfg["default_bed_y"], cfg["delta_y"]) for c in chunks]

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_chunk_task, t): t[0] for t in tasks}
        for future in as_completed(futures):
            path, c_cells, c_slopes, status = future.result()
            if status != "OK":
                errors += 1
                print(f"[!] Error on {os.path.basename(path)}: {status}")
            elif c_cells > 0:
                total_converted += 1
                total_water_cells += c_cells
                total_slopes += c_slopes

    dt = time.time() - t0
    print(f"\n[✓] {map_name} Concluído em {dt:.2f}s!")
    print(f"    Chunks com água convertidos: {total_converted}")
    print(f"    Total de células de água -> lama (Slot 1500): {total_water_cells:,}")
    print(f"    Total de declives nivelados: {total_slopes:,}")
    if errors > 0:
        print(f"    [!] Erros: {errors}")


def main():
    start_total = time.time()
    for map_id in [2, 4, 5]:
        process_map(map_id)

    # Clean Godot import cache for maps 2, 4, 5
    print("\n[*] Limpando arquivos .scn antigos do cache do Godot (.godot/imported/)...")
    cache_dir = os.path.join(BASE_DIR, ".godot", "imported")
    if os.path.exists(cache_dir):
        count_removed = 0
        for f in glob.glob(os.path.join(cache_dir, "chunk_*.scn")):
            try:
                os.remove(f)
                count_removed += 1
            except Exception:
                pass
        for f in glob.glob(os.path.join(cache_dir, "ocean_chunk*.scn")):
            try:
                os.remove(f)
                count_removed += 1
            except Exception:
                pass
        print(f"[✓] Removidos {count_removed} arquivos .scn do cache do Godot.")

    total_time = time.time() - start_total
    print(f"\n[✓✓✓] Sucesso Total! Ilshenar, Tokuno e Ter Mur convertidos em {total_time:.2f}s.")


if __name__ == "__main__":
    main()
