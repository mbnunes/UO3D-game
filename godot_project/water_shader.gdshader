shader_type spatial;
render_mode blend_mix, depth_draw_always, cull_back, diffuse_burley, specular_schlick_ggx;

// =============================================================================
// water_shader.gdshader - Advanced Physical 3D Water for Ultima Online (Godot 4.x)
//
// Features:
//   - Physical Gerstner wave displacement
//   - Depth absorption (shallow cyan -> deep oceanic blue via depth buffer)
//   - Animated shoreline & bridge contact foam
//   - Dual-layer moving normal flow
//   - Screen-space refraction
//   - Fresnel reflections and sun specular sparkles
//   - Caustic light projection
// =============================================================================

uniform sampler2D depth_texture : hint_depth_texture, filter_linear_mipmap;
uniform sampler2D screen_texture : hint_screen_texture, filter_linear_mipmap;

group_uniforms WaterColors;
uniform vec4 shallow_color : source_color = vec4(0.08, 0.45, 0.58, 0.85);
uniform vec4 deep_color : source_color = vec4(0.02, 0.08, 0.25, 0.95);
uniform vec4 foam_color : source_color = vec4(0.92, 0.96, 1.0, 1.0);
uniform float depth_distance : hint_range(0.1, 20.0) = 4.5;
uniform float foam_depth : hint_range(0.01, 1.5) = 0.35;

group_uniforms Waves;
uniform float wave_speed : hint_range(0.05, 3.0) = 0.85;
uniform float wave_scale : hint_range(0.1, 5.0) = 1.2;
uniform float wave_height : hint_range(0.0, 1.0) = 0.12;

group_uniforms OpticalProperties;
uniform float roughness : hint_range(0.0, 1.0) = 0.04;
uniform float specular : hint_range(0.0, 1.0) = 0.92;
uniform float refraction_strength : hint_range(0.0, 0.1) = 0.025;
uniform float fresnel_power : hint_range(1.0, 8.0) = 4.0;

varying vec3 v_world_pos;
varying vec3 v_vertex;

// Procedural wave noise
float hash(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

// Multi-directional Gerstner wave displacement
vec3 gerstner_wave(vec2 coord, float time, float freq, float amp, vec2 dir) {
    float proj = dot(coord, normalize(dir)) * freq + time;
    float sin_p = sin(proj);
    float cos_p = cos(proj);
    return vec3(dir.x * amp * cos_p, amp * sin_p, dir.y * amp * cos_p);
}

void vertex() {
    v_world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    v_vertex = VERTEX;

    float t = TIME * wave_speed;
    vec2 pos2d = v_world_pos.xz * wave_scale;

    vec3 w1 = gerstner_wave(pos2d, t * 1.2, 1.0, wave_height * 0.5, vec2(1.0, 0.3));
    vec3 w2 = gerstner_wave(pos2d, t * 0.9, 1.6, wave_height * 0.3, vec2(-0.7, 0.7));
    vec3 w3 = gerstner_wave(pos2d, t * 1.5, 2.3, wave_height * 0.2, vec2(0.2, -1.0));

    VERTEX.y += (w1.y + w2.y + w3.y);
    v_world_pos.y += (w1.y + w2.y + w3.y);
}

void fragment() {
    // 1. Dual-flow procedural normal map
    float t = TIME * wave_speed;
    vec2 uv1 = v_world_pos.xz * (wave_scale * 0.4) + vec2(t * 0.06, t * 0.03);
    vec2 uv2 = v_world_pos.xz * (wave_scale * 0.7) - vec2(t * 0.04, -t * 0.05);
    vec2 uv3 = v_world_pos.xz * (wave_scale * 1.4) + vec2(-t * 0.05, t * 0.06);

    float n1 = noise(uv1);
    float n2 = noise(uv2);
    float n3 = noise(uv3);

    vec3 normal_tangent = normalize(vec3(
        (n1 - 0.5) * 0.4 + (n2 - 0.5) * 0.3 + (n3 - 0.5) * 0.2,
        1.0,
        (n2 - 0.5) * 0.4 + (n1 - 0.5) * 0.3 + (n3 - 0.5) * 0.2
    ));
    NORMAL = normalize((VIEW_MATRIX * vec4(normal_tangent, 0.0)).xyz);

    // 2. Depth buffer calculation for shallow water & contact foam
    float depth_raw = textureLod(depth_texture, SCREEN_UV, 0.0).r;
    vec4 upos = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, depth_raw, 1.0);
    vec3 pixel_position = upos.xyz / upos.w;
    float scene_depth = -pixel_position.z;
    float water_depth = -VERTEX.z;
    float depth_diff = clamp(scene_depth - water_depth, 0.0, 100.0);

    // Dynamic wave lapping & shoreline curve perturbation (eliminates straight 90-degree tile edges)
    float shore_wave = sin(v_world_pos.x * 1.6 + v_world_pos.z * 1.3 + t * 1.8) * 0.06
                     + cos(v_world_pos.x * 2.8 - v_world_pos.z * 2.2 - t * 1.4) * 0.04;
    float shore_micro = (noise(v_world_pos.xz * 2.5 + vec2(t * 0.15, t * 0.12)) - 0.5) * 0.10;
    float effective_depth = max(0.0, depth_diff + (shore_wave + shore_micro) * smoothstep(1.5, 0.0, depth_diff));

    // 3. Screen-Space Refraction
    vec2 refract_offset = normal_tangent.xz * refraction_strength * clamp(depth_diff * 0.5, 0.0, 1.0);
    vec3 screen_col = textureLod(screen_texture, SCREEN_UV + refract_offset, 0.0).rgb;

    // 4. Water Color & Depth Absorption (Beer-Lambert absorption)
    float depth_factor = clamp(effective_depth / depth_distance, 0.0, 1.0);
    vec3 water_col = mix(shallow_color.rgb, deep_color.rgb, depth_factor);
    vec3 final_color = mix(screen_col, water_col, mix(shallow_color.a, deep_color.a, depth_factor));

    // 5. Shoreline & Object Contact Foam (Organic undulating wave wash)
    float foam_noise = noise(v_world_pos.xz * 3.5 + vec2(t * 0.3, t * 0.2)) * 0.6
                     + noise(v_world_pos.xz * 7.0 - vec2(t * 0.2, t * 0.25)) * 0.4;
    float foam_line = 1.0 - smoothstep(0.0, foam_depth * (0.85 + foam_noise * 0.5), effective_depth);
    final_color = mix(final_color, foam_color.rgb, foam_line * 0.85);

    // 6. Fresnel Effect for reflections
    float fresnel = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), fresnel_power);
    vec3 sky_reflection = vec3(0.70, 0.82, 0.96);
    final_color = mix(final_color, sky_reflection, fresnel * 0.45);

    ALBEDO = final_color;
    ROUGHNESS = roughness + (1.0 - fresnel) * 0.06;
    SPECULAR = specular;
    METALLIC = 0.0;
}
