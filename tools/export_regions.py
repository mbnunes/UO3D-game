#!/usr/bin/env python3
"""
export_regions.py - Generates dedicated Godot 4 scenes and chunk sets for UO regions:
  1. Britain e arredores
  2. Trinsic
  3. Yew e Floresta
  4. Minoc / Covetous
  5. Moonglow (Ilha)
  6. Buc's Den
  7. Magincia
  8. Jhelom (Ilhas)

Also creates a WorldSelector (Menu Hub) scene to easily switch between regions.
"""

import os
import sys
from pathlib import Path
from uo_terrain_to_godot import generate_terrain


REGIONS = [
    {
        "id": "britain",
        "name": "Britain e Arredores",
        "bounds_x": (1300, 1650),
        "bounds_y": (1500, 1850),
        "cam_pos": (1440, 35, 1690),
        "desc": "Capital de Britannia, Castelo de Lord British e rio"
    },
    {
        "id": "trinsic",
        "name": "Trinsic (Cidade dos Paladinos)",
        "bounds_x": (1750, 2150),
        "bounds_y": (2600, 2950),
        "cam_pos": (1950, 35, 2800),
        "desc": "Cidade murada ao sul, muralhas e docas"
    },
    {
        "id": "yew",
        "name": "Yew e Floresta",
        "bounds_x": (450, 850),
        "bounds_y": (850, 1250),
        "cam_pos": (620, 35, 1020),
        "desc": "Cidade da floresta profunda, corte de justiça e abadia"
    },
    {
        "id": "minoc",
        "name": "Minoc e Covetous",
        "bounds_x": (2350, 2750),
        "bounds_y": (350, 700),
        "cam_pos": (2520, 35, 540),
        "desc": "Cidade dos mineradores, pontes sobre o rio e entrada da montanha"
    },
    {
        "id": "moonglow",
        "name": "Moonglow (Ilha dos Magos)",
        "bounds_x": (4300, 4650),
        "bounds_y": (900, 1450),
        "cam_pos": (4440, 40, 1150),
        "desc": "Ilha mágica a leste com telescópio e líceum"
    },
    {
        "id": "bucs_den",
        "name": "Buccaneer's Den",
        "bounds_x": (2600, 2850),
        "bounds_y": (2050, 2300),
        "cam_pos": (2700, 30, 2180),
        "desc": "Ilha dos piratas e foras da lei"
    },
    {
        "id": "magincia",
        "name": "Magincia (Ilha)",
        "bounds_x": (3550, 3850),
        "bounds_y": (2000, 2300),
        "cam_pos": (3700, 35, 2150),
        "desc": "Ilha da humildade e praias"
    },
    {
        "id": "jhelom",
        "name": "Jhelom (Ilhas dos Guerreiros)",
        "bounds_x": (1300, 1550),
        "bounds_y": (3700, 4050),
        "cam_pos": (1400, 35, 3850),
        "desc": "Arquipélago do sul com arena de duelo e fazendas"
    }
]


def create_region_scene(region: dict, scenes_dir: Path):
    reg_id = region["id"]
    reg_name = region["name"]
    cx, cy, cz = region["cam_pos"]

    scene_content = f"""[gd_scene load_steps=8 format=3 uid="uid://uo_scene_{reg_id}"]

[ext_resource type="Script" path="res://TerrainLoader.gd" id="1_terrain"]
[ext_resource type="Script" path="res://FreeLookCamera.gd" id="2_camera"]
[ext_resource type="Shader" path="res://terrain_shader.gdshader" id="3_shader"]
[ext_resource type="Script" path="res://SceneController.gd" id="4_controller"]

[sub_resource type="ProceduralSkyMaterial" id="ProceduralSkyMaterial_1"]
sky_top_color = Color(0.384, 0.545, 0.768, 1)
sky_horizon_color = Color(0.647, 0.725, 0.819, 1)
ground_bottom_color = Color(0.2, 0.169, 0.133, 1)
ground_horizon_color = Color(0.647, 0.725, 0.819, 1)

[sub_resource type="Sky" id="Sky_1"]
sky_material = SubResource("ProceduralSkyMaterial_1")

[sub_resource type="Environment" id="Environment_1"]
background_mode = 2
sky = SubResource("Sky_1")
ambient_light_source = 3
ambient_light_color = Color(0.65, 0.7, 0.75, 1)
tonemap_mode = 2
glow_enabled = true

[sub_resource type="ShaderMaterial" id="ShaderMaterial_1"]
render_priority = 0
shader = ExtResource("3_shader")
shader_parameter/roughness = 0.85
shader_parameter/specular = 0.2
shader_parameter/show_wireframe_grid = false
shader_parameter/grid_line_thickness = 0.05
shader_parameter/show_elevation_contours = false
shader_parameter/contour_interval = 2.0
shader_parameter/water_color = Color(0.12, 0.35, 0.75, 1)
shader_parameter/grass_color = Color(0.22, 0.52, 0.18, 1)
shader_parameter/dirt_color = Color(0.58, 0.44, 0.28, 1)
shader_parameter/sand_color = Color(0.82, 0.76, 0.52, 1)
shader_parameter/rock_color = Color(0.48, 0.48, 0.48, 1)
shader_parameter/snow_color = Color(0.92, 0.94, 0.96, 1)
shader_parameter/lava_color = Color(0.95, 0.25, 0.05, 1)

[node name="{reg_id.capitalize()}" type="Node3D"]
script = ExtResource("4_controller")
region_title = "{reg_name}"

[node name="WorldEnvironment" type="WorldEnvironment" parent="."]
environment = SubResource("Environment_1")

[node name="DirectionalLight3D" type="DirectionalLight3D" parent="."]
transform = Transform3D(0.866025, -0.353553, 0.353553, 0, 0.707107, 0.707107, -0.5, -0.612372, 0.612372, 0, 100, 0)
shadow_enabled = true

[node name="FreeLookCamera" type="Camera3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 0.906308, 0.422618, 0, -0.422618, 0.906308, {cx}, {cy}, {cz})
script = ExtResource("2_camera")
move_speed = 50.0

[node name="TerrainLoader" type="Node3D" parent="." node_paths=PackedStringArray("target_camera")]
script = ExtResource("1_terrain")
chunks_directory = "res://terrain_chunks/{reg_id}/"
chunk_format = "glb"
view_distance = 600.0
target_camera = NodePath("../FreeLookCamera")
custom_material = SubResource("ShaderMaterial_1")

[node name="HUD" type="CanvasLayer" parent="."]

[node name="Panel" type="PanelContainer" parent="HUD"]
anchors_preset = 0
offset_left = 20.0
offset_top = 20.0
offset_right = 360.0
offset_bottom = 120.0

[node name="VBox" type="VBoxContainer" parent="HUD/Panel"]
layout_mode = 2

[node name="Title" type="Label" parent="HUD/Panel/VBox"]
layout_mode = 2
theme_override_font_sizes/font_size = 18
text = "UO 3D - {reg_name}"

[node name="Help" type="Label" parent="HUD/Panel/VBox"]
layout_mode = 2
theme_override_colors/font_color = Color(0.8, 0.8, 0.8, 1)
theme_override_font_sizes/font_size = 13
text = "WASD + Mouse Dir.: Voar | Shift: Acelerar
Pressione 'M' ou ESC para Voltar ao Menu"

[node name="BtnMenu" type="Button" parent="HUD/Panel/VBox"]
layout_mode = 2
text = "Voltar ao Menu de Regiões"
"""
    dest_file = scenes_dir / f"{reg_id.capitalize()}.tscn"
    with open(dest_file, "w", encoding="utf-8") as f:
        f.write(scene_content)
    print(f"[+] Cena gerada: {dest_file}")


def create_scene_controller(project_dir: Path):
    script_content = """class_name SceneController
extends Node3D

@export var region_title: String = "Região"

func _ready() -> void:
	var btn: Button = get_node_or_null("HUD/Panel/VBox/BtnMenu")
	if btn:
		btn.pressed.connect(_on_btn_menu_pressed)

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_M or event.keycode == KEY_ESCAPE:
			_on_btn_menu_pressed()

func _on_btn_menu_pressed() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	get_tree().change_scene_to_file("res://scenes/WorldSelector.tscn")
"""
    with open(project_dir / "SceneController.gd", "w", encoding="utf-8") as f:
        f.write(script_content)


def create_world_selector_scene(project_dir: Path, scenes_dir: Path):
    buttons_markup = ""
    for idx, reg in enumerate(REGIONS, 1):
        reg_id = reg["id"]
        reg_name = reg["name"]
        reg_desc = reg["desc"]
        buttons_markup += f"""
[node name="Btn_{reg_id}" type="Button" parent="Center/Panel/Margin/VBox/Scroll/Grid"]
layout_mode = 2
size_flags_horizontal = 3
custom_minimum_size = Vector2(300, 70)
theme_override_font_sizes/font_size = 15
text = "{idx}. {reg_name}
({reg_desc})"
"""

    selector_scene = f"""[gd_scene load_steps=2 format=3 uid="uid://uo_world_selector"]

[ext_resource type="Script" path="res://WorldSelector.gd" id="1_selector"]

[node name="WorldSelector" type="Control"]
layout_mode = 3
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
grow_horizontal = 2
grow_vertical = 2
script = ExtResource("1_selector")

[node name="Background" type="ColorRect" parent="."]
layout_mode = 1
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
grow_horizontal = 2
grow_vertical = 2
color = Color(0.1, 0.12, 0.16, 1)

[node name="Center" type="CenterContainer" parent="."]
layout_mode = 1
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
grow_horizontal = 2
grow_vertical = 2

[node name="Panel" type="PanelContainer" parent="Center"]
custom_minimum_size = Vector2(750, 520)
layout_mode = 2

[node name="Margin" type="MarginContainer" parent="Center/Panel"]
layout_mode = 2
theme_override_constants/margin_left = 30
theme_override_constants/margin_top = 25
theme_override_constants/margin_right = 30
theme_override_constants/margin_bottom = 25

[node name="VBox" type="VBoxContainer" parent="Center/Panel/Margin"]
layout_mode = 2
theme_override_constants/separation = 15

[node name="Header" type="Label" parent="Center/Panel/Margin/VBox"]
layout_mode = 2
theme_override_font_sizes/font_size = 26
text = "Ultima Online 3D - Seletor de Cidades"
horizontal_alignment = 1

[node name="SubHeader" type="Label" parent="Center/Panel/Margin/VBox"]
layout_mode = 2
theme_override_colors/font_color = Color(0.7, 0.75, 0.8, 1)
theme_override_font_sizes/font_size = 14
text = "Escolha um local para carregar o terreno 3D otimizado (ou pressione as teclas 1 a 8):"
horizontal_alignment = 1

[node name="HSeparator" type="HSeparator" parent="Center/Panel/Margin/VBox"]
layout_mode = 2

[node name="Scroll" type="ScrollContainer" parent="Center/Panel/Margin/VBox"]
layout_mode = 2
size_flags_vertical = 3

[node name="Grid" type="GridContainer" parent="Center/Panel/Margin/VBox/Scroll"]
layout_mode = 2
size_flags_horizontal = 3
size_flags_vertical = 3
theme_override_constants/h_separation = 15
theme_override_constants/v_separation = 12
columns = 2
{buttons_markup}
"""
    with open(scenes_dir / "WorldSelector.tscn", "w", encoding="utf-8") as f:
        f.write(selector_scene)

    selector_script = """class_name WorldSelector
extends Control

var regions = [
	{"key": KEY_1, "file": "res://scenes/Britain.tscn"},
	{"key": KEY_2, "file": "res://scenes/Trinsic.tscn"},
	{"key": KEY_3, "file": "res://scenes/Yew.tscn"},
	{"key": KEY_4, "file": "res://scenes/Minoc.tscn"},
	{"key": KEY_5, "file": "res://scenes/Moonglow.tscn"},
	{"key": KEY_6, "file": "res://scenes/Bucs_den.tscn"},
	{"key": KEY_7, "file": "res://scenes/Magincia.tscn"},
	{"key": KEY_8, "file": "res://scenes/Jhelom.tscn"}
]

func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	var grid = get_node("Center/Panel/Margin/VBox/Scroll/Grid")
	var btn_idx = 0
	for child in grid.get_children():
		if child is Button and btn_idx < regions.size():
			var target_scene: String = regions[btn_idx]["file"]
			child.pressed.connect(func(): get_tree().change_scene_to_file(target_scene))
			btn_idx += 1

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed:
		for r in regions:
			if event.keycode == r["key"]:
				get_tree().change_scene_to_file(r["file"])
				return
"""
    with open(project_dir / "WorldSelector.gd", "w", encoding="utf-8") as f:
        f.write(selector_script)


def main():
    map_file = "/opt/hd_jogos/UOC/map0.mul"
    project_dir = Path("/home/mnunes/uo3d_map/godot_project")
    chunks_root = project_dir / "terrain_chunks"
    scenes_dir = project_dir / "scenes"

    scenes_dir.mkdir(parents=True, exist_ok=True)
    chunks_root.mkdir(parents=True, exist_ok=True)

    create_scene_controller(project_dir)
    create_world_selector_scene(project_dir, scenes_dir)

    print("==========================================================")
    print("Gerando Chunks 3D e Cenas Dedicadas para as Regiões do UO")
    print("==========================================================")

    total_regions = len(REGIONS)
    for i, reg in enumerate(REGIONS, 1):
        reg_id = reg["id"]
        reg_name = reg["name"]
        bx = reg["bounds_x"]
        by = reg["bounds_y"]
        reg_chunk_dir = chunks_root / reg_id
        reg_chunk_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n[{i}/{total_regions}] Exportando {reg_name} (X:{bx[0]}..{bx[1]}, Y:{by[0]}..{by[1]})...")

        generate_terrain(
            input_file=map_file,
            output_dir=str(reg_chunk_dir),
            tiledata_path="/opt/hd_jogos/UOC/tiledata.mul",
            texidx_path="/opt/hd_jogos/UOC/texidx.mul",
            texmaps_path="/opt/hd_jogos/UOC/texmaps.mul",
            texture_mode="baked",
            tile_resolution=32,
            chunk_blocks=8,
            v_scale=0.125,
            h_scale=1.0,
            bounds_x=bx,
            bounds_y=by,
            out_format="glb",
            workers=16
        )

        create_region_scene(reg, scenes_dir)

    # Atualizar project.godot para abrir o WorldSelector como main_scene
    proj_godot = project_dir / "project.godot"
    content = proj_godot.read_text(encoding="utf-8")
    content = content.replace('run/main_scene="res://Main.tscn"', 'run/main_scene="res://scenes/WorldSelector.tscn"')
    proj_godot.write_text(content, encoding="utf-8")
    print("\n[+] project.godot atualizado: cena inicial definida para res://scenes/WorldSelector.tscn")

    print("\n==========================================================")
    print("Concluído com Sucesso! Todas as 8 regiões e o Seletor foram criados.")
    print("==========================================================")


if __name__ == "__main__":
    main()
