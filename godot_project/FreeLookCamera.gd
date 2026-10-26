class_name FreeLookCamera
extends Camera3D

## Simple free-fly spectator camera for inspecting 3D terrain
@export var move_speed: float = 40.0
@export var sprint_multiplier: float = 3.0
@export var mouse_sensitivity: float = 0.003
@export var is_active: bool = true

var _yaw: float = 0.0
var _pitch: float = -0.5

func _ready() -> void:
	rotation.y = _yaw
	rotation.x = _pitch

func set_active(active: bool) -> void:
	is_active = active
	set_process(active)
	set_process_input(active)
	if not active and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

func set_rotation_ypr(y_rad: float, p_rad: float) -> void:
	_yaw = y_rad
	_pitch = clamp(p_rad, -1.5, 1.5)
	rotation.y = _yaw
	rotation.x = _pitch

func _input(event: InputEvent) -> void:
	if not is_active:
		return

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT:
		if event.pressed:
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
		else:
			Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		_yaw -= event.relative.x * mouse_sensitivity
		_pitch -= event.relative.y * mouse_sensitivity
		_pitch = clamp(_pitch, -1.5, 1.5)
		rotation.y = _yaw
		rotation.x = _pitch

func _process(delta: float) -> void:
	if not is_active:
		return
	var move_vec := Vector3.ZERO
	if Input.is_key_pressed(KEY_W): move_vec -= transform.basis.z
	if Input.is_key_pressed(KEY_S): move_vec += transform.basis.z
	if Input.is_key_pressed(KEY_A): move_vec -= transform.basis.x
	if Input.is_key_pressed(KEY_D): move_vec += transform.basis.x
	if Input.is_key_pressed(KEY_E) or Input.is_key_pressed(KEY_SPACE): move_vec += Vector3.UP
	if Input.is_key_pressed(KEY_Q) or Input.is_key_pressed(KEY_CTRL): move_vec -= Vector3.UP

	if move_vec.length_squared() > 0:
		var speed := move_speed
		if Input.is_key_pressed(KEY_SHIFT):
			speed *= sprint_multiplier
		global_position += move_vec.normalized() * speed * delta
