#!/usr/bin/env python3
"""
convert_all_britain_riverbed.py

Applies uniform brown riverbed (Slot 62, TexID 76) at depth Z = -15 (Y = -1.80m)
to all water tiles and eliminates internal water slopes in the Britain region (Felucca).
"""

import os
import struct
import json
import shutil

OUTPUT_DIR = "/home/mnunes/uo3d_map/godot_project/terrain_chunks_atlas"

SLOTS_PER_SIDE = 40
ATLAS_DIM = 2560
inv_slots = 1.0 / SLOTS_PER_SIDE
delta = 0.5 / ATLAS_DIM

# Target Slot: 62 (TexID 76 - Brown edge/riverbed)
target_slot = 62
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

target_y = -15.0 * 0.12 # -1.80m

def process_chunk(path):
    if not os.path.exists(path):
        return None

    bak = path + ".clean_orig"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)

    with open(bak, "rb") as fp:
        data = fp.read()

    magic, version, length = struct.unpack("<4sII", data[:12])
    chunk_len, chunk_type = struct.unpack("<II", data[12:20])
    json_data = json.loads(data[20:20+chunk_len].decode("utf-8"))
    bin_offset = 20 + chunk_len + 8
    bin_bytes = bytearray(data[bin_offset:])

    uv_acc = json_data["accessors"][2]
    uv_bv = json_data["bufferViews"][uv_acc["bufferView"]]
    uv_offset = uv_bv["byteOffset"]

    pos_acc = json_data["accessors"][0]
    pos_bv = json_data["bufferViews"][pos_acc["bufferView"]]
    pos_offset = pos_bv["byteOffset"]

    norm_acc = json_data["accessors"][1]
    norm_bv = json_data["bufferViews"][norm_acc["bufferView"]]
    norm_offset = norm_bv["byteOffset"]

    cells_converted = 0
    for cell_idx in range(64 * 64):
        vert_base = cell_idx * 4
        u, v = struct.unpack_from("<2f", bin_bytes, uv_offset + vert_base * 8)
        col = int(round(u * SLOTS_PER_SIDE - 0.5))
        row = int(round(v * SLOTS_PER_SIDE - 0.5))
        slot = row * SLOTS_PER_SIDE + col

        # If water tile (slot 230)
        if slot == 230:
            cells_converted += 1
            for k in range(4):
                v_idx = vert_base + k
                # 1. Update UV to Slot 62 (brown)
                struct.pack_into("<2f", bin_bytes, uv_offset + v_idx * 8, target_uvs[k][0], target_uvs[k][1])
                # 2. Update Y to -1.80m
                x, y, z = struct.unpack_from("<3f", bin_bytes, pos_offset + v_idx * 12)
                struct.pack_into("<3f", bin_bytes, pos_offset + v_idx * 12, x, target_y, z)
                # 3. Update normal to upward (0, 1, 0)
                struct.pack_into("<3f", bin_bytes, norm_offset + v_idx * 12, 0.0, 1.0, 0.0)

    # Flatten any underwater slopes connected to water that were at y = -0.60
    slopes_flattened = 0
    if cells_converted > 0:
        for i in range(pos_acc["count"]):
            x, y, z = struct.unpack_from("<3f", bin_bytes, pos_offset + i * 12)
            if abs(y - (-0.60)) < 0.05:
                struct.pack_into("<3f", bin_bytes, pos_offset + i * 12, x, target_y, z)
                slopes_flattened += 1

    # Rebuild GLB
    json_str = json.dumps(json_data, separators=(",", ":"))
    while len(json_str) % 4 != 0:
        json_str += " "
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

    return (cells_converted, slopes_flattened)

def main():
    print("==================================================================")
    print("=== Converting Britain Riverbed: Blue Water -> Brown (Slot 62) ===")
    print("=== Depth: Uniform Z = -15 (Y = -1.80m), No Internal Slopes ======")
    print("==================================================================")

    total_cells = 0
    total_slopes = 0
    chunks_modified = 0

    for cx in range(21, 25): # 21, 22, 23, 24
        for cy in range(24, 29): # 24, 25, 26, 27, 28
            sx = cx // 8
            sy = cy // 8
            path = os.path.join(OUTPUT_DIR, f"sector_{sx:02d}_{sy:02d}", f"chunk_{cx}_{cy}.glb")
            res = process_chunk(path)
            if res is not None:
                c, s = res
                total_cells += c
                total_slopes += s
                if c > 0 or s > 0:
                    chunks_modified += 1
                    print(f"[✓] Chunk ({cx:2d}, {cy:2d}): {c:4d} tiles d'água -> marrom (Slot 62), {s:3d} vértices de declive nivelados a Y=-1.80")

    print("\n[✓✓✓] Concluído com Sucesso!")
    print(f"Total de chunks modificados: {chunks_modified}")
    print(f"Total de tiles d'água convertidos: {total_cells}")
    print(f"Total de declives nivelados: {total_slopes}")

if __name__ == "__main__":
    main()
