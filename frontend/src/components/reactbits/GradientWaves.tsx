/**
 * GradientWaves — React Bits (reactbits.dev/backgrounds/gradient-waves), adapted.
 *
 * Adaptations for Aegis:
 *  - TypeScript props.
 *  - Colours retuned from the docs' purple default to our navy/blue palette.
 *  - MANDATORY FALLBACK: WebGL2 support is feature-checked AND renderer
 *    construction is wrapped in try/catch. On any failure the canvas is never
 *    attached (and any partial canvas is removed), and a pure-CSS animated
 *    navy gradient renders instead — silently, no error surface, no broken
 *    canvas left in the DOM. The login page is the first thing anyone sees;
 *    it must never visibly break.
 *  - prefers-reduced-motion: skips WebGL entirely and renders a STATIC
 *    gradient (no animation at all).
 */

import { Mesh, Program, Renderer, Triangle } from "ogl";
import { useEffect, useRef, useState } from "react";

import "./GradientWaves.css";

const hexToRgb = (hex: string): [number, number, number] => {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!result) return [1, 1, 1];
  return [
    parseInt(result[1], 16) / 255,
    parseInt(result[2], 16) / 255,
    parseInt(result[3], 16) / 255,
  ];
};

const detailToSteps = (detail: string) =>
  detail === "low" ? 40.0 : detail === "high" ? 110.0 : 70.0;

const vertex = `#version 300 es
in vec2 position;
void main() {
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

const fragment = `#version 300 es
precision highp float;
uniform vec2 iResolution;
uniform float iTime;
uniform float uSpeed;
uniform float uAmplitude;
uniform float uWaveScale;
uniform float uWaveRatio;
uniform float uSwell;
uniform float uTurbulence;
uniform float uTilt;
uniform float uZoom;
uniform float uHeight;
uniform float uFogDepth;
uniform float uSteps;
uniform float uBrightness;
uniform float uOpacity;
uniform float uGrain;
uniform float uGrainIntensity;
uniform vec2 uMouse;
uniform float uParallax;
uniform bool uEnableMouse;
uniform vec3 uHorizonColor;
uniform vec3 uWaveColor;
uniform vec3 uCrestColor;
out vec4 fragColor;

const float MAX_DIST = 20000.0;

float hash21(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

float plasma(vec3 r, vec2 freq, vec4 tc) {
  float mx = r.x + tc.x;
  mx += uSwell * sin((r.y + mx) / 20.0 + tc.y);
  float my = r.y - tc.z;
  my += uTurbulence * cos(r.x / 23.0 + tc.w);
  return r.z - (sin(mx * freq.x) * uAmplitude + sin(my * freq.y) * uAmplitude + uHeight);
}

float raymarch(vec3 pos, vec3 dir, vec2 freq, vec4 tc) {
  float dist = 0.0;
  for (int i = 0; i < 128; i++) {
    if (float(i) >= uSteps) break;
    float dscene = plasma(pos + dist * dir, freq, tc);
    if (abs(dscene) < 0.1) break;
    dist += 0.9 * dscene;
    if (!(abs(dist) < MAX_DIST)) return MAX_DIST;
  }
  return dist;
}

void main() {
  float T = iTime * uSpeed;
  vec2 freq = vec2(uWaveScale / 7.0, (uWaveScale * uWaveRatio) / 3.0);
  vec4 tc = vec4(T / 0.130, T / 0.810, T / 0.200, T / 0.710);
  float c, s;
  float vfov = (3.14159 / 2.3) / max(uZoom, 0.05);
  vec3 cam = vec3(0.0, 0.0, 30.0);
  vec2 uv = (gl_FragCoord.xy / iResolution.xy) - 0.5;
  uv.x *= iResolution.x / iResolution.y;
  uv.y *= -1.0;

  vec3 dir = vec3(0.0, 0.0, -1.0);
  float ulen = length(uv);
  float xrot = vfov * ulen;
  c = cos(xrot); s = sin(xrot);
  dir = mat3(1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c) * dir;
  vec2 nuv = ulen > 1e-5 ? uv / ulen : vec2(1.0, 0.0);
  c = nuv.x; s = nuv.y;
  dir = mat3(c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0) * dir;
  c = cos(uTilt); s = sin(uTilt);
  dir = mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c) * dir;

  if (uEnableMouse) {
    float yaw = (uMouse.x - 0.5) * uParallax * 0.4;
    float pitch = (uMouse.y - 0.5) * uParallax * 0.4;
    c = cos(yaw); s = sin(yaw);
    dir = mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c) * dir;
    c = cos(pitch); s = sin(pitch);
    dir = mat3(1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c) * dir;
  }

  float dist = raymarch(cam, dir, freq, tc);
  vec3 pos = cam + dist * dir;

  float t = clamp(uFogDepth / max(dist, 0.001), 0.0, 1.0);
  vec3 body = mix(uWaveColor, uCrestColor, clamp(pos.z * 0.08 + 0.5, 0.0, 1.0));
  vec3 col = mix(uHorizonColor, body, t);
  col *= uBrightness;
  col = clamp(col, 0.0, 1.0);

  float alpha = clamp(t, 0.0, 1.0) * uOpacity;
  if (uGrain > 0.5) {
    float g = hash21(gl_FragCoord.xy + mod(iTime, 64.0) * 11.0);
    alpha += (g - 0.5) * uGrainIntensity;
  }
  alpha = clamp(alpha, 0.0, 1.0);
  fragColor = vec4(col * alpha, alpha);
}
`;

export interface GradientWavesProps {
  horizonColor?: string;
  waveColor?: string;
  crestColor?: string;
  speed?: number;
  amplitude?: number;
  waveScale?: number;
  waveRatio?: number;
  swell?: number;
  turbulence?: number;
  tilt?: number;
  zoom?: number;
  height?: number;
  fogDepth?: number;
  detail?: "low" | "medium" | "high";
  brightness?: number;
  opacity?: number;
  mouseInteraction?: boolean;
  parallaxStrength?: number;
  grain?: boolean;
  grainIntensity?: number;
  className?: string;
}

/** Cheap pre-flight: can this browser give us a WebGL2 context at all? */
function supportsWebGL2(): boolean {
  try {
    const probe = document.createElement("canvas");
    const ctx = probe.getContext("webgl2");
    if (!ctx) return false;
    ctx.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}

function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

export default function GradientWaves({
  // Sarvam palette on paper: near-white horizon, pale indigo waves, white
  // crests. The hero is a light surface now, so the shader tints rather than
  // dominates — dark values here would reintroduce the black panel.
  horizonColor = "#FAFAFA",
  waveColor = "#D2DFF9",
  crestColor = "#FFFFFF",
  speed = 0.22,
  amplitude = 1.7,
  waveScale = 0.55,
  waveRatio = 0.9,
  swell = 24,
  turbulence = 10,
  tilt = 1.11,
  zoom = 1.0,
  height = 5.5,
  fogDepth = 15,
  detail = "low",
  brightness = 1.0,
  opacity = 0.9,
  mouseInteraction = false,
  parallaxStrength = 0.35,
  grain = true,
  grainIntensity = 0.03,
  className = "",
}: GradientWavesProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // "webgl" until proven otherwise; flips to a CSS mode on any failure.
  const [mode, setMode] = useState<"webgl" | "css-animated" | "css-static">(() => {
    if (prefersReducedMotion()) return "css-static";
    return supportsWebGL2() ? "webgl" : "css-animated";
  });

  useEffect(() => {
    if (mode !== "webgl") return;
    const container = containerRef.current;
    if (!container) return;

    let renderer: Renderer;
    // ogl exposes its own context type (OGLRenderingContext); use it rather
    // than WebGL2RenderingContext so Program/Mesh/Triangle accept it.
    let gl: Renderer["gl"];
    let canvas: HTMLCanvasElement;
    let program: Program;
    let mesh: Mesh;

    // --- Guarded construction: any throw here falls back to CSS silently. ---
    try {
      renderer = new Renderer({
        webgl: 2,
        alpha: true,
        premultipliedAlpha: true,
        antialias: false,
        dpr: Math.min(window.devicePixelRatio || 1, 2),
      });
      gl = renderer.gl;
      if (!gl) throw new Error("no gl context");
      gl.clearColor(0, 0, 0, 0);

      canvas = gl.canvas as HTMLCanvasElement;
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      canvas.style.display = "block";

      const geometry = new Triangle(gl);
      program = new Program(gl, {
        vertex,
        fragment,
        uniforms: {
          iTime: { value: 0 },
          iResolution: { value: new Float32Array([1, 1]) },
          uSpeed: { value: speed },
          uAmplitude: { value: amplitude },
          uWaveScale: { value: waveScale },
          uWaveRatio: { value: waveRatio },
          uSwell: { value: swell },
          uTurbulence: { value: turbulence },
          uTilt: { value: tilt },
          uZoom: { value: zoom },
          uHeight: { value: height },
          uFogDepth: { value: fogDepth },
          uSteps: { value: detailToSteps(detail) },
          uBrightness: { value: brightness },
          uOpacity: { value: opacity },
          uGrain: { value: grain ? 1.0 : 0.0 },
          uGrainIntensity: { value: grainIntensity },
          uMouse: { value: new Float32Array([0.5, 0.5]) },
          uParallax: { value: parallaxStrength },
          uEnableMouse: { value: mouseInteraction },
          uHorizonColor: { value: new Float32Array(hexToRgb(horizonColor)) },
          uWaveColor: { value: new Float32Array(hexToRgb(waveColor)) },
          uCrestColor: { value: new Float32Array(hexToRgb(crestColor)) },
        },
      });
      mesh = new Mesh(gl, { geometry, program });
      // Only attach once everything above succeeded — a failed init never
      // leaves a canvas element behind.
      container.appendChild(canvas);
    } catch {
      setMode("css-animated");
      return;
    }

    let raf = 0;
    let disposed = false;

    const setSize = () => {
      if (disposed) return;
      try {
        const rect = container.getBoundingClientRect();
        renderer.setSize(Math.max(1, Math.floor(rect.width)), Math.max(1, Math.floor(rect.height)));
        const res = program.uniforms.iResolution.value as Float32Array;
        res[0] = gl.drawingBufferWidth;
        res[1] = gl.drawingBufferHeight;
        renderer.render({ scene: mesh });
      } catch {
        /* a resize failure is not worth tearing the page down for */
      }
    };

    const ro = new ResizeObserver(setSize);
    ro.observe(container);
    setSize();

    const currentMouse = [0.5, 0.5];
    const targetMouse = [0.5, 0.5];
    const onPointerMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      targetMouse[0] = (e.clientX - rect.left) / rect.width;
      targetMouse[1] = 1.0 - (e.clientY - rect.top) / rect.height;
    };
    const onPointerLeave = () => {
      targetMouse[0] = 0.5;
      targetMouse[1] = 0.5;
    };
    if (mouseInteraction) {
      canvas.addEventListener("pointermove", onPointerMove);
      canvas.addEventListener("pointerleave", onPointerLeave);
    }

    let isVisible = true;
    let isPageVisible = !document.hidden;
    const t0 = performance.now();

    const loop = (t: number) => {
      if (disposed) return;
      try {
        program.uniforms.iTime.value = (t - t0) * 0.001;
        const tx = mouseInteraction ? targetMouse[0] : 0.5;
        const ty = mouseInteraction ? targetMouse[1] : 0.5;
        currentMouse[0] += 0.05 * (tx - currentMouse[0]);
        currentMouse[1] += 0.05 * (ty - currentMouse[1]);
        (program.uniforms.uMouse.value as Float32Array)[0] = currentMouse[0];
        (program.uniforms.uMouse.value as Float32Array)[1] = currentMouse[1];
        renderer.render({ scene: mesh });
        raf = requestAnimationFrame(loop);
      } catch {
        // Context lost mid-flight (GPU reset, tab throttling, driver crash):
        // stop cleanly and hand over to the CSS gradient.
        raf = 0;
        setMode("css-animated");
      }
    };

    const tryStart = () => {
      if (isVisible && isPageVisible && raf === 0 && !disposed) raf = requestAnimationFrame(loop);
    };
    const tryStop = () => {
      if (raf !== 0) {
        cancelAnimationFrame(raf);
        raf = 0;
      }
    };

    const io = new IntersectionObserver(
      ([entry]) => {
        isVisible = entry.isIntersecting;
        isVisible ? tryStart() : tryStop();
      },
      { threshold: 0 }
    );
    io.observe(container);

    const onVisibility = () => {
      isPageVisible = !document.hidden;
      isPageVisible ? tryStart() : tryStop();
    };
    document.addEventListener("visibilitychange", onVisibility);

    // If the GPU drops the context, fall back rather than showing a dead canvas.
    const onContextLost = (e: Event) => {
      e.preventDefault();
      tryStop();
      setMode("css-animated");
    };
    canvas.addEventListener("webglcontextlost", onContextLost);

    tryStart();

    return () => {
      disposed = true;
      tryStop();
      ro.disconnect();
      io.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      canvas.removeEventListener("webglcontextlost", onContextLost);
      if (mouseInteraction) {
        canvas.removeEventListener("pointermove", onPointerMove);
        canvas.removeEventListener("pointerleave", onPointerLeave);
      }
      try {
        container.removeChild(canvas);
      } catch {
        /* already detached */
      }
      try {
        gl.getExtension("WEBGL_lose_context")?.loseContext();
      } catch {
        /* nothing to release */
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  if (mode !== "webgl") {
    // CSS fallback: same navy/blue tones, animated or static per motion pref.
    return (
      <div
        className={`gradient-waves-container gradient-waves-fallback ${
          mode === "css-static" ? "is-static" : ""
        } ${className}`.trim()}
        aria-hidden="true"
      />
    );
  }

  return (
    <div
      ref={containerRef}
      className={`gradient-waves-container ${className}`.trim()}
      aria-hidden="true"
    />
  );
}
