#!/usr/bin/env python3
"""
enrich_community_buildings_mul_info.py

Enriches all info.json files in uo3d-community-buildings with exact MUL/UOP source pointers:
- File names (mapX.mul, staticsX.mul, staidxX.mul, mapXLegacyMUL.uop)
- Block coordinates and block indices (bx, by, block_index)
- Exact file byte offsets in staidx, statics, and map.mul
- Static items count per block
- UOP entry references (uop_entry file, entry_name, block_in_entry)
"""

import os
import sys
import glob
import json
import struct
import time

UOC_DIR = "/opt/hd_jogos/UOC"
COMMUNITY_DIR = "/home/mnunes/uo3d-community-buildings"

MAPS_CONFIG = {
    0: {
        "name": "Felucca",
        "map_file": "map0.mul",
        "statics_file": "statics0.mul",
        "staidx_file": "staidx0.mul",
        "uop_file": "map0LegacyMUL.uop",
        "w_blocks": 896,
        "h_blocks": 512,
    },
    1: {
        "name": "Trammel",
        "map_file": "map1.mul",
        "statics_file": "statics1.mul",
        "staidx_file": "staidx1.mul",
        "uop_file": "map1LegacyMUL.uop",
        "w_blocks": 896,
        "h_blocks": 512,
    },
    2: {
        "name": "Ilshenar",
        "map_file": "map2.mul",
        "statics_file": "statics2.mul",
        "staidx_file": "staidx2.mul",
        "uop_file": "map2LegacyMUL.uop",
        "w_blocks": 288,
        "h_blocks": 200,
    },
    3: {
        "name": "Malas",
        "map_file": "map3.mul",
        "statics_file": "statics3.mul",
        "staidx_file": "staidx3.mul",
        "uop_file": "map3LegacyMUL.uop",
        "w_blocks": 320,
        "h_blocks": 256,
    },
    4: {
        "name": "Tokuno",
        "map_file": "map4.mul",
        "statics_file": "statics4.mul",
        "staidx_file": "staidx4.mul",
        "uop_file": "map4LegacyMUL.uop",
        "w_blocks": 181,
        "h_blocks": 181,
    },
    5: {
        "name": "TerMur",
        "map_file": "map5.mul",
        "statics_file": "statics5.mul",
        "staidx_file": "staidx5.mul",
        "uop_file": "map5LegacyMUL.uop",
        "w_blocks": 160,
        "h_blocks": 512,
    },
}


def load_staidx_cache():
    staidx_cache = {}
    for map_idx, cfg in MAPS_CONFIG.items():
        staidx_path = os.path.join(UOC_DIR, cfg["staidx_file"])
        if os.path.exists(staidx_path):
            with open(staidx_path, "rb") as f:
                staidx_cache[map_idx] = f.read()
            print(f"[✓] Loaded {cfg['staidx_file']} ({len(staidx_cache[map_idx]) / 1024:.1f} KB)")
        else:
            print(f"[!] Warning: {staidx_path} not found!")
    return staidx_cache


def enrich_building_info(info_path, staidx_cache):
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, f"Failed to read JSON: {e}"

    map_idx = data.get("map_index")
    if map_idx is None:
        # Fallback deduce from folder name
        for m in range(6):
            if f"map{m}" in info_path:
                map_idx = m
                break
        if map_idx is None:
            map_idx = 0

    if map_idx not in MAPS_CONFIG or map_idx not in staidx_cache:
        return False, f"Unknown map_index {map_idx}"

    cfg = MAPS_CONFIG[map_idx]
    wb = data.get("world_bounds")
    if not wb or "min_x" not in wb or "max_x" not in wb:
        return False, "world_bounds missing in info.json"

    min_x, max_x = wb["min_x"], wb["max_x"]
    min_y, max_y = wb["min_y"], wb["max_y"]

    min_bx, max_bx = min_x // 8, max_x // 8
    min_by, max_by = min_y // 8, max_y // 8

    h_blocks = cfg["h_blocks"]
    w_blocks = cfg["w_blocks"]
    staidx_bytes = staidx_cache[map_idx]

    blocks = []
    for bx in range(min_bx, max_bx + 1):
        if bx < 0 or bx >= w_blocks:
            continue
        for by in range(min_by, max_by + 1):
            if by < 0 or by >= h_blocks:
                continue
            b_idx = bx * h_blocks + by
            off_staidx = b_idx * 12
            if off_staidx + 12 <= len(staidx_bytes):
                lookup, length, extra = struct.unpack_from("<III", staidx_bytes, off_staidx)
            else:
                lookup, length = 0xFFFFFFFF, 0

            blocks.append({
                "block_x": bx,
                "block_y": by,
                "block_index": b_idx,
                "staidx_offset": off_staidx,
                "statics_offset": lookup if lookup != 0xFFFFFFFF else None,
                "statics_length": length if lookup != 0xFFFFFFFF else 0,
                "static_items_count": (length // 7) if lookup != 0xFFFFFFFF else 0,
                "map_offset": b_idx * 196 + 4,
                "uop_entry": {
                    "file": cfg["uop_file"],
                    "entry_name": f"build/map{map_idx}legacymul/{b_idx // 4096:08d}.dat",
                    "entry_index": b_idx // 4096,
                    "block_in_entry": b_idx % 4096,
                },
            })

    data["source_data"] = {
        "mul_files": {
            "map_file": cfg["map_file"],
            "statics_file": cfg["statics_file"],
            "staidx_file": cfg["staidx_file"],
            "uop_file": cfg["uop_file"],
        },
        "block_grid": {
            "w_blocks": w_blocks,
            "h_blocks": h_blocks,
            "min_block_x": min_bx,
            "max_block_x": max_bx,
            "min_block_y": min_by,
            "max_block_y": max_by,
            "total_blocks": len(blocks),
        },
        "blocks": blocks,
    }

    try:
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True, "OK"
    except Exception as e:
        return False, f"Failed to write JSON: {e}"


def main():
    print("==================================================================")
    print("=== Enriching Community Buildings info.json with MUL/UOP Data  ===")
    print("==================================================================")

    t0 = time.time()
    staidx_cache = load_staidx_cache()

    info_files = sorted(glob.glob(os.path.join(COMMUNITY_DIR, "**/info.json"), recursive=True))
    total_files = len(info_files)
    print(f"\n[*] Found {total_files} info.json files across all maps.")

    success_count = 0
    error_count = 0

    for i, path in enumerate(info_files):
        ok, msg = enrich_building_info(path, staidx_cache)
        if ok:
            success_count += 1
        else:
            error_count += 1
            print(f"[!] Error on {path}: {msg}")

        if (i + 1) % 1000 == 0 or (i + 1) == total_files:
            elapsed = time.time() - t0
            print(f"[*] Processed {i + 1}/{total_files} buildings ({elapsed:.1f}s, {(i + 1)/elapsed:.1f} bld/s)...")

    total_time = time.time() - t0
    print("\n==================================================================")
    print(f"[✓✓✓] Concluído em {total_time:.2f}s!")
    print(f"Total atualizado com sucesso: {success_count}/{total_files}")
    if error_count > 0:
        print(f"[!] Erros encontrados: {error_count}")
    print("==================================================================")


if __name__ == "__main__":
    main()
