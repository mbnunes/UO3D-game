shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

// terrain_shader.gdshader - Ultima Online 3D Terrain Shader for Godot 4.x
//
// Extracts 16-bit TileID and elevation from vertex colors:
//   COLOR.r = TileID low byte
//   COLOR.g = TileID high byte
//   COLOR.b = Normalized elevation (Z + 128) / 255
//
// Maps TileIDs to classic UO biomes (Water, Grass, Dirt, Sand, Mountain/Rock, Snow, Lava).
// Supports optional procedural wireframe grid and elevation contours.

group_uniforms Shading;
uniform float roughness : hint_range(0.0, 1.0) = 0.85;
uniform float specular : hint_range(0.0, 1.0) = 0.2;
uniform bool show_wireframe_grid = false;
uniform float grid_line_thickness : hint_range(0.01, 0.2) = 0.05;
uniform bool show_elevation_contours = false;
uniform float contour_interval : hint_range(0.5, 10.0) = 2.0;

group_uniforms BiomeColors;
uniform vec3 water_color : source_color = vec3(0.12, 0.35, 0.75);
uniform vec3 grass_color : source_color = vec3(0.22, 0.52, 0.18);
uniform vec3 dirt_color : source_color = vec3(0.58, 0.44, 0.28);
uniform vec3 sand_color : source_color = vec3(0.82, 0.76, 0.52);
uniform vec3 rock_color : source_color = vec3(0.48, 0.48, 0.48);
uniform vec3 snow_color : source_color = vec3(0.92, 0.94, 0.96);
uniform vec3 lava_color : source_color = vec3(0.95, 0.25, 0.05);

varying vec3 v_world_pos;
varying vec4 v_vertex_color;

void vertex() {
    v_world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    v_vertex_color = COLOR;
}

uint unpack_tile_id(vec4 col) {
    uint r = uint(round(col.r * 255.0)) & 0xFFu;
    uint g = uint(round(col.g * 255.0)) & 0xFFu;
    return r | (g << 8u);
}

vec3 get_biome_color(uint tid) {
    // Ultima Online Classic Land Tile ID Ranges:
    // Water: 0x0A8..0x0AB (168..171), 0x0136..0x0137 (310..311), 0x310..0x311, etc.
    if ((tid >= 168u && tid <= 171u) || (tid >= 310u && tid <= 311u) || (tid >= 0x00A4u && tid <= 0x00A7u)) {
        return water_color;
    }
    // Grass: 0x0003..0x0015 (3..21), 0x01AC..0x01BE (428..446), 0x02C4..0x02D3
    if ((tid >= 3u && tid <= 21u) || (tid >= 428u && tid <= 446u) || (tid >= 708u && tid <= 723u)) {
        return grass_color;
    }
    // Sand: 0x0016..0x0019 (22..25), 0x0033..0x003B (51..59), 0x01BE..0x01C1
    if ((tid >= 22u && tid <= 25u) || (tid >= 51u && tid <= 59u) || (tid >= 446u && tid <= 449u)) {
        return sand_color;
    }
    // Dirt / Furrows: 0x0009..0x000C, 0x0071..0x0078 (113..120), 0x00E4..0x00EB
    if ((tid >= 113u && tid <= 120u) || (tid >= 228u && tid <= 235u) || (tid >= 368u && tid <= 375u)) {
        return dirt_color;
    }
    // Rock / Mountain / Cave: 0x00DC..0x00FB (220..251), 0x021F..0x0243 (543..579)
    if ((tid >= 220u && tid <= 263u) || (tid >= 543u && tid <= 579u) || (tid >= 676u && tid <= 695u)) {
        return rock_color;
    }
    // Snow: 0x010C..0x011D (268..285), 0x0190..0x0193
    if ((tid >= 268u && tid <= 285u) || (tid >= 400u && tid <= 403u)) {
        return snow_color;
    }
    // Lava: 0x01F4..0x01FB (500..507)
    if (tid >= 500u && tid <= 507u) {
        return lava_color;
    }

    // Procedural color hash for unmapped tiles
    float hash = fract(sin(float(tid) * 12.9898) * 43758.5453);
    float hash2 = fract(sin(float(tid) * 78.233) * 43758.5453);
    return vec3(0.25 + 0.5 * hash, 0.35 + 0.4 * hash2, 0.2 + 0.3 * fract(hash + hash2));
}

void fragment() {
    uint tid = unpack_tile_id(v_vertex_color);
    vec3 base_color = get_biome_color(tid);

    // Optional subtle elevation gradient based on normalized Z
    float elev = v_vertex_color.b;
    base_color *= (0.85 + 0.3 * elev);

    // Optional wireframe grid overlay (1-meter tile grid)
    if (show_wireframe_grid) {
        vec2 grid = abs(fract(v_world_pos.xz - 0.5) - 0.5) / fwidth(v_world_pos.xz);
        float line = min(grid.x, grid.y);
        float c = 1.0 - min(line, 1.0);
        base_color = mix(base_color, vec3(0.0), c * 0.5);
    }

    // Optional elevation contour lines
    if (show_elevation_contours) {
        float f = abs(fract(v_world_pos.y / contour_interval) - 0.5);
        float df = fwidth(v_world_pos.y / contour_interval);
        float contour = 1.0 - smoothstep(0.0, df * 1.5, f);
        base_color = mix(base_color, vec3(1.0, 1.0, 1.0), contour * 0.4);
    }

    ALBEDO = base_color;
    ROUGHNESS = roughness;
    SPECULAR = specular;
    METALLIC = 0.0;
}
