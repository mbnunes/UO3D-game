shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled, diffuse_burley, specular_schlick_ggx;

// =============================================================================
// procedural_grass_shader.gdshader - Dynamic Swaying Grass Blades
//
// Etapa 4: Procedural Grass Blades with Wind Displacement & Distance Fade
//
// Features:
//   - Ground-anchored wind sway (base stays rooted at Y=0, tips sway vigorously).
//   - Color gradient from rich earth green at root to warm sunlight yellow at tip.
//   - Distance dither fade to seamlessly blend grass LOD into the terrain.
//   - Responds to Godot 4 directional lighting, SSAO, and subsurface scattering.
// =============================================================================

group_uniforms GrassColors;
uniform vec3 base_color : source_color = vec3(0.12, 0.32, 0.08);
uniform vec3 tip_color : source_color = vec3(0.38, 0.65, 0.18);
uniform vec3 dry_color : source_color = vec3(0.55, 0.62, 0.25);
uniform float roughness : hint_range(0.0, 1.0) = 0.6;
uniform float specular : hint_range(0.0, 1.0) = 0.25;

group_uniforms WindSettings;
uniform vec3 wind_direction = vec3(1.0, 0.0, 0.4);
uniform float wind_speed : hint_range(0.1, 5.0) = 2.2;
uniform float wind_strength : hint_range(0.0, 1.0) = 0.28;
uniform float gust_frequency : hint_range(0.05, 1.0) = 0.2;

group_uniforms FadeSettings;
uniform float fade_start : hint_range(10.0, 150.0) = 55.0;
uniform float fade_end : hint_range(20.0, 200.0) = 85.0;

varying vec3 v_world_pos;
varying float v_height_factor;
varying float v_cam_dist;

void vertex() {
    v_world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    v_height_factor = clamp(UV.y, 0.0, 1.0); // 0 = base, 1 = tip of blade

    vec3 wind_dir = normalize(wind_direction);
    float t = TIME * wind_speed;

    // Wind gust across world position
    float gust = sin(dot(v_world_pos.xz, wind_dir.xz) * gust_frequency + t);
    float turbulence = cos(v_world_pos.x * 2.0 + t * 1.5 + v_world_pos.z * 1.8);

    // Tip sway
    float displacement_magnitude = (gust * 0.7 + turbulence * 0.3) * wind_strength * v_height_factor;
    vec3 displacement = wind_dir * displacement_magnitude;
    displacement.y -= abs(displacement_magnitude) * 0.3; // bend down when pushed

    VERTEX += displacement;

    // Compute distance to camera for smooth LOD fade
    vec3 cam_pos = (INV_VIEW_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
    v_cam_dist = length(v_world_pos - cam_pos);
}

void fragment() {
    // Screen-space dither distance fade
    if (v_cam_dist > fade_start) {
        float fade_factor = clamp((fade_end - v_cam_dist) / (fade_end - fade_start), 0.0, 1.0);
        // Bayer 4x4 matrix dither
        int x = int(FRAGCOORD.x) % 4;
        int y = int(FRAGCOORD.y) % 4;
        int index = x + y * 4;
        const float bayer[16] = float[16](
            0.0/16.0,  8.0/16.0,  2.0/16.0, 10.0/16.0,
            12.0/16.0, 4.0/16.0, 14.0/16.0,  6.0/16.0,
            3.0/16.0, 11.0/16.0,  1.0/16.0,  9.0/16.0,
            15.0/16.0, 7.0/16.0, 13.0/16.0,  5.0/16.0
        );
        if (fade_factor < bayer[index]) {
            discard;
        }
    }

    // Color gradient from root to tip
    vec3 col = mix(base_color, tip_color, v_height_factor);

    // Subtle natural patch variation using world coordinates
    float patch = fract(sin(dot(floor(v_world_pos.xz * 0.3), vec2(12.9898, 78.233))) * 43758.5453);
    col = mix(col, dry_color, patch * 0.35);

    ALBEDO = col;
    ROUGHNESS = roughness;
    SPECULAR = specular;
    METALLIC = 0.0;
    NORMAL = vec3(0.0, 1.0, 0.0); // upward hemisphere normal for soft lush foliage lighting
    BACKLIGHT = col * 0.35; // subsurface light passing through thin grass blades
}
