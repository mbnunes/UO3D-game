shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

// =============================================================================
// terrain_shader.gdshader - Next-Gen PBR Ultima Online Terrain Shader (Godot 4.x)
//
// Etapa 3: PBR Terrain with Normal Maps, Triplanar Cliffs & Seamless Blending
//
// Features:
//   - Unpacks 16-bit TileID and elevation from vertex colors.
//   - High-fidelity procedural PBR Normal Mapping for all surface types.
//   - Triplanar cliff rock projection (eliminates texture stretching on mountains).
//   - Multi-scale PBR roughness, specular, and ambient occlusion (AO).
//   - Dynamic organic blending between grass, dry grass, dirt, sand, and rock.
//   - Seamless integration with Godot 4 SDFGI, SSAO, SSIL, and Cascaded Shadows.
// =============================================================================

group_uniforms PBR_Parameters;
uniform float normal_strength : hint_range(0.0, 3.0) = 1.35;
uniform float rock_normal_strength : hint_range(0.0, 3.0) = 1.8;
uniform float base_roughness : hint_range(0.0, 1.0) = 0.78;
uniform float base_specular : hint_range(0.0, 1.0) = 0.28;
uniform float ao_strength : hint_range(0.0, 1.0) = 0.65;

group_uniforms BiomeColors;
uniform vec3 grass_color : source_color = vec3(0.24, 0.48, 0.16);
uniform vec3 grass_dry_color : source_color = vec3(0.42, 0.52, 0.22);
uniform vec3 dirt_color : source_color = vec3(0.48, 0.38, 0.24);
uniform vec3 sand_color : source_color = vec3(0.82, 0.74, 0.50);
uniform vec3 rock_color : source_color = vec3(0.48, 0.48, 0.50);
uniform vec3 rock_dark_color : source_color = vec3(0.28, 0.28, 0.30);
uniform vec3 snow_color : source_color = vec3(0.92, 0.95, 0.98);
uniform vec3 lava_color : source_color = vec3(0.95, 0.28, 0.05);

group_uniforms TriplanarSettings;
uniform float cliff_slope_start : hint_range(0.1, 0.9) = 0.40;
uniform float cliff_slope_end : hint_range(0.1, 0.9) = 0.68;
uniform float triplanar_scale : hint_range(0.05, 2.0) = 0.35;

group_uniforms Debug;
uniform bool show_wireframe_grid = false;
uniform float grid_line_thickness : hint_range(0.01, 0.2) = 0.05;
uniform bool show_elevation_contours = false;
uniform float contour_interval : hint_range(0.5, 10.0) = 2.0;

varying vec3 v_world_pos;
varying vec3 v_normal;
varying vec4 v_vertex_color;

// Hash and Noise functions for procedural micro-detail & PBR relief
float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float hash13(vec3 p) {
    p = fract(p * 0.1031);
    p += dot(p, p.zyx + 31.32);
    return fract((p.x + p.y) * p.z);
}

float noise2d(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash12(i);
    float b = hash12(i + vec2(1.0, 0.0));
    float c = hash12(i + vec2(0.0, 1.0));
    float d = hash12(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float noise3d(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
        mix(mix(hash13(i + vec3(0,0,0)), hash13(i + vec3(1,0,0)), f.x),
            mix(hash13(i + vec3(0,1,0)), hash13(i + vec3(1,1,0)), f.x), f.y),
        mix(mix(hash13(i + vec3(0,0,1)), hash13(i + vec3(1,0,1)), f.x),
            mix(hash13(i + vec3(0,1,1)), hash13(i + vec3(1,1,1)), f.x), f.y),
        f.z
    );
}

float fbm2d(vec2 p) {
    float val = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 4; i++) {
        val += amp * noise2d(p);
        p *= 2.15;
        amp *= 0.5;
    }
    return val;
}

float fbm3d(vec3 p) {
    float val = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 3; i++) {
        val += amp * noise3d(p);
        p *= 2.08;
        amp *= 0.5;
    }
    return val;
}

// Analytical height field for ground PBR normal generation
float ground_height(vec2 p) {
    return fbm2d(p * 2.5) * 0.65 + noise2d(p * 8.0) * 0.25 + noise2d(p * 20.0) * 0.10;
}

// Procedural normal map from ground height derivatives
vec3 calculate_ground_normal(vec2 p, float strength) {
    float eps = 0.08;
    float hL = ground_height(p - vec2(eps, 0.0));
    float hR = ground_height(p + vec2(eps, 0.0));
    float hD = ground_height(p - vec2(0.0, eps));
    float hU = ground_height(p + vec2(0.0, eps));
    vec3 n = vec3((hL - hR) * strength, eps * 2.0, (hD - hU) * strength);
    return normalize(n);
}

// Triplanar procedural rock texture & normal (eliminates stretching on cliffs)
void get_triplanar_rock(vec3 pos, vec3 world_norm, out vec3 rock_col, out vec3 rock_norm, out float rock_rough) {
    vec3 blend_weights = pow(abs(world_norm), vec3(4.0));
    blend_weights /= (blend_weights.x + blend_weights.y + blend_weights.z + 0.0001);

    vec3 p = pos * triplanar_scale;

    // Rock layers / stratification
    float n_xy = fbm2d(vec2(p.x * 1.5, p.y * 3.0));
    float n_zy = fbm2d(vec2(p.z * 1.5, p.y * 3.0));
    float n_xz = fbm2d(vec2(p.x, p.z));

    float rock_pattern = n_xy * blend_weights.z + n_zy * blend_weights.x + n_xz * blend_weights.y;
    rock_col = mix(rock_dark_color, rock_color, rock_pattern);

    // Triplanar normal derivatives
    float eps = 0.06;
    float n_xy_r = fbm2d(vec2((p.x + eps) * 1.5, p.y * 3.0));
    float n_xy_u = fbm2d(vec2(p.x * 1.5, (p.y + eps) * 3.0));
    vec3 norm_z = vec3((n_xy - n_xy_r) * rock_normal_strength, (n_xy - n_xy_u) * rock_normal_strength, 1.0);

    float n_zy_r = fbm2d(vec2((p.z + eps) * 1.5, p.y * 3.0));
    float n_zy_u = fbm2d(vec2(p.z * 1.5, (p.y + eps) * 3.0));
    vec3 norm_x = vec3(1.0, (n_zy - n_zy_u) * rock_normal_strength, (n_zy - n_zy_r) * rock_normal_strength);

    float n_xz_r = fbm2d(vec2((p.x + eps), p.z));
    float n_xz_u = fbm2d(vec2(p.x, (p.z + eps)));
    vec3 norm_y = vec3((n_xz - n_xz_r) * rock_normal_strength, 1.0, (n_xz - n_xz_u) * rock_normal_strength);

    rock_norm = normalize(norm_x * blend_weights.x + norm_y * blend_weights.y + norm_z * blend_weights.z);
    rock_rough = clamp(0.55 + rock_pattern * 0.35, 0.45, 0.90);
}

uint unpack_tile_id(vec4 col) {
    uint r = uint(round(col.r * 255.0)) & 0xFFu;
    uint g = uint(round(col.g * 255.0)) & 0xFFu;
    return r | (g << 8u);
}

bool is_water_tile(uint tid) {
    return ((tid >= 168u && tid <= 171u) || (tid >= 310u && tid <= 311u) || (tid >= 0x00A4u && tid <= 0x00A7u));
}

void vertex() {
    v_world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    v_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
    v_vertex_color = COLOR;
}

void fragment() {
    uint tid = unpack_tile_id(v_vertex_color);

    // If water tile and user didn't hide ocean, keep subtle bedrock tint
    if (is_water_tile(tid)) {
        ALBEDO = vec3(0.04, 0.16, 0.28);
        ROUGHNESS = 0.15;
        SPECULAR = 0.5;
        METALLIC = 0.0;
    } else {
        // 1. Calculate slope (0.0 = completely flat ground, 1.0 = completely vertical wall)
        float slope = 1.0 - clamp(dot(v_normal, vec3(0.0, 1.0, 0.0)), 0.0, 1.0);

        // 2. Base Biome Color & Material properties
        vec3 base_col = grass_color;
        float mat_roughness = base_roughness;
        float mat_specular = base_specular;
        float mat_ao = 1.0;

        // Biome determination by TileID
        if ((tid >= 268u && tid <= 285u) || (tid >= 400u && tid <= 403u)) {
            // Snow
            float n = fbm2d(v_world_pos.xz * 0.4);
            base_col = mix(snow_color * 0.92, snow_color, n);
            mat_roughness = 0.35;
            mat_specular = 0.45;
        } else if (tid >= 500u && tid <= 507u) {
            // Lava
            float pulse = sin(TIME * 2.5 + v_world_pos.x * 0.6 + v_world_pos.z * 0.6) * 0.5 + 0.5;
            base_col = mix(lava_color, vec3(1.0, 0.75, 0.1), pulse * 0.6);
            mat_roughness = 0.25;
            mat_specular = 0.8;
            EMISSION = base_col * (pulse * 1.2 + 0.3);
        } else if ((tid >= 22u && tid <= 25u) || (tid >= 51u && tid <= 59u) || (tid >= 446u && tid <= 449u)) {
            // Sand / Beach
            float n = fbm2d(v_world_pos.xz * 0.6);
            base_col = mix(sand_color * 0.93, sand_color * 1.07, n);
            mat_roughness = 0.72;
            mat_specular = 0.35;
        } else if ((tid >= 113u && tid <= 120u) || (tid >= 228u && tid <= 235u) || (tid >= 368u && tid <= 375u)) {
            // Dirt / Pathways
            float n = fbm2d(v_world_pos.xz * 0.5);
            base_col = mix(dirt_color * 0.88, dirt_color * 1.12, n);
            mat_roughness = 0.86;
            mat_specular = 0.18;
        } else if ((tid >= 220u && tid <= 263u) || (tid >= 543u && tid <= 579u) || (tid >= 676u && tid <= 695u)) {
            // Mountain rock
            slope = max(slope, 0.55); // Force rock treatment on mountain tiles
        } else {
            // Grass (Default Britannian soil with dry/lush organic patches)
            float patch_noise = fbm2d(v_world_pos.xz * 0.2);
            float micro_noise = fbm2d(v_world_pos.xz * 1.2);
            base_col = mix(grass_color, grass_dry_color, patch_noise);
            base_col = mix(base_col, base_col * 1.15, micro_noise * 0.5);
            mat_roughness = 0.74;
            mat_specular = 0.25;
        }

        // 3. Ground PBR Normal Mapping
        vec3 ground_norm_local = calculate_ground_normal(v_world_pos.xz, normal_strength);
        // Align ground normal to world coordinates
        vec3 ground_norm_world = normalize(vec3(ground_norm_local.x, ground_norm_local.y * v_normal.y, ground_norm_local.z));

        // 4. Triplanar Cliff Rock Mapping (for steep mountains & cliffs)
        vec3 rock_col;
        vec3 rock_norm;
        float rock_rough;
        get_triplanar_rock(v_world_pos, v_normal, rock_col, rock_norm, rock_rough);

        // Smooth slope transition: Flat ground -> Steep rocky cliff
        float cliff_factor = smoothstep(cliff_slope_start, cliff_slope_end, slope);
        vec3 final_albedo = mix(base_col, rock_col, cliff_factor);
        vec3 final_world_norm = normalize(mix(ground_norm_world, rock_norm, cliff_factor));
        float final_roughness = mix(mat_roughness, rock_rough, cliff_factor);
        float final_specular = mix(mat_specular, 0.32, cliff_factor);

        // 5. Procedural Ambient Occlusion (Cavity darkening in soil & rock cracks)
        float cavity = clamp(ground_height(v_world_pos.xz * 1.8), 0.0, 1.0);
        mat_ao = mix(1.0 - ao_strength * 0.3, 1.0, cavity);
        final_albedo *= mat_ao;

        // Convert world normal to view space for Godot fragment pipeline
        NORMAL = normalize((VIEW_MATRIX * vec4(final_world_norm, 0.0)).xyz);

        // Debug overlays
        if (show_wireframe_grid) {
            vec2 grid = abs(fract(v_world_pos.xz - 0.5) - 0.5) / fwidth(v_world_pos.xz);
            float line = min(grid.x, grid.y);
            float c = 1.0 - min(line, 1.0);
            final_albedo = mix(final_albedo, vec3(0.0), c * 0.5);
        }

        if (show_elevation_contours) {
            float f = abs(fract(v_world_pos.y / contour_interval) - 0.5);
            float df = fwidth(v_world_pos.y / contour_interval);
            float contour = 1.0 - smoothstep(0.0, df * 1.5, f);
            final_albedo = mix(final_albedo, vec3(1.0, 1.0, 1.0), contour * 0.4);
        }

        ALBEDO = final_albedo;
        ROUGHNESS = final_roughness;
        SPECULAR = final_specular;
        METALLIC = 0.0;
        AO = mat_ao;
    }
}
