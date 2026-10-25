class_name WorldSelector
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
