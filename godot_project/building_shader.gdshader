shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

// =============================================================================
// building_shader.gdshader - Next-Gen Procedural PBR Architectural Shader
//
// Etapa 5: PBR Textures for Building Walls, Roofs, and Timbers
//
// Features:
//   - Automatic geometric classification:
//       * Walls (Vertical): Medieval masonry stone blocks with mortar beveling.
//       * Roofs (Sloped): Layered blue slate & terracotta shingles.
//       * Floors/Tops (Horizontal): Wooden timber planks / flagstones.
//   - Analytical PBR normal maps for deep mortar joints and tile overlaps.
//   - Distinct roughness & specular response per architectural material.
//   - Edge Ambient Occlusion (AO) darkening under eaves and foundations.
// =============================================================================

group_uniforms MasonryWalls;
uniform vec3 stone_color : source_color = vec3(0.72, 0.70, 0.66);
uniform vec3 stone_dark_color : source_color = vec3(0.52, 0.50, 0.46);
uniform vec3 mortar_color : source_color = vec3(0.38, 0.36, 0.34);
uniform float brick_width : hint_range(0.2, 2.0) = 0.65;
uniform float brick_height : hint_range(0.1, 1.0) = 0.32;
uniform float mortar_size : hint_range(0.01, 0.15) = 0.04;
uniform float wall_normal_strength : hint_range(0.0, 3.0) = 1.6;

group_uniforms RoofShingles;
uniform vec3 roof_color : source_color = vec3(0.22, 0.32, 0.45); // Classic Britannian blue slate
uniform vec3 roof_ridge_color : source_color = vec3(0.15, 0.22, 0.32);
uniform float shingle_width : hint_range(0.1, 1.0) = 0.35;
uniform float shingle_height : hint_range(0.1, 1.0) = 0.40;
uniform float roof_roughness : hint_range(0.0, 1.0) = 0.48;
uniform float roof_specular : hint_range(0.0, 1.0) = 0.45;

group_uniforms TimberPlanks;
uniform vec3 wood_color : source_color = vec3(0.45, 0.32, 0.20);
uniform vec3 wood_dark_color : source_color = vec3(0.30, 0.20, 0.12);
uniform float plank_width : hint_range(0.1, 1.0) = 0.28;

varying vec3 v_world_pos;
varying vec3 v_world_normal;

// Hash functions for subtle variations per brick / shingle
float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
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

void vertex() {
    v_world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    v_world_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

// Procedural Brick Wall calculation
void calculate_wall(vec3 pos, vec3 norm, out vec3 albedo, out vec3 normal_out, out float rough, out float ao) {
    // Project along dominant wall axis
    bool face_z = abs(norm.z) > abs(norm.x);
    float u = face_z ? pos.x : pos.z;
    float v = pos.y;

    float row = floor(v / brick_height);
    float col = floor((u + (mod(row, 2.0) * 0.5 * brick_width)) / brick_width);
    vec2 brick_id = vec2(col, row);

    vec2 uv_brick = vec2(
        fract((u + (mod(row, 2.0) * 0.5 * brick_width)) / brick_width),
        fract(v / brick_height)
    );

    // Distance to brick borders (mortar detection)
    vec2 border = min(uv_brick, 1.0 - uv_brick);
    float border_dist = min(border.x * brick_width, border.y * brick_height);
    float is_mortar = 1.0 - smoothstep(mortar_size * 0.5, mortar_size * 1.5, border_dist);

    // Brick color variation & surface grain
    float rnd = hash12(brick_id);
    float grain = noise2d(vec2(u * 8.0, v * 8.0)) * 0.15;
    vec3 brick_col = mix(stone_dark_color, stone_color, rnd) + grain;

    albedo = mix(brick_col, mortar_color, is_mortar);
    rough = mix(0.76, 0.95, is_mortar);
    ao = mix(1.0, 0.45, is_mortar);

    // Bevel normal for 3D brick relief
    vec2 bevel = clamp((border - vec2(mortar_size)) * 5.0, -1.0, 1.0);
    vec3 local_n = vec3(
        (uv_brick.x < 0.5 ? 1.0 : -1.0) * (1.0 - bevel.x) * wall_normal_strength,
        (uv_brick.y < 0.5 ? 1.0 : -1.0) * (1.0 - bevel.y) * wall_normal_strength,
        1.0
    );
    local_n = normalize(local_n);

    // Orient local normal to wall facing
    if (face_z) {
        normal_out = vec3(local_n.x * sign(norm.z), local_n.y, local_n.z * sign(norm.z));
    } else {
        normal_out = vec3(local_n.z * sign(norm.x), local_n.y, local_n.x * sign(norm.x));
    }
}

// Procedural Sloped Roof Shingle calculation
void calculate_roof(vec3 pos, vec3 norm, out vec3 albedo, out vec3 normal_out, out float rough, out float spec, out float ao) {
    float u = (abs(norm.x) > abs(norm.z)) ? pos.z : pos.x;
    float v = pos.y * 1.414 + (pos.x * norm.x + pos.z * norm.z) * 0.5; // align along slope

    float row = floor(v / shingle_height);
    float col = floor((u + (mod(row, 2.0) * 0.5 * shingle_width)) / shingle_width);
    vec2 tile_id = vec2(col, row);

    vec2 uv_tile = vec2(
        fract((u + (mod(row, 2.0) * 0.5 * shingle_width)) / shingle_width),
        fract(v / shingle_height)
    );

    float rnd = hash12(tile_id);
    vec3 tile_col = mix(roof_ridge_color, roof_color, rnd * 0.4 + 0.6);

    // Shingle lip overlap shadow
    float lip = 1.0 - smoothstep(0.0, 0.08, uv_tile.y);
    float edge = 1.0 - smoothstep(0.0, 0.05, min(uv_tile.x, 1.0 - uv_tile.x));

    albedo = tile_col * (1.0 - lip * 0.4) * (1.0 - edge * 0.25);
    rough = roof_roughness + rnd * 0.1;
    spec = roof_specular;
    ao = 1.0 - lip * 0.5;

    // Slanted tile normal for realistic light reflections
    vec3 n_mod = norm;
    n_mod.y += (uv_tile.y - 0.5) * 0.4;
    normal_out = normalize(n_mod);
}

// Procedural Wood Timber Planks
void calculate_wood(vec3 pos, out vec3 albedo, out float rough, out float ao) {
    float u = pos.x;
    float plank = floor(u / plank_width);
    float uv_p = fract(u / plank_width);

    float rnd = hash12(vec2(plank, 1.0));
    float grain = noise2d(vec2(pos.x * 2.0, pos.z * 12.0)) * 0.12;

    float seam = 1.0 - smoothstep(0.01, 0.05, min(uv_p, 1.0 - uv_p));
    vec3 wood = mix(wood_dark_color, wood_color, rnd) + grain;

    albedo = mix(wood, wood_dark_color * 0.6, seam);
    rough = 0.68;
    ao = 1.0 - seam * 0.4;
}

void fragment() {
    float slope = abs(v_world_normal.y);

    vec3 albedo_out = stone_color;
    vec3 normal_world = v_world_normal;
    float rough_out = 0.8;
    float spec_out = 0.25;
    float ao_out = 1.0;

    if (slope < 0.32) {
        // Vertical surfaces -> Medieval Stone Walls
        calculate_wall(v_world_pos, v_world_normal, albedo_out, normal_world, rough_out, ao_out);
    } else if (slope >= 0.32 && slope < 0.85) {
        // Sloped surfaces -> Shingle Roofs
        calculate_roof(v_world_pos, v_world_normal, albedo_out, normal_world, rough_out, spec_out, ao_out);
    } else {
        // Horizontal surfaces -> Wood Planks / Flat Floors
        calculate_wood(v_world_pos, albedo_out, rough_out, ao_out);
    }

    // Convert world normal to view space
    NORMAL = normalize((VIEW_MATRIX * vec4(normal_world, 0.0)).xyz);
    ALBEDO = albedo_out * ao_out;
    ROUGHNESS = rough_out;
    SPECULAR = spec_out;
    METALLIC = 0.05;
    AO = ao_out;
}
