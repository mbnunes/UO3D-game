class_name FirstPersonPlayer
extends CharacterBody3D

## FirstPersonPlayer.gd - 3D First-Person controller for UO3D
##
## Supports WASD walking, Shift sprinting, Space jumping, and smooth mouse-look.
## Collides with terrain and building architecture via CharacterBody3D physics.

@export var walk_speed: float = 6.0
@export var sprint_speed: float = 12.0
@export var jump_velocity: float = 6.5
@export var gravity: float = 18.0
@export var mouse_sensitivity: float = 0.0025

@onready var head: Node3D = $Head
@onready var camera: Camera3D = $Head/Camera3D

var _pitch: float = 0.0
var is_active: bool = false

func _ready() -> void:
	motion_mode = MOTION_MODE_GROUNDED
	up_direction = Vector3.UP
	floor_constant_speed = true
	floor_snap_length = 0.25
	floor_max_angle = deg_to_rad(50.0)
	floor_stop_on_slope = true
	floor_block_on_wall = false
	wall_min_slide_angle = 0.0
	set_active(false)

func set_active(active: bool) -> void:
	is_active = active
	visible = active
	set_physics_process(active)
	set_process_input(active)
	if camera:
		camera.current = active
	if active:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	else:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

func set_pitch(p: float) -> void:
	_pitch = clamp(p, -deg_to_rad(88.0), deg_to_rad(88.0))
	if head:
		head.rotation.x = _pitch

func _input(event: InputEvent) -> void:
	if not is_active:
		return

	# Re-capture mouse on click if freed
	if event is InputEventMouseButton and event.pressed:
		if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
			get_viewport().set_input_as_handled()

	# ESC frees the mouse cursor
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

	# Mouse look
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * mouse_sensitivity)
		_pitch = clamp(_pitch - event.relative.y * mouse_sensitivity, -deg_to_rad(88.0), deg_to_rad(88.0))
		if head:
			head.rotation.x = _pitch

func _physics_process(delta: float) -> void:
	if not is_active:
		return

	# 1. Apply gravity / floor adherence
	# Keeping a slight downward velocity when grounded keeps floor snap engaged across trimesh seams
	if not is_on_floor():
		velocity.y -= gravity * delta
	else:
		velocity.y = -1.0

	# 2. Handle Jump with Space
	if Input.is_key_pressed(KEY_SPACE) and is_on_floor():
		velocity.y = jump_velocity

	# 3. WASD Movement in local character direction
	var input_dir := Vector2.ZERO
	if Input.is_key_pressed(KEY_W): input_dir.y -= 1.0
	if Input.is_key_pressed(KEY_S): input_dir.y += 1.0
	if Input.is_key_pressed(KEY_A): input_dir.x -= 1.0
	if Input.is_key_pressed(KEY_D): input_dir.x += 1.0
	input_dir = input_dir.normalized()

	var speed := sprint_speed if Input.is_key_pressed(KEY_SHIFT) else walk_speed
	var move_dir := (transform.basis * Vector3(input_dir.x, 0, input_dir.y)).normalized()

	if move_dir.length_squared() > 0:
		velocity.x = lerp(velocity.x, move_dir.x * speed, 14.0 * delta)
		velocity.z = lerp(velocity.z, move_dir.z * speed, 14.0 * delta)
	else:
		velocity.x = lerp(velocity.x, 0.0, 16.0 * delta)
		velocity.z = lerp(velocity.z, 0.0, 16.0 * delta)

	move_and_slide()

	# Failsafe: if player somehow drops out of bounds, rescue to sea level
	if global_position.y < -40.0:
		velocity = Vector3.ZERO
		global_position.y = 5.0
