class_name SceneController
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
