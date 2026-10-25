// The opening view: an abstract dot-matrix sphere with the clinics on it. Each clinic sends a
// thin arc back to the California site the AI was validated on; the arc brightens with drift
// and turns red on an alarm. Locations are illustrative. Everything here is unlit and drawn
// in a handful of calls, so it stays smooth on integrated graphics.
import { Html, Line } from "@react-three/drei";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { REASON_LABEL } from "../format";
import { getState, reducedMotion, setState, useBundle, useDecisions, useStore } from "../store";
import { glowTexture, token } from "./layout";

export const GLOBE_RADIUS = 3;
const R = GLOBE_RADIUS;
const DOTS = 4200;
const TILT = 0.38; // the north pole leans toward you, so arcs over the top stay in view

/** The site the AI was validated on (EyePACS, California). */
const HOME_SITE: [number, number] = [37.8, -122.3];

/** Illustrative positions, near where each dataset comes from. */
const PLACES: Record<string, [number, number]> = {
  "US-EYE-01": [34.1, -118.2],
  "US-EYE-02": [36.7, -119.8],
  "US-WEAR-01": [33.4, -112.1],
  "US-UPD-01": [39.7, -105.0],
  "SW-MES-01": [41.9, -87.6],
  "SW-APT-01": [33.7, -84.4],
  "FR-MES-01": [48.4, -4.5],
  "IN-APT-01": [9.9, 78.1],
  "IN-APT-02": [13.1, 80.3],
  "IN-IDR-01": [19.1, 77.3],
};

function toVec(lat: number, lon: number, r = R): THREE.Vector3 {
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lon + 180);
  return new THREE.Vector3(-r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta));
}

/** The spin that brings a longitude to face the camera. */
const yawFor = (lon: number) => THREE.MathUtils.degToRad(-lon - 90);

/** A great-circle arc lifted off the surface, higher the farther it goes. */
function arc(from: [number, number], to: [number, number], segments = 64): THREE.Vector3[] {
  const a = toVec(...from, 1);
  const b = toVec(...to, 1);
  const angle = a.angleTo(b);
  const lift = 0.03 + angle * 0.07;
  const out: THREE.Vector3[] = [];
  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    const p = new THREE.Vector3().copy(a).lerp(b, t);
    if (angle > 1e-4) {
      // Slerp: the straight lerp cuts through the sphere.
      const s = Math.sin(angle);
      p.copy(a).multiplyScalar(Math.sin((1 - t) * angle) / s).addScaledVector(b, Math.sin(t * angle) / s);
    }
    out.push(p.normalize().multiplyScalar(R * (1.004 + lift * Math.sin(Math.PI * t))));
  }
  return out;
}

const dotVertex = /* glsl */ `
  uniform float uSize;
  varying float vFacing;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vFacing = dot(normalize(normalMatrix * normalize(position)), normalize(-mv.xyz));
    gl_PointSize = uSize * (10.0 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }
`;
const dotFragment = /* glsl */ `
  uniform vec3 uColor;
  varying float vFacing;
  void main() {
    vec2 c = gl_PointCoord - 0.5;
    if (dot(c, c) > 0.25) discard;
    if (vFacing < 0.0) discard;
    // Dots fade toward the limb, so the sphere reads as round without any shading.
    float a = mix(0.10, 0.55, smoothstep(0.0, 0.9, vFacing));
    gl_FragColor = vec4(uColor, a);
  }
`;
const rimVertex = /* glsl */ `
  varying float vRim;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    // Seen from inside the shell: strongest where it meets the sphere, nothing at its outer edge.
    vRim = abs(dot(normalize(normalMatrix * normal), normalize(-mv.xyz)));
    gl_Position = projectionMatrix * mv;
  }
`;
const rimFragment = /* glsl */ `
  uniform vec3 uColor;
  uniform float uStrength;
  varying float vRim;
  void main() {
    gl_FragColor = vec4(uColor, pow(vRim, 4.0) * uStrength);
  }
`;

export function GlobeView() {
  const bundle = useBundle();
  const spin = useRef<THREE.Group>(null);
  const yaw = useRef(yawFor(-60));

  const colours = useMemo(
    () => ({
      ink: new THREE.Color(token("--ink-2")),
      body: new THREE.Color(token("--panel")),
      rim: new THREE.Color(token("--belief")),
      line: token("--ink"),
    }),
    [],
  );

  const dots = useMemo(() => {
    // A Fibonacci lattice: evenly spaced, no seams at the poles.
    const pos = new Float32Array(DOTS * 3);
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < DOTS; i++) {
      const y = 1 - (i / (DOTS - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const t = golden * i;
      pos.set([Math.cos(t) * r * R * 1.002, y * R * 1.002, Math.sin(t) * r * R * 1.002], i * 3);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    return g;
  }, []);

  const graticule = useMemo(() => {
    const pts: number[] = [];
    const push = (a: THREE.Vector3, b: THREE.Vector3) => pts.push(a.x, a.y, a.z, b.x, b.y, b.z);
    for (let lat = -60; lat <= 60; lat += 30)
      for (let lon = -180; lon < 180; lon += 4) push(toVec(lat, lon, R * 1.001), toVec(lat, lon + 4, R * 1.001));
    for (let lon = -180; lon < 180; lon += 30)
      for (let lat = -88; lat < 88; lat += 4) push(toVec(lat, lon, R * 1.001), toVec(lat + 4, lon, R * 1.001));
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
    return g;
  }, []);

  const clinics = useMemo(
    () =>
      bundle.clinics
        .filter((c) => PLACES[c.clinic_id])
        .map((c) => ({ clinic: c, at: toVec(...PLACES[c.clinic_id], R * 1.006), arc: arc(PLACES[c.clinic_id], HOME_SITE) })),
    [bundle],
  );

  useFrame((_, delta) => {
    if (!spin.current) return;
    const { selected, hovered, week, story } = getState();
    const n = bundle.settings.n_weeks;
    const focus = selected ?? (story !== null ? null : hovered);
    // Play turns the world with the replay: the Americas first, then east toward India.
    const target = focus && PLACES[focus] ? yawFor(PLACES[focus][1]) : yawFor(-95 + ((week - 1) / Math.max(1, n - 1)) * 120);
    const k = reducedMotion() ? 1 : 1 - Math.exp(-delta * 2.2);
    let d = target - yaw.current;
    d = Math.atan2(Math.sin(d), Math.cos(d));
    yaw.current += d * k;
    spin.current.rotation.y = yaw.current;
  });

  return (
    <group rotation={[TILT, 0, -0.12]}>
      <group ref={spin}>
        {/* The body: hides the far side's dots, arcs and markers. */}
        <mesh renderOrder={0}>
          <sphereGeometry args={[R * 0.995, 64, 48]} />
          <meshBasicMaterial color={colours.body} />
        </mesh>
        <points geometry={dots}>
          <shaderMaterial
            vertexShader={dotVertex}
            fragmentShader={dotFragment}
            uniforms={{ uColor: { value: colours.ink }, uSize: { value: 2.6 } }}
            transparent
            depthWrite={false}
          />
        </points>
        <lineSegments geometry={graticule}>
          <lineBasicMaterial color={colours.line} transparent opacity={0.07} depthWrite={false} />
        </lineSegments>
        <HomeSite />
        {clinics.map((c) => (
          <ClinicMarker key={c.clinic.clinic_id} id={c.clinic.clinic_id} at={c.at} points={c.arc} />
        ))}
      </group>
      {/* A soft rim, drawn on a slightly larger shell so it sits outside the dots. */}
      <mesh scale={1.14}>
        <sphereGeometry args={[R, 64, 48]} />
        <shaderMaterial
          vertexShader={rimVertex}
          fragmentShader={rimFragment}
          uniforms={{ uColor: { value: colours.rim }, uStrength: { value: 0.45 } }}
          transparent
          side={THREE.BackSide}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
    </group>
  );
}

function HomeSite() {
  const at = useMemo(() => toVec(...HOME_SITE, R * 1.006), []);
  const ink = token("--ink");
  return (
    <group position={at}>
      <mesh>
        <sphereGeometry args={[0.06, 16, 12]} />
        <meshBasicMaterial color={ink} toneMapped={false} />
      </mesh>
      <sprite scale={[0.5, 0.5, 1]}>
        <spriteMaterial map={glowTexture()} color={ink} transparent opacity={0.35} blending={THREE.AdditiveBlending} depthWrite={false} />
      </sprite>
      <Html center className="stage-label" zIndexRange={[5, 0]} position={[0, 0.28, 0]}>
        <div className="stage-label__inner">Validation site</div>
      </Html>
    </group>
  );
}

function ClinicMarker({ id, at, points }: { id: string; at: THREE.Vector3; points: THREE.Vector3[] }) {
  const bundle = useBundle();
  const week = useStore((s) => s.week);
  const selected = useStore((s) => s.selected);
  const hovered = useStore((s) => s.hovered);
  const decisions = useDecisions();
  const clinic = bundle.clinics.find((c) => c.clinic_id === id)!;
  const w = clinic.weeks[week - 1];
  const d = decisions[id]?.weeks[week - 1];
  const alarm = !!d?.alarm;
  const focus = selected === id || hovered === id;
  const dim = (selected || hovered) && !focus;

  const glow = useRef<THREE.Sprite>(null);
  useFrame(({ clock }) => {
    if (!glow.current) return;
    const p = reducedMotion() ? 0.5 : (clock.elapsedTime % 2.4) / 2.4;
    glow.current.scale.setScalar(0.55 + 0.35 * Math.sin(Math.PI * p));
    (glow.current.material as THREE.SpriteMaterial).opacity = 0.9 - 0.4 * p;
  });

  // Drift between "trusted" and "untrusted" sets how bright the arc home is.
  const { drift_trusted: lo, drift_untrusted: hi } = bundle.settings;
  const drift = THREE.MathUtils.clamp((w.drift_auc - lo) / Math.max(1e-6, hi - lo), 0, 1);
  const arcColour = alarm ? token("--alarm") : token("--drift");
  const arcOpacity = (alarm ? 0.85 : 0.18 + 0.6 * drift) * (dim ? 0.35 : 1);
  const dot = alarm ? token("--alarm") : token("--ink");

  const over = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    setState({ hovered: id });
    document.body.style.cursor = "pointer";
  };
  const out = () => {
    setState((s) => (s.hovered === id ? { hovered: null } : {}));
    document.body.style.cursor = "";
  };
  const click = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    setState((s) => ({ selected: s.selected === id ? null : id, story: null }));
  };

  return (
    <>
      <Line points={points} color={arcColour} lineWidth={4} transparent opacity={arcOpacity * 0.18} depthWrite={false} />
      <Line points={points} color={arcColour} lineWidth={1.2} transparent opacity={arcOpacity} depthWrite={false} />
      <group position={at}>
        <mesh>
          <sphereGeometry args={[focus ? 0.075 : 0.055, 16, 12]} />
          <meshBasicMaterial color={dot} toneMapped={false} transparent opacity={dim ? 0.5 : 1} />
        </mesh>
        {alarm && (
          <sprite ref={glow} scale={[0.7, 0.7, 1]}>
            <spriteMaterial map={glowTexture()} color={token("--alarm")} transparent blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
          </sprite>
        )}
        {/* A larger invisible target: the dots are too small to point at. */}
        <mesh onPointerOver={over} onPointerOut={out} onClick={click}>
          <sphereGeometry args={[0.22, 8, 6]} />
          <meshBasicMaterial transparent opacity={0} depthWrite={false} />
        </mesh>
        {focus && (
          <Html center className="stage-label" zIndexRange={[6, 0]} position={[0, 0.3, 0]}>
            <div className="stage-label__inner is-focus stage-label__inner--row">
              {id}
              {alarm && d?.reason && <span className="stage-label__alarm">{REASON_LABEL[d.reason]}</span>}
            </div>
          </Html>
        )}
      </group>
    </>
  );
}
