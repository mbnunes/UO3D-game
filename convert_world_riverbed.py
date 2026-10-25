#!/usr/bin/env python3
"""
convert_world_riverbed.py

Converts water tiles across all of Felucca (Map 0) and Trammel (Map 1):
1. Replaces blue water (Slot 230) with uniform brown riverbed/seabed (Slot 62).
2. Lowers depth from Z = -5 (Y = -0.60m) to Z = -15 (Y = -1.80m).
3. Eliminates blue shoreline slope steps by lowering shore transition vertices to Y = -1.80m.
4. Also converts ocean_chunk.glb for universal deep ocean fallback.
5. Highly parallelized with ProcessPoolExecutor.
"""

import os
import glob
import struct
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

BASE_DIR = "/home/mnunes/uo3d_map/godot_project"
MAPS = [
    ("Felucca (Map 0)", os.path.join(BASE_DIR, "terrain_chunks_atlas")),
    ("Trammel (Map 1)", os.path.join(BASE_DIR, "terrain_chunks_atlas_map1")),
]

SLOTS_PER_SIDE = 40
ATLAS_DIM = 2560
inv_slots = 1.0 / SLOTS_PER_SIDE
delta = 0.5 / ATLAS_DIM

target_slot = 62  # Brown mud / riverbed
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

target_y = -15.0 * 0.12  # -1.80m


def process_file(path):
    try:
        with open(path, "rb") as fp:
            data = fp.read()
    except Exception as e:
        return (path, 0, 0, f"Error reading: {e}")

    if len(data) < 28 or data[:4] != b"glTF":
        return (path, 0, 0, "Not a valid GLB")

    chunk_len = struct.unpack("<II", data[12:20])[0]
    json_bytes = data[20:20+chunk_len]
    try:
        json_data = json.loads(json_bytes.decode("utf-8"))
    except Exception as e:
        return (path, 0, 0, f"JSON parse error: {e}")

    bin_offset = 20 + chunk_len + 8
    bin_bytes = bytearray(data[bin_offset:])

    accessors = json_data.get("accessors", [])
    buffer_views = json_data.get("bufferViews", [])
    if len(accessors) < 3:
        return (path, 0, 0, "Less than 3 accessors")

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
    for cell_idx in range(num_cells):
        vert_base = cell_idx * 4
        u, v = struct.unpack_from("<2f", bin_bytes, uv_offset + vert_base * 8)
        col = int(round(u * SLOTS_PER_SIDE - 0.5))
        row = int(round(v * SLOTS_PER_SIDE - 0.5))
        slot = row * SLOTS_PER_SIDE + col

        if slot == 230:
            cells_converted += 1
            for k in range(4):
                v_idx = vert_base + k
                # 1. Update UV to Slot 62 (brown mud)
                struct.pack_into("<2f", bin_bytes, uv_offset + v_idx * 8, target_uvs[k][0], target_uvs[k][1])
                # 2. Update Y to -1.80m
                x, y, z = struct.unpack_from("<3f", bin_bytes, pos_offset + v_idx * 12)
                struct.pack_into("<3f", bin_bytes, pos_offset + v_idx * 12, x, target_y, z)
                # 3. Update normal to upward (0, 1, 0)
                struct.pack_into("<3f", bin_bytes, norm_offset + v_idx * 12, 0.0, 1.0, 0.0)

    slopes_flattened = 0
    if cells_converted > 0:
        for i in range(pos_acc["count"]):
            x, y, z = struct.unpack_from("<3f", bin_bytes, pos_offset + i * 12)
            if abs(y - (-0.60)) < 0.05:
                struct.pack_into("<3f", bin_bytes, pos_offset + i * 12, x, target_y, z)
                slopes_flattened += 1

        # Update AABB min Y in accessor 0
        if "min" in pos_acc and len(pos_acc["min"]) >= 2:
            pos_acc["min"][1] = min(pos_acc["min"][1], target_y)

        # Rebuild GLB
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


def process_map(map_name, folder):
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

    total_converted_chunks = 0
    total_water_cells = 0
    total_slopes_flattened = 0
    errors = 0

    workers = os.cpu_count() or 8
    print(f"[*] Processing with {workers} parallel processes...")

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_file, c): c for c in chunks}
        for future in as_completed(futures):
            path, c_cells, c_slopes, status = future.result()
            if status != "OK":
                errors += 1
                print(f"[!] Error on {os.path.basename(path)}: {status}")
            elif c_cells > 0:
                total_converted_chunks += 1
                total_water_cells += c_cells
                total_slopes_flattened += c_slopes

    dt = time.time() - t0
    print(f"\n[✓] {map_name} Concluído em {dt:.2f}s!")
    print(f"    Chunks com água convertidos: {total_converted_chunks}")
    print(f"    Total de células de água -> lama (Slot 62): {total_water_cells:,}")
    print(f"    Total de declives nivelados a Y=-1.80m: {total_slopes_flattened:,}")
    if errors > 0:
        print(f"    [!] Erros encontrados: {errors}")


def main():
    start_total = time.time()
    for map_name, folder in MAPS:
        if os.path.exists(folder):
            process_map(map_name, folder)
        else:
            print(f"[!] Pasta não encontrada: {folder}")

    # Clear Godot import cache
    print("\n[*] Limpando arquivos de cache do Godot (.godot/imported/)...")
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
        print(f"[✓] Removidos {count_removed} arquivos .scn antigos do cache do Godot.")

    total_time = time.time() - start_total
    print(f"\n[✓✓✓] Sucesso Absoluto! Felucca e Trammel convertidos em {total_time:.2f}s.")


if __name__ == "__main__":
    main()
