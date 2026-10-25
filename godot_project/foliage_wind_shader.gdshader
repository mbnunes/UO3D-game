shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled, diffuse_burley, specular_schlick_ggx;

// =============================================================================
// foliage_wind_shader.gdshader - Dynamic Wind & Translucent Foliage for UO 3D
//
// Etapa 4: Dynamic Vegetation with Wind Vertex Displacement
//
// Features:
//   - Physical wind sway driven by directional gusts and turbulence.
//   - Height-based stiffness (tree trunks stay firmly anchored, upper canopy sways).
//   - Micro-leaf flutter (high frequency trembling in the breeze).
//   - Subsurface scattering simulation (foliage glows warmly when backlit by sunlight).
//   - Alpha testing / cutout for crisp UO tree leaves and branches.
// =============================================================================

group_uniforms WindSettings;
uniform vec3 wind_direction = vec3(1.0, 0.0, 0.5);
uniform float wind_speed : hint_range(0.1, 5.0) = 1.6;
uniform float wind_strength : hint_range(0.0, 1.5) = 0.35;
uniform float leaf_flutter_speed : hint_range(0.5, 15.0) = 6.0;
uniform float leaf_flutter_strength : hint_range(0.0, 0.3) = 0.04;
uniform float trunk_height_anchor : hint_range(0.0, 10.0) = 1.0;

group_uniforms FoliageMaterial;
uniform sampler2D texture_albedo : source_color, filter_linear_mipmap;
uniform vec4 foliage_tint : source_color = vec4(0.85, 1.0, 0.85, 1.0);
uniform float alpha_scissor_threshold : hint_range(0.0, 1.0) = 0.5;
uniform float roughness : hint_range(0.0, 1.0) = 0.65;
uniform float specular : hint_range(0.0, 1.0) = 0.2;
uniform float subsurface_scattering : hint_range(0.0, 1.0) = 0.45;

varying vec3 v_world_pos;
varying vec3 v_local_vertex;

void vertex() {
    v_world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    v_local_vertex = VERTEX;

    // Anchor: displacement only affects vertices above trunk_height_anchor
    float height_factor = clamp((VERTEX.y - trunk_height_anchor) * 0.25, 0.0, 1.0);
    height_factor = height_factor * height_factor; // quadratic curve for realistic branch bending

    if (height_factor > 0.001) {
        vec3 wind_dir = normalize(wind_direction);
        float t = TIME * wind_speed;

        // Large macro wind wave traversing the landscape
        float wave_pos = dot(v_world_pos.xz, wind_dir.xz) * 0.15 + t;
        float main_sway = sin(wave_pos) * 0.7 + sin(wave_pos * 1.83) * 0.3;

        // Local branch turbulence
        float branch_turb = cos(v_world_pos.y * 1.5 + t * 1.3 + v_world_pos.x * 0.8);

        // High-frequency leaf flutter
        float flutter = sin(TIME * leaf_flutter_speed + v_world_pos.x * 4.0 + v_world_pos.z * 4.0);

        // Combined displacement vector
        vec3 displacement = wind_dir * (main_sway * wind_strength + branch_turb * wind_strength * 0.4);
        displacement.y -= abs(main_sway) * wind_strength * 0.2; // naturally droop down slightly when pushed by wind
        displacement += vec3(flutter, flutter * 0.5, flutter) * leaf_flutter_strength;

        VERTEX += displacement * height_factor;
    }
}

void fragment() {
    vec4 tex = texture(texture_albedo, UV);
    vec4 final_color = tex * foliage_tint;

    // Alpha scissor for crisp foliage silhouettes
    if (final_color.a < alpha_scissor_threshold) {
        discard;
    }

    // Subsurface scattering glow when backlit by light
    float sss = subsurface_scattering * (1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0));
    vec3 sunlit_albedo = final_color.rgb + vec3(0.08, 0.12, 0.02) * sss;

    ALBEDO = sunlit_albedo;
    ROUGHNESS = roughness;
    SPECULAR = specular;
    METALLIC = 0.0;

    // Translucent light passing through two-sided leaves
    BACKLIGHT = final_color.rgb * (subsurface_scattering * 0.5);
}
