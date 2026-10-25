class_name WorldExplorer
extends Node3D

## WorldExplorer.gd - Teleport & Seamless Continuous World Navigation
##
## Allows continuous movement across the entire continent with instant hotkey teleports (1..9)
## to any major city to test seamless terrain streaming.

@export var player_camera: Camera3D
@export var terrain_loader: TerrainLoader

var maps_info = {
	KEY_F1: {"id": 0, "name": "Felucca (Map 0)",  "pos": Vector3(1440, 35, 1690), "loc": "Britain (West Bank)"},
	KEY_F2: {"id": 1, "name": "Trammel (Map 1)",  "pos": Vector3(1440, 35, 1690), "loc": "Britain (West Bank)"},
	KEY_F3: {"id": 2, "name": "Ilshenar (Map 2)", "pos": Vector3(850, 30, 800),   "loc": "Pass of Karnaugh"},
	KEY_F4: {"id": 3, "name": "Malas (Map 3)",    "pos": Vector3(1000, 30, 520),  "loc": "Luna (Capital)"},
	KEY_F5: {"id": 4, "name": "Tokuno (Map 4)",   "pos": Vector3(740, 35, 1260),  "loc": "Zento (Capital)"},
	KEY_F6: {"id": 5, "name": "Ter Mur (Map 5)",  "pos": Vector3(850, 35, 3450),  "loc": "Royal City"},
}

var current_map_id: int = 0

var waypoints = {
	KEY_0: {"name": "Castelo British (Entrada)", "pos": Vector3(1360, 24, 1680)},
	KEY_C: {"name": "Castelo British (Sala do Trono)", "pos": Vector3(1323, 14, 1624)},
	KEY_1: {"name": "Britain (West Bank)", "pos": Vector3(1440, 35, 1690)},
	KEY_B: {"name": "Britain (Ponte & Ferreiro)", "pos": Vector3(1460, 30, 1630)},
	KEY_P: {"name": "Britain (Porto & Docas)", "pos": Vector3(1480, 25, 1750)},
	KEY_2: {"name": "Cove (Vila & Montanhas)", "pos": Vector3(2260, 35, 1200)},
	KEY_3: {"name": "Minoc & Covetous", "pos": Vector3(2520, 35, 540)},
	KEY_4: {"name": "Yew & Floresta", "pos": Vector3(620, 35, 1020)},
	KEY_5: {"name": "Trinsic (Sul)", "pos": Vector3(1950, 35, 2800)},
	KEY_6: {"name": "Moonglow (Ilha)", "pos": Vector3(4440, 40, 1150)},
	KEY_7: {"name": "Buc's Den", "pos": Vector3(2700, 30, 2180)},
	KEY_8: {"name": "Magincia", "pos": Vector3(3700, 35, 2150)},
	KEY_9: {"name": "Jhelom (Ilhas)", "pos": Vector3(1400, 35, 3850)},
}

func _ready() -> void:
	if not player_camera:
		player_camera = get_node_or_null("FreeLookCamera")
	if not terrain_loader:
		terrain_loader = get_node_or_null("TerrainLoader")

	var vbox = get_node_or_null("HUD/Panel/VBox")
	if vbox:
		# Map Selector Status Label
		var map_lbl = Label.new()
		map_lbl.name = "CurrentMap"
		map_lbl.add_theme_color_override("font_color", Color(0.3, 1.0, 0.6, 1.0))
		map_lbl.add_theme_font_size_override("font_size", 14)
		map_lbl.text = "Mapa Ativo: Felucca (Map 0) [F1..F6 para trocar]"
		vbox.add_child(map_lbl)

		# Buttons row for mouse clickers
		var btn_row = HBoxContainer.new()
		btn_row.name = "MapButtons"
		for k in [KEY_F1, KEY_F2, KEY_F3, KEY_F4, KEY_F5, KEY_F6]:
			var info = maps_info[k]
			var btn = Button.new()
			btn.text = "M%d: %s" % [info["id"], info["name"].split(" ")[0]]
			btn.tooltip_text = "Alternar para %s (%s)" % [info["name"], info["loc"]]
			btn.pressed.connect(func(mid=info["id"], mname=info["name"], mpos=info["pos"], mloc=info["loc"]):
				change_map(mid, mname, mpos, mloc)
			)
			btn_row.add_child(btn)
		vbox.add_child(btn_row)

		# Realtime inspect label
		var insp = Label.new()
		insp.name = "InspectInfo"
		insp.add_theme_color_override("font_color", Color(0.4, 0.95, 1.0, 1.0))
		insp.add_theme_font_size_override("font_size", 14)
		insp.text = "Mirando: [Mire em qualquer construção ou terreno]"
		vbox.add_child(insp)

		# Graphics FX Status Label
		var fx_lbl = Label.new()
		fx_lbl.name = "FXStatus"
		fx_lbl.add_theme_color_override("font_color", Color(0.9, 0.85, 0.4, 1.0))
		fx_lbl.add_theme_font_size_override("font_size", 13)
		fx_lbl.text = "Visual: [H: Efeitos HD] | [T: Terreno PBR] | [O: Oceano 3D] | [G: Grama 3D]"
		vbox.add_child(fx_lbl)

		# Buttons row for visual toggles
		var fx_btn_row = HBoxContainer.new()
		fx_btn_row.name = "FXButtons"

		var btn_hd = Button.new()
		btn_hd.text = "HD (H)"
		btn_hd.tooltip_text = "Alternar SSAO, SSIL, SDFGI e Fog"
		btn_hd.pressed.connect(func(): toggle_hd_effects())
		fx_btn_row.add_child(btn_hd)

		var btn_pbr = Button.new()
		btn_pbr.text = "PBR (T)"
		btn_pbr.tooltip_text = "Alternar Terreno PBR vs Atlas Clássico"
		btn_pbr.pressed.connect(func(): toggle_terrain_shader())
		fx_btn_row.add_child(btn_pbr)

		var btn_water = Button.new()
		btn_water.text = "Oceano (O)"
		btn_water.tooltip_text = "Alternar Oceano e Rios 3D"
		btn_water.pressed.connect(func(): toggle_water())
		fx_btn_row.add_child(btn_water)

		var btn_grass = Button.new()
		btn_grass.text = "Grama (G)"
		btn_grass.tooltip_text = "Alternar Grama Procedural Dinâmica"
		btn_grass.pressed.connect(func(): toggle_grass())
		fx_btn_row.add_child(btn_grass)

		vbox.add_child(fx_btn_row)

	# Setup crosshair in the center of the screen
	var hud = get_node_or_null("HUD")
	if hud:
		var ch = Label.new()
		ch.name = "Crosshair"
		ch.text = "+"
		ch.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		ch.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		ch.set_anchors_preset(Control.PRESET_CENTER)
		ch.grow_horizontal = Control.GROW_DIRECTION_BOTH
		ch.grow_vertical = Control.GROW_DIRECTION_BOTH
		ch.add_theme_color_override("font_color", Color(1.0, 1.0, 1.0, 0.7))
		ch.add_theme_font_size_override("font_size", 20)
		hud.add_child(ch)

var _hd_fx_enabled: bool = true
var _water_enabled: bool = true

func _process(_delta: float) -> void:
	if player_camera:
		var ocean: Node3D = get_node_or_null("OceanWater")
		if ocean:
			# Snap to 2-meter increments to keep vertex grid stable while following camera
			ocean.global_position.x = floor(player_camera.global_position.x / 2.0) * 2.0
			ocean.global_position.z = floor(player_camera.global_position.z / 2.0) * 2.0

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_H or event.keycode == KEY_F11:
			toggle_hd_effects()
			return
		if event.keycode == KEY_T:
			toggle_terrain_shader()
			return
		if event.keycode == KEY_O:
			toggle_water()
			return
		if event.keycode == KEY_G:
			toggle_grass()
			return
		if maps_info.has(event.keycode):
			var m = maps_info[event.keycode]
			change_map(m["id"], m["name"], m["pos"], m["loc"])
			return
		if waypoints.has(event.keycode):
			var wp = waypoints[event.keycode]
			teleport_to(wp["pos"], wp["name"])

func toggle_hd_effects() -> void:
	var we: WorldEnvironment = get_node_or_null("WorldEnvironment")
	if not we or not we.environment:
		return
	_hd_fx_enabled = not _hd_fx_enabled
	we.environment.ssao_enabled = _hd_fx_enabled
	we.environment.ssil_enabled = _hd_fx_enabled
	we.environment.sdfgi_enabled = _hd_fx_enabled
	we.environment.volumetric_fog_enabled = _hd_fx_enabled
	var lbl: Label = get_node_or_null("HUD/Panel/VBox/FXStatus")
	if lbl:
		if _hd_fx_enabled:
			lbl.text = "Graficos HD: SSAO, SSIL, SDFGI, Fog ATIVOS [H: Desativar]"
			lbl.add_theme_color_override("font_color", Color(0.3, 1.0, 0.6, 1.0))
		else:
			lbl.text = "Graficos HD: DESATIVADOS (Modo Leve / 1997) [H: Ativar]"
			lbl.add_theme_color_override("font_color", Color(1.0, 0.4, 0.4, 1.0))
	print("[WorldExplorer] Graficos HD alternados: ", _hd_fx_enabled)

func toggle_terrain_shader() -> void:
	if not terrain_loader:
		return
	terrain_loader.use_baked_textures = not terrain_loader.use_baked_textures
	if not terrain_loader.use_baked_textures and not terrain_loader.custom_material:
		var sm := ShaderMaterial.new()
		sm.shader = load("res://terrain_shader.gdshader")
		terrain_loader.custom_material = sm
	terrain_loader.reload_all_chunks()
	print("[WorldExplorer] Material de terreno alternado: use_baked_textures = ", terrain_loader.use_baked_textures)

func toggle_water() -> void:
	var ocean: Node3D = get_node_or_null("OceanWater")
	if not ocean:
		return
	_water_enabled = not _water_enabled
	ocean.visible = _water_enabled
	print("[WorldExplorer] Oceano 3D alternado: ", _water_enabled)

func toggle_grass() -> void:
	var gm: Node3D = get_node_or_null("GrassManager")
	if not gm:
		return
	gm.visible = not gm.visible
	if "enabled" in gm:
		gm.enabled = gm.visible
	print("[WorldExplorer] Grama procedural alternada: ", gm.visible)

func change_map(map_id: int, map_name: String, spawn_pos: Vector3, spawn_name: String) -> void:
	current_map_id = map_id
	if terrain_loader:
		terrain_loader.switch_map(map_id)
	teleport_to(spawn_pos, map_name + " - " + spawn_name)
	var map_lbl: Label = get_node_or_null("HUD/Panel/VBox/CurrentMap")
	if map_lbl:
		map_lbl.text = "Mapa Ativo: " + map_name + " [F1..F6 para trocar]"
	print("[WorldExplorer] Alternado para o mapa: ", map_name)

func teleport_to(target_pos: Vector3, location_name: String) -> void:
	if player_camera:
		player_camera.global_position = target_pos
		var lbl: Label = get_node_or_null("HUD/Panel/VBox/Location")
		if lbl:
			lbl.text = "Localização: " + location_name + " " + str(target_pos)
		print("[WorldExplorer] Teleportado para: ", location_name, " em ", target_pos)
