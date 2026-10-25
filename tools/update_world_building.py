#!/usr/bin/env python3
"""
update_world_building.py

Instantly syncs a refined/modeled community building into the live Godot world.

Usage:
  python update_world_building.py <path_or_building_id>
  python update_world_building.py --all

Examples:
  python update_world_building.py community_assets/map0_felucca/britain/building_17_the_hammer_and_anvil_blacksmith
  python update_world_building.py lord_british_castle
  python update_world_building.py --all
"""

import os
import sys
import json
import shutil
import glob
from pathlib import Path

PROJECT_ROOT = Path("/home/mnunes/uo3d_map")
COMMUNITY_ROOT = PROJECT_ROOT / "community_assets"
GODOT_CUSTOM_DIR = PROJECT_ROOT / "godot_project" / "custom_buildings"
MANIFEST_PATH = GODOT_CUSTOM_DIR / "custom_buildings.json"

def find_building_dir(query):
    # Direct path
    p = Path(query)
    if p.is_dir() and (p / "info.json").exists():
        return p.resolve()

    # Search in community_assets
    matches = []
    for info_file in COMMUNITY_ROOT.glob("**/info.json"):
        bdir = info_file.parent
        if query.lower() in bdir.name.lower():
            matches.append(bdir)

    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        print(f"[!] Multiple buildings match '{query}':")
        for m in matches[:10]:
            print(f"    - {m.relative_to(PROJECT_ROOT)}")
        if len(matches) > 10:
            print(f"    ... and {len(matches) - 10} more.")
        print("[!] Please provide the more specific path.")
        return None
    else:
        print(f"[X] No building matching '{query}' found.")
        return None

def load_custom_manifest():
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_custom_manifest(manifest):
    GODOT_CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

def update_building(bdir):
    info_file = bdir / "info.json"
    if not info_file.exists():
        print(f"[X] Missing info.json in {bdir}")
        return False

    with open(info_file, "r", encoding="utf-8") as f:
        info = json.load(f)

    building_id = info.get("building_id", bdir.name)
    building_name = info.get("name", building_id)
    map_index = info.get("map_index", 0)
    world_bounds = info.get("world_bounds", {})

    center_x = world_bounds.get("center_x", 0.0)
    center_y = world_bounds.get("center_y", 0.0)
    center_z_elevation = world_bounds.get("center_z_elevation", 0.0)

    # Check for model: prioritize model_refined.glb over model_base.glb
    refined_glb = bdir / "model_refined.glb"
    base_glb = bdir / "model_base.glb"

    if refined_glb.exists():
        src_model = refined_glb
        model_type = "Refined Community Model"
    elif base_glb.exists():
        src_model = base_glb
        model_type = "Base Model"
    else:
        print(f"[X] No .glb model found in {bdir}")
        return False

    # Calculate chunk
    chunk_x = int(center_x) // 64
    chunk_y = int(center_y) // 64

    # Relative to chunk corner
    rel_x = center_x - (chunk_x * 64.0)
    rel_y = center_z_elevation
    rel_z = center_y - (chunk_y * 64.0)

    GODOT_CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    dest_filename = f"{building_id}.glb"
    dest_path = GODOT_CUSTOM_DIR / dest_filename

    shutil.copy2(src_model, dest_path)

    # Update manifest
    manifest = load_custom_manifest()
    # Remove existing entry for this building if present
    manifest = [item for item in manifest if item.get("building_id") != building_id]

    entry = {
        "building_id": building_id,
        "name": building_name,
        "map_index": map_index,
        "model_path": f"res://custom_buildings/{dest_filename}",
        "chunk": [chunk_x, chunk_y],
        "position": [round(rel_x, 4), round(rel_y, 4), round(rel_z, 4)],
        "world_position": [center_x, center_z_elevation, center_y],
        "bounds": [
            world_bounds.get("min_x", 0),
            world_bounds.get("max_x", 0),
            world_bounds.get("min_y", 0),
            world_bounds.get("max_y", 0)
        ],
        "updated_at": src_model.stat().st_mtime
    }
    manifest.append(entry)
    save_custom_manifest(manifest)

    print(f"\n[+] Successfully updated '{building_name}' in Godot world!")
    print(f"    - Source: {src_model.relative_to(PROJECT_ROOT)} ({model_type})")
    print(f"    - Godot Asset: res://custom_buildings/{dest_filename}")
    print(f"    - Chunk: ({chunk_x}, {chunk_y}) | Chunk Local Pos: ({rel_x:.1f}, {rel_y:.1f}, {rel_z:.1f})")
    print(f"    - World Coordinates: ({center_x:.1f}, {center_y:.1f}) [UO Z: {world_bounds.get('base_z', 0)}]")
    return True

def sync_all_refined():
    print("[*] Scanning all community packages for 'model_refined.glb'...")
    refined_models = list(COMMUNITY_ROOT.glob("**/model_refined.glb"))
    if not refined_models:
        print("[!] No 'model_refined.glb' found yet in community_assets.")
        print("    Tip: After refining a building in Blender, save it as 'model_refined.glb' in its folder.")
        return

    print(f"[*] Found {len(refined_models)} refined buildings. Syncing to Godot...")
    for model_path in refined_models:
        update_building(model_path.parent)

    print(f"\n[+] All {len(refined_models)} refined buildings synced to Godot!")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python update_world_building.py <path_or_building_name>")
        print("  python update_world_building.py --all")
        sys.exit(1)

    arg = sys.argv[1]
    if arg == "--all":
        sync_all_refined()
    else:
        bdir = find_building_dir(arg)
        if bdir:
            update_building(bdir)

if __name__ == "__main__":
    main()
