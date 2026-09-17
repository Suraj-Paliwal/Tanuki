/**
 * Sharpness helpers.
 *
 * The tanuki's face occupies under 2% of its texture atlas - about 287x287
 * texels - so on screen it is always being magnified several times over. That
 * ceiling is in the source model and no renderer setting removes it, but two
 * things claw back most of the perceived softness:
 *
 *   applyTextureQuality()  anisotropic filtering, which is off by default in
 *                          three.js and costs nothing
 *   sharpenPass()          contrast-adaptive sharpening on the final image
 */
import * as THREE from 'three';

/** Max anisotropy + correct colour space on every texture in the subtree. */
export function applyTextureQuality(object, renderer, { anisotropy } = {}) {
  const max = anisotropy ?? renderer.capabilities.getMaxAnisotropy();
  const seen = new Set();
  object.traverse((o) => {
    const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
    for (const m of mats) {
      for (const key of ['map', 'normalMap', 'roughnessMap', 'metalnessMap',
                         'aoMap', 'emissiveMap']) {
        const t = m[key];
        if (!t || seen.has(t)) continue;
        seen.add(t);
        t.anisotropy = max;
        t.minFilter = THREE.LinearMipmapLinearFilter;
        t.magFilter = THREE.LinearFilter;
        t.generateMipmaps = true;
        t.needsUpdate = true;
      }
    }
  });
  return max;
}

/**
 * FidelityFX-style Contrast Adaptive Sharpening.
 *
 * Adaptive, not a flat unsharp mask: the amount is scaled by how much local
 * headroom there is, so edges tighten while flat fur is left alone and does
 * not turn crunchy. `sharpness` 0..1. With the pre-sharpened textures in 07_web_model, 0.2-0.3
 * is right; push to 0.5 only if you swap back to the unsharpened maps.
 */
export const CASShader = {
  name: 'CASShader',
  uniforms: {
    tDiffuse:   { value: null },
    resolution: { value: new THREE.Vector2(1, 1) },
    sharpness:  { value: 0.25 },
  },
  vertexShader: /* glsl */`
    varying vec2 vUv;
    void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }
  `,
  fragmentShader: /* glsl */`
    uniform sampler2D tDiffuse;
    uniform vec2 resolution;
    uniform float sharpness;
    varying vec2 vUv;

    void main() {
      vec2 px = 1.0 / resolution;
      vec3 c  = texture2D(tDiffuse, vUv).rgb;
      vec3 n  = texture2D(tDiffuse, vUv + vec2(0.0, -px.y)).rgb;
      vec3 s  = texture2D(tDiffuse, vUv + vec2(0.0,  px.y)).rgb;
      vec3 w  = texture2D(tDiffuse, vUv + vec2(-px.x, 0.0)).rgb;
      vec3 e  = texture2D(tDiffuse, vUv + vec2( px.x, 0.0)).rgb;

      vec3 mn = min(c, min(min(n, s), min(w, e)));
      vec3 mx = max(c, max(max(n, s), max(w, e)));

      // headroom: how much this pixel can be pushed before clipping
      vec3 amp = clamp(min(mn, 1.0 - mx) / max(mx, 1e-4), 0.0, 1.0);
      amp = sqrt(amp);

      // peak weight, lerped between the gentle and strong CAS constants
      float peak = -1.0 / mix(8.0, 5.0, clamp(sharpness, 0.0, 1.0));
      vec3 wgt = amp * peak;

      vec3 outc = (n + s + w + e) * wgt + c;
      outc /= (4.0 * wgt + 1.0);
      // Opaque on purpose. This is the final display pass, and the composer's
      // render target carries alpha 0 in untouched areas - passing that through
      // makes the whole canvas transparent and nothing appears at all.
      gl_FragColor = vec4(clamp(outc, 0.0, 1.0), 1.0);
    }
  `,
};
