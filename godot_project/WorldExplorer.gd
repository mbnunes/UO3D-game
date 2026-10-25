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

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed:
		if maps_info.has(event.keycode):
			var m = maps_info[event.keycode]
			change_map(m["id"], m["name"], m["pos"], m["loc"])
			return
		if waypoints.has(event.keycode):
			var wp = waypoints[event.keycode]
			teleport_to(wp["pos"], wp["name"])

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
