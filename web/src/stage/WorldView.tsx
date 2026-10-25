// "World": the opening view. One eye-screening AI, validated in California, used at ten clinics
// around the world. Each clinic is a small column standing on the globe (its height the catch rate
// ClinicDrift believes), ringed in aqua by drift, with a line back to where the AI was validated
// that brightens as the clinic's scans drift away. Alarms glow red. While the replay plays, the
// globe turns to wherever the next alarm fires; it never turns on its own otherwise.
import { Html } from "@react-three/drei";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import gsap from "gsap";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { Clinic } from "../data/types";
import { pct, num, REASON_LABEL } from "../format";
import { reducedMotion, setState, useBundle, useDecisions, useStore } from "../store";
import { storySteps } from "../ui/storySteps";
import { easeInOutCubic, glowTexture, token } from "./layout";
import { faceTurn, GLOBE_SHOTS, latLonToVector, placeOf, VALIDATION } from "./places";

export const GLOBE_RADIUS = 4;
const R = GLOBE_RADIUS;
const MARKER_HEIGHT = 1.0; // world units for a 100% catch rate
const DATA_SECONDS = 0.6;
const UI_SECONDS = 0.2;
const PULSE_SECONDS = 2.4;
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
  const [land, setLand] = useState<Float32Array | null>(null);

  useEffect(() => {
    let live = true;
    fetch(`${import.meta.env.BASE_URL}data/land.json`)
      .then((r) => r.json() as Promise<number[]>)
      .then((pairs) => {
        if (!live) return;
        const pos = new Float32Array((pairs.length / 2) * 3);
        for (let i = 0; i < pairs.length; i += 2) {
          const v = latLonToVector(pairs[i], pairs[i + 1], R * 1.002);
          pos.set([v.x, v.y, v.z], (i / 2) * 3);
        }
        setLand(pos);
      })
      .catch(() => undefined); // the globe still works without its map
    return () => {
      live = false;
    };
  }, []);

  const ink = token("--ink");
  const validation = useMemo(() => latLonToVector(VALIDATION.lat, VALIDATION.lon, R), []);

  return (
    <group ref={tilt}>
      <group ref={spin}>
        {/* The globe: an opaque dark ball. It also stops pointing from reaching markers behind it. */}
        <mesh onPointerMove={(e) => e.stopPropagation()} onPointerOver={(e) => e.stopPropagation()}>
          <sphereGeometry args={[R, 96, 64]} />
          <meshStandardMaterial color={token("--panel")} roughness={0.8} metalness={0.15} envMapIntensity={0.45} />
        </mesh>
        {land && (
          <points>
            <bufferGeometry>
              <bufferAttribute attach="attributes-position" args={[land, 3]} />
            </bufferGeometry>
            <pointsMaterial map={dotTexture()} color={token("--ink-2")} size={0.15} sizeAttenuation transparent opacity={0.5} alphaTest={0.3} depthWrite={false} />
          </points>
        )}

        <Rim />

        {/* Where the AI was validated. */}
        <group position={validation} quaternion={new THREE.Quaternion().setFromUnitVectors(UP, validation.clone().normalize())}>
          <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[0.12, 0.17, 40]} />
            <meshBasicMaterial color={ink} />
          </mesh>
          <FacingLabel className="globe-label globe-label--home">
            Validated here
            <span className="globe-label__city">{VALIDATION.city}</span>
          </FacingLabel>
        </group>

        {bundle.clinics.map((clinic) => (
          <WorldClinic key={clinic.clinic_id} clinic={clinic} validation={validation} />
        ))}
      </group>
      <GlobeRig spin={spin} tilt={tilt} />
    </group>
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
        side: THREE.FrontSide,
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

/** Turns the globe: to the story's shot, the opened clinic, or (while playing) the next alarm. */
function GlobeRig({ spin, tilt }: { spin: React.RefObject<THREE.Group>; tilt: React.RefObject<THREE.Group> }) {
  const bundle = useBundle();
  const decisions = useDecisions();
  const week = useStore((s) => s.week);
  const playing = useStore((s) => s.playing);
  const selected = useStore((s) => s.selected);
  const story = useStore((s) => s.story);
  const turn = useRef({ spin: faceTurn(GLOBE_SHOTS.americas.lat, GLOBE_SHOTS.americas.lon).spin, tilt: 0.35 });
  const placed = useRef(false);

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
    const seconds = !placed.current || reducedMotion() ? 0 : 1.2;
    placed.current = true;
    const tw = gsap.to(turn.current, { spin: target, tilt: tiltTo, duration: seconds, ease: "power3.inOut" });
    return () => void tw.kill();
  }, [bundle, decisions, week, playing, selected, story]);

  useFrame(() => {
    if (spin.current) spin.current.rotation.y = turn.current.spin;
    if (tilt.current) tilt.current.rotation.x = turn.current.tilt;
  });

  return null;
}

/** A label that fades out when its point turns to the far side of the globe. */
function FacingLabel({ className, children }: { className: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const group = useRef<THREE.Group>(null);
  const p = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ camera }) => {
    if (!group.current || !ref.current) return;
    group.current.getWorldPosition(p);
    const facing = p.clone().normalize().dot(camera.position.clone().sub(p).normalize());
    const visible = facing > 0.15;
    ref.current.style.opacity = visible ? "1" : "0";
  });
  return (
    <group ref={group}>
      <Html center zIndexRange={[5, 0]} className="stage-label">
        <div ref={ref} className={className}>
          {children}
        </div>
      </Html>
    </group>
  );
}

function WorldClinic({ clinic, validation }: { clinic: Clinic; validation: THREE.Vector3 }) {
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
      belief: new THREE.Color(token("--belief")),
      drift: new THREE.Color(token("--drift")),
      alarm: new THREE.Color(token("--alarm")).multiplyScalar(1.15),
      alarmFlat: new THREE.Color(token("--alarm")),
      ink: new THREE.Color(token("--ink")),
      recede: new THREE.Color(token("--panel")),
    }),
    [],
  );

  // Tweens: data 600ms ease-in-out, focus 200ms ease-out.
  const target = {
    belief: w.catch_rate,
    drift: Math.min(1, Math.max(0, (w.drift_auc - 0.5) / 0.5)),
    alarm: alarm ? 1 : 0,
    dim: dimmed ? 1 : 0,
  };
  type K = keyof typeof target;
  const keys = Object.keys(target) as K[];
  const cur = useRef({ ...target });
  const from = useRef({ ...target });
  const to = useRef({ ...target });
  const t0 = useRef<Record<K, number>>({ belief: 0, drift: 0, alarm: 0, dim: 0 });
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

  const column = useRef<THREE.Mesh>(null);
  const columnMat = useRef<THREE.MeshStandardMaterial>(null);
  const ring = useRef<THREE.Mesh>(null);
  const beacon = useRef<THREE.Group>(null);
  const okRing = useRef<THREE.Mesh>(null);
  const pulse = useRef<THREE.Mesh>(null);
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
    const fade = 1 - 0.75 * v.dim;
    const h = Math.max(0.02, v.belief * MARKER_HEIGHT);
    if (column.current) {
      column.current.scale.y = h;
      column.current.position.y = h / 2;
    }
    if (columnMat.current) {
      columnMat.current.color.copy(colours.belief).lerp(colours.recede, 0.7 * v.dim);
      columnMat.current.emissive.copy(columnMat.current.color);
    }
    if (ring.current) {
      const s = 1 + 0.6 * v.drift;
      ring.current.scale.set(s, s, 1);
      (ring.current.material as THREE.MeshBasicMaterial).opacity = (0.25 + 0.65 * v.drift) * fade;
    }
    (geo.arc.material as THREE.LineBasicMaterial).opacity = (0.08 + 0.72 * v.drift) * fade;
    if (beacon.current) {
      beacon.current.position.y = h + 0.22;
      beacon.current.scale.setScalar(Math.max(0.001, v.alarm));
      beacon.current.visible = v.alarm > 0.01;
    }
    if (okRing.current) {
      okRing.current.position.y = h + 0.18;
      (okRing.current.material as THREE.MeshBasicMaterial).opacity = 0.6 * (1 - v.alarm) * fade;
      okRing.current.visible = v.alarm < 0.99;
    }
    if (pulse.current) {
      const mat = pulse.current.material as THREE.MeshBasicMaterial;
      pulse.current.visible = v.alarm > 0.01;
      const phase = still ? 0.4 : (now % PULSE_SECONDS) / PULSE_SECONDS;
      const s = 1 + 1.4 * (1 - Math.pow(1 - phase, 2));
      pulse.current.scale.set(s, s, 1);
      mat.opacity = (still ? 0.45 : 0.7 * (1 - phase)) * v.alarm * fade;
    }
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
        <mesh position={[0, 0.5, 0]} onPointerOver={onOver} onPointerOut={onOut} onClick={onClick}>
          <cylinderGeometry args={[0.3, 0.3, 1.9, 12]} />
          <meshBasicMaterial transparent opacity={0} depthWrite={false} />
        </mesh>
        <mesh ref={ring} position={[0, 0.012, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.13, 0.18, 48]} />
          <meshBasicMaterial color={colours.drift} transparent opacity={0.3} depthWrite={false} />
        </mesh>
        <mesh ref={pulse} position={[0, 0.016, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.16, 0.2, 48]} />
          <meshBasicMaterial color={colours.alarmFlat} transparent opacity={0} depthWrite={false} />
        </mesh>
        <mesh ref={column}>
          <cylinderGeometry args={[0.05, 0.05, 1, 20]} />
          <meshStandardMaterial ref={columnMat} color={colours.belief} emissive={colours.belief} emissiveIntensity={0.3} roughness={0.35} metalness={0.1} />
        </mesh>
        <group ref={beacon}>
          <mesh>
            <sphereGeometry args={[0.085, 20, 14]} />
            <meshBasicMaterial color={colours.alarm} toneMapped={false} />
          </mesh>
          <sprite scale={[0.75, 0.75, 1]}>
            <spriteMaterial map={glowTexture()} color={colours.alarmFlat} transparent opacity={0.85} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
          </sprite>
        </group>
        <mesh ref={okRing} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.05, 0.075, 28]} />
          <meshBasicMaterial color={colours.ink} transparent opacity={0.6} side={THREE.DoubleSide} />
        </mesh>
        {/* Names only where they matter (alarms, focus), so nearby cities don't pile up. */}
        {(alarm || selected || hovered) && (
          <group position={[0, -0.05, 0]}>
            <FacingLabel className={`globe-label${tone}`}>
              <span className="globe-label__id">
                {alarm && <i className="status-dot status-dot--alarm status-dot--still" aria-hidden="true" />}
                {clinic.clinic_id}
              </span>
            </FacingLabel>
          </group>
        )}
        {hovered && (
          <Html position={[0, MARKER_HEIGHT + 0.6, 0]} center zIndexRange={[30, 20]}>
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
