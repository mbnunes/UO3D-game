class_name WorldExplorer
extends Node3D

## WorldExplorer.gd - Teleport & Seamless Continuous World Navigation
##
## Allows continuous movement across the entire continent with instant hotkey teleports (1..9)
## to any major city to test seamless terrain streaming.

@export var player_camera: Camera3D
@export var terrain_loader: TerrainLoader
@export var first_person_player: CharacterBody3D

var maps_info = {
	KEY_F1: {"id": 0, "name": "Felucca (Map 0)",  "pos": Vector3(1440, 35, 1690), "loc": "Britain (West Bank)", "has_ocean": true,  "water_y": -0.55},
	KEY_F2: {"id": 1, "name": "Trammel (Map 1)",  "pos": Vector3(1440, 35, 1690), "loc": "Britain (West Bank)", "has_ocean": true,  "water_y": -0.55},
	KEY_F3: {"id": 2, "name": "Ilshenar (Map 2)", "pos": Vector3(850, 30, 800),   "loc": "Pass of Karnaugh",    "has_ocean": false, "water_y": -20.0},
	KEY_F4: {"id": 3, "name": "Malas (Map 3)",    "pos": Vector3(1000, 30, 520),  "loc": "Luna (Capital)",       "has_ocean": false, "water_y": -30.0},
	KEY_F5: {"id": 4, "name": "Tokuno (Map 4)",   "pos": Vector3(740, 35, 1260),  "loc": "Zento (Capital)",      "has_ocean": true,  "water_y": -0.55},
	KEY_F6: {"id": 5, "name": "Ter Mur (Map 5)",  "pos": Vector3(850, 35, 3450),  "loc": "Royal City",           "has_ocean": false, "water_y": -20.0},
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
	if not first_person_player:
		first_person_player = get_node_or_null("FirstPersonPlayer")

	_load_buildings_spatial_index()

	var vbox = get_node_or_null("HUD/Panel/VBox")
	if vbox:
		var help_lbl = vbox.get_node_or_null("Help")
		if help_lbl:
			help_lbl.text = "V: Alternar 1ª Pessoa / Voo Livre | Espaço: Pular | Shift: Correr\nWASD + Botão Dir.: Mover | 1..9: Teleporte | K: Copiar Alvo"

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

		var btn_cam = Button.new()
		btn_cam.name = "BtnCameraMode"
		btn_cam.text = "1ª Pessoa (V)"
		btn_cam.tooltip_text = "Alternar entre Câmera Livre (Voo) e 1ª Pessoa com Física e Pulo (V)"
		btn_cam.pressed.connect(func(): toggle_camera_mode())
		fx_btn_row.add_child(btn_cam)

		vbox.add_child(fx_btn_row)

	# Connect Inspector Copy Button
	var btn_copy = get_node_or_null("HUD/PanelInspector/VBox/BtnCopy")
	if btn_copy:
		btn_copy.pressed.connect(copy_inspect_details)

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
var _buildings_index: Dictionary = {}
var _last_copied_text: String = ""

func _load_buildings_spatial_index() -> void:
	var path := "res://buildings_spatial_index.json"
	if FileAccess.file_exists(path):
		var f := FileAccess.open(path, FileAccess.READ)
		if f:
			var txt := f.get_as_text()
			var json = JSON.new()
			if json.parse(txt) == OK and json.data is Dictionary:
				_buildings_index = json.data
				print("[WorldExplorer] Indice espacial de construcoes carregado com sucesso.")

func _physics_process(_delta: float) -> void:
	_update_raycast_inspection()

func _update_raycast_inspection() -> void:
	if not player_camera:
		return
	var label: RichTextLabel = get_node_or_null("HUD/PanelInspector/VBox/TargetDetails")
	if not label:
		return

	var space_state = player_camera.get_world_3d().direct_space_state
	var cam_pos = player_camera.global_position
	var forward = -player_camera.global_transform.basis.z
	var ray_end = cam_pos + forward * 350.0

	var query = PhysicsRayQueryParameters3D.create(cam_pos, ray_end)
	query.collide_with_areas = false
	query.collide_with_bodies = true
	query.collision_mask = 1
	if first_person_player:
		query.exclude = [first_person_player.get_rid()]
	var res = space_state.intersect_ray(query)

	if not res:
		label.text = "[color=#888888]Mirando no horizonte / nada ao alcance (alcance: 350m)[/color]"
		_last_copied_text = ""
		return

	var hit_pos: Vector3 = res.position
	var dist: float = cam_pos.distance_to(hit_pos)
	var uo_x := int(round(hit_pos.x))
	var uo_y := int(round(hit_pos.z))
	var uo_z := int(round(hit_pos.y / 0.12))
	var cx := int(floor(hit_pos.x / 64.0))
	var cy := int(floor(hit_pos.z / 64.0))
	var sec_x := int(floor(cx / 8.0))
	var sec_y := int(floor(cy / 8.0))

	var bld = _find_building_at_coords(current_map_id, uo_x, uo_y)

	var text := ""
	var copy_summary := ""

	if bld:
		text += "[b][color=#FFD54F]🏛️ CONSTRUÇÃO:[/color][/b] [color=#00E5FF]%s[/color]\n" % bld.get("id", "")
		text += "[b]🏷️ Nome:[/b] %s ([color=#81C784]%s[/color])\n" % [bld.get("name", ""), bld.get("region", "")]
		text += "[b]📍 Coord UO:[/b] [color=#FFF59D]X: %d, Y: %d, Z: %d[/color]\n" % [uo_x, uo_y, uo_z]
		text += "[b]🌐 Coord 3D:[/b] Vector3(%.1f, %.2f, %.1f) [b]Dist:[/b] %.1fm\n" % [hit_pos.x, hit_pos.y, hit_pos.z, dist]
		text += "[b]🗺️ Chunk:[/b] (%d, %d) [Sector (%d, %d)]\n" % [cx, cy, sec_x, sec_y]
		text += "[b]📁 Pasta:[/b] [color=#90CAF9]%s[/color]\n" % bld.get("folder", "")
		text += "[b]⚡ Comando:[/b] [color=#A7FFEB]python3 update_world_building.py --building %s[/color]" % bld.get("id", "")

		copy_summary = "[UO3D Construção]\nID: %s\nNome: %s\nRegião: %s\nMapa: %d\nCoord UO: X: %d, Y: %d, Z: %d\nCoord 3D: Vector3(%.1f, %.2f, %.1f)\nChunk: (%d, %d)\nPasta: %s\nComando: python3 update_world_building.py --building %s" % [
			bld.get("id", ""), bld.get("name", ""), bld.get("region", ""), current_map_id, uo_x, uo_y, uo_z, hit_pos.x, hit_pos.y, hit_pos.z, cx, cy, bld.get("folder", ""), bld.get("id", "")
		]
	else:
		var collider = res.collider
		var col_name: String = str(collider.name) if collider else ""
		var parent_name: String = str(collider.get_parent().name) if (collider and collider.get_parent()) else ""
		text += "[b][color=#81C784]🌱 TERRENO / SOLO NATURAL[/color][/b]\n"
		text += "[b]📍 Coord UO:[/b] [color=#FFF59D]X: %d, Y: %d, Z: %d[/color]\n" % [uo_x, uo_y, uo_z]
		text += "[b]🌐 Coord 3D:[/b] Vector3(%.1f, %.2f, %.1f) [b]Dist:[/b] %.1fm\n" % [hit_pos.x, hit_pos.y, hit_pos.z, dist]
		text += "[b]🗺️ Chunk:[/b] (%d, %d) [Sector (%d, %d)]\n" % [cx, cy, sec_x, sec_y]
		text += "[b]🔍 Objeto:[/b] %s (%s)\n" % [parent_name, col_name]
		text += "[color=#B0BEC5]Mire em uma parede ou telhado para inspecionar construções.[/color]"

		copy_summary = "[UO3D Terreno]\nMapa: %d\nCoord UO: X: %d, Y: %d, Z: %d\nCoord 3D: Vector3(%.1f, %.2f, %.1f)\nChunk: (%d, %d)\nSetor: (%d, %d)" % [
			current_map_id, uo_x, uo_y, uo_z, hit_pos.x, hit_pos.y, hit_pos.z, cx, cy, sec_x, sec_y
		]

	label.text = text
	_last_copied_text = copy_summary

func _find_building_at_coords(map_id: int, uo_x: int, uo_y: int) -> Dictionary:
	var key = str(map_id)
	if not _buildings_index.has(key):
		return {}
	var list: Array = _buildings_index[key]
	for b in list:
		if uo_x >= b["min_x"] and uo_x <= b["max_x"] and uo_y >= b["min_y"] and uo_y <= b["max_y"]:
			return b
	return {}

func copy_inspect_details() -> void:
	if _last_copied_text.is_empty():
		return
	DisplayServer.clipboard_set(_last_copied_text)
	var fb: Label = get_node_or_null("HUD/PanelInspector/VBox/CopyFeedback")
	if fb:
		fb.text = "✓ Dados copiados! Pode colar no chat (Ctrl+V)."
		var tween = create_tween()
		tween.tween_property(fb, "modulate:a", 1.0, 0.1)
		tween.tween_interval(3.0)
		tween.tween_property(fb, "modulate:a", 0.0, 1.0)
	print("[WorldExplorer] Dados do alvo copiados para o clipboard:\n", _last_copied_text)

func _process(_delta: float) -> void:
	if player_camera:
		var ocean: Node3D = get_node_or_null("OceanWater")
		if ocean and ocean.visible:
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
		if event.keycode == KEY_K:
			copy_inspect_details()
			return
		if event.keycode == KEY_V:
			toggle_camera_mode()
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
	var has_ocean: bool = true
	for k in maps_info:
		if maps_info[k]["id"] == current_map_id:
			has_ocean = maps_info[k].get("has_ocean", true)
			break
	ocean.visible = _water_enabled and has_ocean
	print("[WorldExplorer] Oceano 3D alternado: ", ocean.visible)

func toggle_grass() -> void:
	var gm: Node3D = get_node_or_null("GrassManager")
	if not gm:
		return
	gm.visible = not gm.visible
	if "enabled" in gm:
		gm.enabled = gm.visible
	print("[WorldExplorer] Grama procedural alternada: ", gm.visible)

var _is_first_person: bool = false

func toggle_camera_mode() -> void:
	_is_first_person = not _is_first_person
	var free_cam: FreeLookCamera = get_node_or_null("FreeLookCamera")
	if not free_cam or not first_person_player:
		return

	var btn_cam: Button = get_node_or_null("HUD/Panel/VBox/FXButtons/BtnCameraMode")

	if _is_first_person:
		# Switch from FreeLook to First-Person
		var cam_pos = free_cam.global_position
		var cam_yaw = free_cam.rotation.y
		var cam_pitch = free_cam.rotation.x

		# Raycast down to find ground level under camera
		var space_state = get_world_3d().direct_space_state
		var query = PhysicsRayQueryParameters3D.create(cam_pos + Vector3.UP * 1.0, cam_pos + Vector3.DOWN * 200.0)
		query.collision_mask = 1
		var hit = space_state.intersect_ray(query)
		if hit:
			first_person_player.global_position = hit["position"] + Vector3.UP * 0.05
		else:
			first_person_player.global_position = cam_pos

		first_person_player.velocity = Vector3.ZERO
		first_person_player.rotation.y = cam_yaw
		if first_person_player.has_method("set_pitch"):
			first_person_player.set_pitch(cam_pitch)

		free_cam.set_active(false)
		free_cam.current = false

		if first_person_player.has_method("set_active"):
			first_person_player.set_active(true)
		var fp_cam: Camera3D = first_person_player.get_node_or_null("Head/Camera3D")
		if fp_cam:
			player_camera = fp_cam

		if btn_cam:
			btn_cam.text = "Voo Livre (V)"
			btn_cam.tooltip_text = "Alternar de volta para Câmera Livre de Voo (V)"
		print("[WorldExplorer] Modo Primeira Pessoa ATIVO (WASD move, Espaço pula, Shift corre, V volta).")
	else:
		# Switch from First-Person to FreeLook
		var fp_cam: Camera3D = first_person_player.get_node_or_null("Head/Camera3D")
		var head_pos: Vector3 = fp_cam.global_position if fp_cam else first_person_player.global_position + Vector3.UP * 1.65
		var head_rot: Vector3 = fp_cam.global_rotation if fp_cam else first_person_player.global_rotation

		if first_person_player.has_method("set_active"):
			first_person_player.set_active(false)

		free_cam.global_position = head_pos
		free_cam.set_rotation_ypr(head_rot.y, head_rot.x)
		free_cam.set_active(true)
		free_cam.current = true
		player_camera = free_cam

		if btn_cam:
			btn_cam.text = "1ª Pessoa (V)"
			btn_cam.tooltip_text = "Alternar para Modo Primeira Pessoa com Física e Pulo (V)"
		print("[WorldExplorer] Modo Câmera Livre ATIVO.")

	# Update target camera references for streaming and procedural grass
	if terrain_loader:
		terrain_loader.target_camera = player_camera
	var gm: Node3D = get_node_or_null("GrassManager")
	if gm and "target_camera" in gm:
		gm.target_camera = player_camera

func change_map(map_id: int, map_name: String, spawn_pos: Vector3, spawn_name: String) -> void:
	current_map_id = map_id
	if terrain_loader:
		terrain_loader.switch_map(map_id)

	# Configure ocean water according to continental geography
	var ocean: Node3D = get_node_or_null("OceanWater")
	if ocean:
		var has_ocean: bool = true
		var water_y: float = -0.55
		for k in maps_info:
			if maps_info[k]["id"] == map_id:
				has_ocean = maps_info[k].get("has_ocean", true)
				water_y = maps_info[k].get("water_y", -0.55)
				break
		ocean.visible = has_ocean and _water_enabled
		ocean.global_position.y = water_y
		print("[WorldExplorer] Mapa %s: Oceano 3D visivel=%s, nivel Y=%.2f" % [map_name, str(ocean.visible), water_y])

	teleport_to(spawn_pos, map_name + " - " + spawn_name)
	var map_lbl: Label = get_node_or_null("HUD/Panel/VBox/CurrentMap")
	if map_lbl:
		map_lbl.text = "Mapa Ativo: " + map_name + " [F1..F6 para trocar]"
	print("[WorldExplorer] Alternado para o mapa: ", map_name)

func teleport_to(target_pos: Vector3, location_name: String) -> void:
	if _is_first_person and first_person_player:
		var space_state = get_world_3d().direct_space_state
		var query = PhysicsRayQueryParameters3D.create(target_pos + Vector3.UP * 5.0, target_pos + Vector3.DOWN * 200.0)
		query.collision_mask = 1
		var hit = space_state.intersect_ray(query)
		if hit:
			first_person_player.global_position = hit["position"] + Vector3.UP * 0.1
		else:
			first_person_player.global_position = target_pos
		first_person_player.velocity = Vector3.ZERO
	elif player_camera:
		player_camera.global_position = target_pos

	var lbl: Label = get_node_or_null("HUD/Panel/VBox/Location")
	if lbl:
		lbl.text = "Localização: " + location_name + " " + str(target_pos)
	print("[WorldExplorer] Teleportado para: ", location_name, " em ", target_pos)
