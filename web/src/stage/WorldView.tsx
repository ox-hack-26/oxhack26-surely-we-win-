// "World": the opening view. One eye-screening AI, validated in California, used at ten clinics
// around the world. Each clinic is a pin on the globe with a callout (its code and the catch rate
// ClinicDrift believes), ringed in aqua by drift, with a line back to where the AI was validated
// that brightens as its scans drift away. An alarm turns the land around the clinic red and sends
// out thin ripples. The camera is fixed (no zoom); dragging turns the globe, which otherwise turns
// slowly on its own, swings to the next alarm while the replay plays, and holds still while
// someone points at a clinic.
import { Html } from "@react-three/drei";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import gsap from "gsap";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { Clinic } from "../data/types";
import { num, pct, REASON_LABEL } from "../format";
import { getState, reducedMotion, setState, useBundle, useDecisions, useStore } from "../store";
import { storySteps } from "../ui/storySteps";
import { easeInOutCubic, token } from "./layout";
import { faceTurn, GLOBE_SHOTS, latLonToVector, placeOf, VALIDATION } from "./places";

export const GLOBE_RADIUS = 4;
const R = GLOBE_RADIUS;
const DATA_SECONDS = 0.6;
const UI_SECONDS = 0.2;
const PULSE_SECONDS = 2.4;
const IDLE_SPIN = 0.045; // radians a second: one turn in about two and a half minutes
const ALARM_REACH = (9 * Math.PI) / 180; // land within 9 degrees of an alarmed clinic turns red
const UP = new THREE.Vector3(0, 1, 0);

let dot: THREE.Texture | null = null;
function dotTexture(): THREE.Texture {
  if (dot) return dot;
  const size = 32;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#fff";
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
  ctx.fill();
  dot = new THREE.CanvasTexture(canvas);
  return dot;
}

export function WorldView() {
  const bundle = useBundle();
  const spin = useRef<THREE.Group>(null);
  const tilt = useRef<THREE.Group>(null);
  const validation = useMemo(() => latLonToVector(VALIDATION.lat, VALIDATION.lon, R), []);
  const ink = token("--ink");

  return (
    <group ref={tilt}>
      <group ref={spin}>
        {/* The globe: an opaque dark ball. It also stops pointing from reaching pins behind it. */}
        <mesh onPointerMove={(e) => e.stopPropagation()} onPointerOver={(e) => e.stopPropagation()}>
          <sphereGeometry args={[R, 96, 64]} />
          <meshStandardMaterial color={token("--panel")} roughness={0.8} metalness={0.15} envMapIntensity={0.45} />
        </mesh>
        <Graticule />
        <Land />
        <Rim />

        {/* Where the AI was validated. */}
        <group position={validation} quaternion={new THREE.Quaternion().setFromUnitVectors(UP, validation.clone().normalize())}>
          <mesh position={[0, 0.006, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[0.1, 0.135, 48]} />
            <meshBasicMaterial color={ink} />
          </mesh>
          <mesh position={[0, 0.008, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <circleGeometry args={[0.04, 24]} />
            <meshBasicMaterial color={ink} />
          </mesh>
          <Callout height={0.9} priority={1} className="callout callout--home">
            <span className="callout__id">Validated here</span>
            <span className="callout__sub">{VALIDATION.city}</span>
          </Callout>
        </group>

        {bundle.clinics.map((clinic, i) => (
          <WorldClinic key={clinic.clinic_id} clinic={clinic} validation={validation} stem={0.45 + (i % 3) * 0.32} />
        ))}
      </group>
      <GlobeRig spin={spin} tilt={tilt} />
      <Declutter />
    </group>
  );
}

/** Faint lines of latitude and longitude every 30 degrees: the globe reads as an instrument. */
function Graticule() {
  const geometry = useMemo(() => {
    const pts: THREE.Vector3[] = [];
    const r = R * 1.001;
    for (let lat = -60; lat <= 60; lat += 30)
      for (let lon = -180; lon < 180; lon += 3) pts.push(latLonToVector(lat, lon, r), latLonToVector(lat, lon + 3, r));
    for (let lon = -180; lon < 180; lon += 30)
      for (let lat = -84; lat < 84; lat += 3) pts.push(latLonToVector(lat, lon, r), latLonToVector(lat + 3, lon, r));
    return new THREE.BufferGeometry().setFromPoints(pts);
  }, []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={token("--ink")} transparent opacity={0.07} depthWrite={false} />
    </lineSegments>
  );
}

/** The continents in dots. Dots near a clinic on alarm turn red, so the trouble reads as a place. */
function Land() {
  const bundle = useBundle();
  const week = useStore((s) => s.week);
  const decisions = useDecisions();
  const [land, setLand] = useState<{ pos: Float32Array; unit: Float32Array } | null>(null);

  useEffect(() => {
    let live = true;
    fetch(`${import.meta.env.BASE_URL}data/land.json`)
      .then((r) => r.json() as Promise<number[]>)
      .then((pairs) => {
        if (!live) return;
        const n = pairs.length / 2;
        const pos = new Float32Array(n * 3);
        const unit = new Float32Array(n * 3);
        for (let i = 0; i < n; i++) {
          const v = latLonToVector(pairs[2 * i], pairs[2 * i + 1], 1);
          unit.set([v.x, v.y, v.z], i * 3);
          pos.set([v.x * R * 1.002, v.y * R * 1.002, v.z * R * 1.002], i * 3);
        }
        setLand({ pos, unit });
      })
      .catch(() => undefined); // the globe still works without its map
    return () => {
      live = false;
    };
  }, []);

  // Which places are on alarm this week, recomputed only when that set changes.
  const alarmed = bundle.clinics
    .filter((c) => decisions[c.clinic_id]?.weeks[week - 1]?.alarm)
    .map((c) => c.clinic_id)
    .join(",");
  // The land within reach of an alarmed clinic, drawn again on top in red, slightly larger.
  const hot = useMemo(() => {
    if (!land || !alarmed) return null;
    const centres = alarmed.split(",").map((id) => {
      const c = bundle.clinics.find((k) => k.clinic_id === id)!;
      const p = placeOf(c.clinic_id, c.country);
      return latLonToVector(p.lat, p.lon, 1);
    });
    const cosReach = Math.cos(ALARM_REACH);
    const out: number[] = [];
    for (let i = 0; i < land.unit.length / 3; i++) {
      const x = land.unit[3 * i];
      const y = land.unit[3 * i + 1];
      const z = land.unit[3 * i + 2];
      if (centres.some((k) => x * k.x + y * k.y + z * k.z > cosReach)) out.push(x * R * 1.003, y * R * 1.003, z * R * 1.003);
    }
    return new Float32Array(out);
  }, [land, alarmed, bundle]);

  if (!land) return null;
  return (
    <>
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[land.pos, 3]} />
        </bufferGeometry>
        <pointsMaterial map={dotTexture()} color={token("--ink-2")} size={0.15} sizeAttenuation transparent opacity={0.55} alphaTest={0.3} depthWrite={false} />
      </points>
      {hot && hot.length > 0 && (
        <points key={alarmed}>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[hot, 3]} />
          </bufferGeometry>
          <pointsMaterial map={dotTexture()} color={token("--alarm")} size={0.19} sizeAttenuation transparent opacity={0.95} alphaTest={0.3} depthWrite={false} />
        </points>
      )}
    </>
  );
}

/** A faint neutral rim of light round the globe's edge, so the dark ball reads against the dark
 *  ground. Lighting, not decoration: it carries no data and does not move. */
function Rim() {
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        uniforms: { colour: { value: new THREE.Color(token("--ink-2")) } },
        vertexShader: `varying vec3 vNormal; varying vec3 vView;
          void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); vNormal = normalize(normalMatrix * normal); vView = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`,
        fragmentShader: `uniform vec3 colour; varying vec3 vNormal; varying vec3 vView;
          void main() { float edge = 1.0 - abs(dot(vNormal, vView)); gl_FragColor = vec4(colour, pow(edge, 3.0) * 0.55); }`,
        transparent: true,
        depthWrite: false,
      }),
    [],
  );
  useEffect(() => () => material.dispose(), [material]);
  return (
    <mesh material={material}>
      <sphereGeometry args={[R * 1.006, 96, 64]} />
    </mesh>
  );
}

/** Turns the globe: to the story's shot, the opened clinic, or (while playing) the next alarm.
 *  Otherwise it turns slowly on its own, and holds still while someone points at a clinic. */
function GlobeRig({ spin, tilt }: { spin: React.RefObject<THREE.Group>; tilt: React.RefObject<THREE.Group> }) {
  const bundle = useBundle();
  const decisions = useDecisions();
  const week = useStore((s) => s.week);
  const playing = useStore((s) => s.playing);
  const selected = useStore((s) => s.selected);
  const story = useStore((s) => s.story);
  const turn = useRef({ spin: faceTurn(GLOBE_SHOTS.americas.lat, GLOBE_SHOTS.americas.lon).spin, tilt: 0.35 });
  const placed = useRef(false);
  const tween = useRef<gsap.core.Tween | null>(null);
  const still = useMemo(() => reducedMotion(), []);
  const gl = useThree((s) => s.gl);
  // Dragging turns the globe itself (the camera stays put, and there is no zoom). The slow
  // idle turn waits a few seconds after a drag before it resumes.
  const drag = useRef<{ x: number; y: number } | null>(null);
  const lastDrag = useRef(0);
  useEffect(() => {
    const el = gl.domElement;
    el.style.cursor = "grab";
    const down = (e: PointerEvent) => {
      drag.current = { x: e.clientX, y: e.clientY };
      tween.current?.kill();
      el.style.cursor = "grabbing";
    };
    const move = (e: PointerEvent) => {
      if (!drag.current) return;
      const dx = e.clientX - drag.current.x;
      const dy = e.clientY - drag.current.y;
      drag.current = { x: e.clientX, y: e.clientY };
      turn.current.spin += dx * 0.006;
      turn.current.tilt = Math.max(-0.9, Math.min(1.1, turn.current.tilt + dy * 0.004));
      lastDrag.current = performance.now();
      if (Math.abs(dx) + Math.abs(dy) > 2 && !getState().orbited) setState({ orbited: true });
    };
    const up = () => {
      drag.current = null;
      el.style.cursor = "grab";
    };
    el.addEventListener("pointerdown", down);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      el.style.cursor = "";
      el.removeEventListener("pointerdown", down);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [gl]);

  useEffect(() => {
    let to: { lat: number; lon: number } | null = null;
    const step = story !== null ? storySteps(bundle)[story] : null;
    if (step && step.mode === "world") to = GLOBE_SHOTS[step.shot] ?? GLOBE_SHOTS.americas;
    else if (selected) {
      const c = bundle.clinics.find((k) => k.clinic_id === selected);
      if (c) to = placeOf(c.clinic_id, c.country);
    } else if (playing) {
      // Follow the alarms: face the clinics whose alarm starts this week.
      const starting = bundle.clinics.filter((c) => decisions[c.clinic_id]?.firstAlarm === week);
      if (starting.length) {
        const places = starting.map((c) => placeOf(c.clinic_id, c.country));
        to = { lat: places.reduce((s, p) => s + p.lat, 0) / places.length, lon: places.reduce((s, p) => s + p.lon, 0) / places.length };
      }
    } else if (!placed.current) to = GLOBE_SHOTS.americas;
    if (!to) return;
    const goal = faceTurn(to.lat, to.lon);
    // Take the short way round.
    const now = turn.current.spin;
    let target = goal.spin;
    while (target - now > Math.PI) target -= 2 * Math.PI;
    while (target - now < -Math.PI) target += 2 * Math.PI;
    const tiltTo = Math.max(-0.2, Math.min(0.75, goal.tilt * 0.75));
    const seconds = !placed.current || still ? 0 : 1.2;
    placed.current = true;
    tween.current?.kill();
    tween.current = gsap.to(turn.current, { spin: target, tilt: tiltTo, duration: seconds, ease: "power3.inOut" });
  }, [bundle, decisions, week, playing, selected, story, still]);
  useEffect(() => () => void tween.current?.kill(), []);

  useFrame((_, delta) => {
    const { hovered, selected: open, story: telling, playing: running } = getState();
    const resting = !drag.current && performance.now() - lastDrag.current > 3000;
    const idle = resting && !still && !hovered && !open && telling === null && !running && !tween.current?.isActive();
    if (idle) turn.current.spin += IDLE_SPIN * Math.min(delta, 0.1);
    if (spin.current) spin.current.rotation.y = turn.current.spin;
    if (tilt.current) tilt.current.rotation.x = turn.current.tilt;
  });

  return null;
}

interface CalloutEntry {
  el: HTMLDivElement;
  x: number; // screen position of the line's tip, in CSS pixels
  y: number;
  visible: boolean;
  priority: number; // alarms and focus win the free space
}
const callouts = new Set<CalloutEntry>();

/** Slides overlapping callouts apart vertically, highest priority first. It works from the
 *  positions the callouts reported last frame, a lag nobody can see. */
function Declutter() {
  useFrame(({ gl }) => {
    // The panels over the stage count as taken space, so callouts steer clear of them.
    const stage = gl.domElement.getBoundingClientRect();
    const placed: { l: number; r: number; t: number; b: number }[] = [...document.querySelectorAll(".world-bars, .legend, .story")].map((el) => {
      const r = el.getBoundingClientRect();
      return { l: r.left - stage.left - 4, r: r.right - stage.left + 4, t: r.top - stage.top - 4, b: r.bottom - stage.top + 4 };
    });
    const list = [...callouts].filter((c) => c.visible).sort((a, b) => b.priority - a.priority || a.y - b.y);
    for (const c of list) {
      const w = c.el.offsetWidth;
      const h = c.el.offsetHeight + 4;
      const l = c.el.dataset.side === "left" ? c.x - 6 - w : c.x + 6;
      let dy = 0;
      for (const step of [0, 1, -1, 2, -2, 3, -3, 4, -4]) {
        const t = c.y - h / 2 + step * h;
        if (!placed.some((p) => l < p.r && l + w > p.l && t < p.b && t + h > p.t)) {
          dy = step * h;
          break;
        }
      }
      placed.push({ l, r: l + w, t: c.y - h / 2 + dy, b: c.y + h / 2 + dy });
      c.el.style.setProperty("--dy", `${dy}px`);
    }
  });
  return null;
}

/** A label on a thin leader line, standing off the globe's surface. It fades when its point
 *  turns to the far side, and sits on whichever side of the line points away from the globe. */
function Callout({ height, side, priority = 0, className, children }: { height: number; side?: "left" | "right"; priority?: number; className: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const tip = useRef<THREE.Group>(null);
  const base = useRef<THREE.Group>(null);
  const line = useMemo(() => {
    const g = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0.02, 0), new THREE.Vector3(0, height, 0)]);
    return new THREE.Line(g, new THREE.LineBasicMaterial({ color: token("--ink-2"), transparent: true, opacity: 0.55, depthWrite: false }));
  }, [height]);
  useEffect(
    () => () => {
      line.geometry.dispose();
      (line.material as THREE.Material).dispose();
    },
    [line],
  );
  const p = useMemo(() => new THREE.Vector3(), []);
  const q = useMemo(() => new THREE.Vector3(), []);
  const n = useMemo(() => new THREE.Vector3(), []);
  const centre = useMemo(() => new THREE.Vector3(), []);
  // Html renders its children in a root of its own, so the element appears a frame or two after
  // mount: the callout joins the declutter list from the render loop once it exists.
  const entry = useRef<CalloutEntry | null>(null);
  useEffect(
    () => () => {
      if (entry.current) callouts.delete(entry.current);
    },
    [],
  );
  useFrame(({ camera, size }) => {
    if (!base.current || !tip.current || !ref.current) return;
    if (!entry.current || entry.current.el !== ref.current) {
      if (entry.current) callouts.delete(entry.current);
      entry.current = { el: ref.current, x: 0, y: 0, visible: false, priority };
      callouts.add(entry.current);
    }
    entry.current.priority = priority;
    base.current.getWorldPosition(p);
    const facing = n.copy(p).normalize().dot(q.copy(camera.position).sub(p).normalize());
    const visible = facing > 0.3;
    ref.current.style.opacity = visible ? "1" : "0";
    (line.material as THREE.LineBasicMaterial).opacity = visible ? 0.55 : 0;
    // Left or right of the line: away from the globe's centre on screen.
    tip.current.getWorldPosition(q).project(camera);
    let onLeft = side ? side === "left" : q.x < centre.set(0, 0, 0).project(camera).x;
    const sx = ((q.x + 1) / 2) * size.width;
    const sy = ((1 - q.y) / 2) * size.height;
    // Never off the stage: flip sides when the card would run past an edge.
    const w = ref.current.offsetWidth + 10;
    if (onLeft && sx - w < 0) onLeft = false;
    else if (!onLeft && sx + w > size.width) onLeft = true;
    ref.current.dataset.side = onLeft ? "left" : "right";
    if (entry.current) {
      entry.current.x = sx;
      entry.current.y = sy;
      entry.current.visible = visible;
    }
  });
  return (
    <group ref={base}>
      <primitive object={line} />
      <group ref={tip} position={[0, height, 0]}>
        <Html zIndexRange={[6, 0]} className="callout-anchor">
          <div ref={ref} className={className} data-side="right">
            {children}
          </div>
        </Html>
      </group>
    </group>
  );
}

function WorldClinic({ clinic, validation, stem }: { clinic: Clinic; validation: THREE.Vector3; stem: number }) {
  const week = useStore((s) => s.week);
  const hovered = useStore((s) => s.hovered === clinic.clinic_id);
  const selected = useStore((s) => s.selected === clinic.clinic_id);
  const dimmed = useStore((s) => {
    const focus = s.hovered ?? s.selected;
    return focus !== null && focus !== clinic.clinic_id;
  });
  const decision = useDecisions()[clinic.clinic_id];
  const w = clinic.weeks[week - 1];
  const d = decision?.weeks[week - 1];
  const alarm = !!d?.alarm;
  const place = placeOf(clinic.clinic_id, clinic.country);

  const geo = useMemo(() => {
    const at = latLonToVector(place.lat, place.lon, R);
    const normal = at.clone().normalize();
    // The line home: lifted higher the further away the clinic is.
    const angle = validation.angleTo(at);
    const mid = validation.clone().add(at).multiplyScalar(0.5).normalize().multiplyScalar(R * (1.04 + 0.32 * (angle / Math.PI)));
    const curve = new THREE.QuadraticBezierCurve3(validation.clone().normalize().multiplyScalar(R * 1.004), mid, normal.clone().multiplyScalar(R * 1.004));
    const arc = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(curve.getPoints(64)),
      new THREE.LineBasicMaterial({ color: token("--drift"), transparent: true, opacity: 0.2, depthWrite: false }),
    );
    return { at, quaternion: new THREE.Quaternion().setFromUnitVectors(UP, normal), arc };
  }, [place.lat, place.lon, validation]);
  useEffect(
    () => () => {
      geo.arc.geometry.dispose();
      (geo.arc.material as THREE.Material).dispose();
    },
    [geo],
  );

  const colours = useMemo(
    () => ({
      ink: new THREE.Color(token("--ink")),
      alarm: new THREE.Color(token("--alarm")),
    }),
    [],
  );

  // Tweens: data 600ms ease-in-out, focus 200ms ease-out.
  const target = {
    drift: Math.min(1, Math.max(0, (w.drift_auc - 0.5) / 0.5)),
    alarm: alarm ? 1 : 0,
    dim: dimmed ? 1 : 0,
  };
  type K = keyof typeof target;
  const keys = Object.keys(target) as K[];
  const cur = useRef({ ...target });
  const from = useRef({ ...target });
  const to = useRef({ ...target });
  const t0 = useRef<Record<K, number>>({ drift: 0, alarm: 0, dim: 0 });
  const signature = keys.map((k) => target[k].toFixed(4)).join("|");
  useEffect(() => {
    const now = performance.now() / 1000;
    for (const k of keys) {
      if (to.current[k] !== target[k]) {
        from.current[k] = cur.current[k];
        to.current[k] = target[k];
        t0.current[k] = now;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  const pinMat = useRef<THREE.MeshBasicMaterial>(null);
  const ring = useRef<THREE.Mesh>(null);
  const ripples = useRef<(THREE.Mesh | null)[]>([]);
  const still = useMemo(() => reducedMotion(), []);

  useFrame(() => {
    const now = performance.now() / 1000;
    const v = cur.current;
    for (const k of keys) {
      const seconds = still ? 0 : k === "dim" ? UI_SECONDS : DATA_SECONDS;
      const p = seconds === 0 ? 1 : Math.min(1, (now - t0.current[k]) / seconds);
      const e = k === "dim" ? 1 - Math.pow(1 - p, 3) : easeInOutCubic(p);
      v[k] = from.current[k] + (to.current[k] - from.current[k]) * e;
    }
    const fade = 1 - 0.7 * v.dim;
    if (pinMat.current) {
      pinMat.current.color.copy(colours.ink).lerp(colours.alarm, v.alarm);
      pinMat.current.opacity = fade;
    }
    if (ring.current) {
      const s = 1 + 1.1 * v.drift;
      ring.current.scale.set(s, s, 1);
      (ring.current.material as THREE.MeshBasicMaterial).opacity = (0.3 + 0.6 * v.drift) * fade;
    }
    (geo.arc.material as THREE.LineBasicMaterial).opacity = (0.06 + 0.7 * v.drift) * fade;
    // Two thin ripples, half a period apart, while the alarm is on.
    ripples.current.forEach((m, i) => {
      if (!m) return;
      const mat = m.material as THREE.MeshBasicMaterial;
      m.visible = v.alarm > 0.01;
      const phase = still ? 0.35 + 0.3 * i : ((now / PULSE_SECONDS + i / 2) % 1);
      const s = 1 + 4 * phase;
      m.scale.set(s, s, 1);
      mat.opacity = (still ? 0.5 : 0.8 * (1 - phase)) * v.alarm * fade;
    });
  });

  const onOver = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    setState({ hovered: clinic.clinic_id });
    document.body.style.cursor = "pointer";
  };
  const onOut = () => {
    setState((s) => (s.hovered === clinic.clinic_id ? { hovered: null } : {}));
    document.body.style.cursor = "";
  };
  const onClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    setState({ selected: clinic.clinic_id, story: null });
  };
  const tone = selected || hovered ? " is-focus" : dimmed ? " is-dim" : "";

  return (
    <>
      <primitive object={geo.arc} />
      <group position={geo.at} quaternion={geo.quaternion}>
        {/* Hit area: the pin and its leader line. */}
        <mesh position={[0, stem / 2, 0]} onPointerOver={onOver} onPointerOut={onOut} onClick={onClick}>
          <cylinderGeometry args={[0.22, 0.22, stem + 0.3, 12]} />
          <meshBasicMaterial transparent opacity={0} depthWrite={false} />
        </mesh>
        <mesh ref={ring} position={[0, 0.006, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.09, 0.105, 64]} />
          <meshBasicMaterial color={token("--drift")} transparent opacity={0.4} depthWrite={false} />
        </mesh>
        {[0, 1].map((i) => (
          <mesh key={i} ref={(m) => (ripples.current[i] = m)} position={[0, 0.007, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[0.1, 0.112, 64]} />
            <meshBasicMaterial color={colours.alarm} transparent opacity={0} depthWrite={false} />
          </mesh>
        ))}
        <mesh position={[0, 0.009, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[0.055, 32]} />
          <meshBasicMaterial ref={pinMat} color={colours.ink} transparent />
        </mesh>
        <Callout height={stem} priority={(selected || hovered ? 4 : 0) + (alarm ? 2 : 0)} className={`callout${alarm ? " is-alarm" : ""}${tone}`}>
          <span className="callout__id">
            {alarm && <i className="status-dot status-dot--alarm status-dot--still" aria-hidden="true" />}
            {clinic.clinic_id}
          </span>
          <span className="callout__value num">{pct(w.catch_rate)}</span>
        </Callout>
        {hovered && (
          <Html position={[0, stem + 0.2, 0]} center zIndexRange={[30, 20]} style={{ transform: "translateY(-110%)" }}>
            <div className="tooltip" role="tooltip">
              <div className="tooltip__title">
                {clinic.clinic_id} <span className="tooltip__sub">{place.city}</span>
              </div>
              <dl className="tooltip__rows">
                <div><dt><i className="key key--belief" />ClinicDrift</dt><dd className="num">{pct(w.catch_rate)} <span className="tooltip__sub num">{pct(w.catch_low)}–{pct(w.catch_high)}</span></dd></div>
                <div><dt><i className="key key--estimate" />AI's own estimate</dt><dd className="num">{pct(w.est_sensitivity)}</dd></div>
                <div><dt><i className="key key--drift" />Drift</dt><dd className="num">{num(w.drift_auc)}</dd></div>
                {alarm && d?.reason && <div><dt>Status</dt><dd>{REASON_LABEL[d.reason]}</dd></div>}
              </dl>
            </div>
          </Html>
        )}
      </group>
    </>
  );
}
