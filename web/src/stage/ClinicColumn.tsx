// One clinic in the 3D view. Height is ClinicDrift's belief about the catch rate this week, the
// sleeve its 90% band, the amber ring the AI's own estimate, the aqua halo on the floor drift,
// the orange ring the real catch rate (hindsight only), and a red beacon an alarm.
import { Html } from "@react-three/drei";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { Clinic } from "../data/types";
import { realCatchRate } from "../data/model";
import { pct, num, REASON_LABEL } from "../format";
import { reducedMotion, setState, useDecisions, useStore } from "../store";
import { COLUMN_HEIGHT as H, easeInOutCubic, glowTexture, token } from "./layout";

const KEYS = ["belief", "low", "high", "est", "real", "realOn", "drift", "alarm", "lift", "dim"] as const;
type Key = (typeof KEYS)[number];
type Values = Record<Key, number>;
const UI_KEYS = new Set<Key>(["lift", "dim"]);

const DATA_SECONDS = 0.6;
const UI_SECONDS = 0.2;
const PULSE_SECONDS = 2.4;
const LABEL_OFFSET = 1.3;

interface Props {
  clinic: Clinic;
  position: [number, number, number];
}

export function ClinicColumn({ clinic, position }: Props) {
  const week = useStore((s) => s.week);
  const hindsight = useStore((s) => s.hindsight);
  const hovered = useStore((s) => s.hovered === clinic.clinic_id);
  const selected = useStore((s) => s.selected === clinic.clinic_id);
  // Pointing at (or opening) one clinic dims the rest, so its marks stand out.
  const dimmed = useStore((s) => {
    const focus = s.hovered ?? s.selected;
    return focus !== null && focus !== clinic.clinic_id;
  });
  const decision = useDecisions()[clinic.clinic_id];

  const w = clinic.weeks[Math.min(week, clinic.weeks.length) - 1];
  const d = decision?.weeks[w.week - 1];
  const real = realCatchRate(clinic, week);
  const alarm = !!d?.alarm;

  const colours = useMemo(
    () => ({
      belief: new THREE.Color(token("--belief")),
      estimate: new THREE.Color(token("--estimate")),
      grades: new THREE.Color(token("--grades")),
      drift: new THREE.Color(token("--drift")),
      alarm: new THREE.Color(token("--alarm")).multiplyScalar(1.15),
      alarmFlat: new THREE.Color(token("--alarm")),
      ink: new THREE.Color(token("--ink")),
      base: new THREE.Color(token("--panel-2")),
      baseLit: new THREE.Color(token("--panel-3")),
      recede: new THREE.Color(token("--panel")),
    }),
    [],
  );

  // Tweened values: data moves in 600ms, interface (hover, focus) in 200ms, no overshoot.
  const target: Values = {
    belief: w.catch_rate,
    low: w.catch_low,
    high: w.catch_high,
    est: w.est_sensitivity,
    real: real ?? w.catch_rate,
    realOn: hindsight && real !== null ? 1 : 0,
    drift: Math.min(1, Math.max(0, (w.drift_auc - 0.5) / 0.5)),
    alarm: alarm ? 1 : 0,
    lift: hovered || selected ? 1 : 0,
    dim: dimmed ? 1 : 0,
  };
  const current = useRef<Values>({ ...target });
  const from = useRef<Values>({ ...target });
  const to = useRef<Values>({ ...target });
  const started = useRef<Record<Key, number>>(Object.fromEntries(KEYS.map((k) => [k, 0])) as Record<Key, number>);
  const key = KEYS.map((k) => target[k].toFixed(4)).join("|");
  useEffect(() => {
    const now = performance.now() / 1000;
    for (const k of KEYS) {
      if (to.current[k] !== target[k]) {
        from.current[k] = current.current[k];
        to.current[k] = target[k];
        started.current[k] = now;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const column = useRef<THREE.Mesh>(null);
  const cap = useRef<THREE.Mesh>(null);
  const sleeve = useRef<THREE.Mesh>(null);
  const estRing = useRef<THREE.Mesh>(null);
  const realRing = useRef<THREE.Mesh>(null);
  const halo = useRef<THREE.Mesh>(null);
  const beacon = useRef<THREE.Group>(null);
  const okRing = useRef<THREE.Mesh>(null);
  const pulse = useRef<THREE.Mesh>(null);
  const label = useRef<THREE.Group>(null);
  const baseMat = useRef<THREE.MeshStandardMaterial>(null);
  const columnMat = useRef<THREE.MeshStandardMaterial>(null);
  const capMat = useRef<THREE.MeshStandardMaterial>(null);
  const still = useMemo(() => reducedMotion(), []);
  const scratch = useMemo(() => new THREE.Color(), []);

  useFrame(({ camera }) => {
    const now = performance.now() / 1000;
    const v = current.current;
    for (const k of KEYS) {
      const seconds = still ? 0 : UI_KEYS.has(k) ? UI_SECONDS : DATA_SECONDS;
      const p = seconds === 0 ? 1 : Math.min(1, (now - started.current[k]) / seconds);
      const e = UI_KEYS.has(k) ? 1 - Math.pow(1 - p, 3) : easeInOutCubic(p);
      v[k] = from.current[k] + (to.current[k] - from.current[k]) * e;
    }
    const fade = 1 - 0.75 * v.dim; // how much of each mark is left when another clinic has focus
    const h = Math.max(0.02, v.belief * H);
    if (column.current) {
      column.current.scale.y = h;
      column.current.position.y = h / 2;
    }
    if (columnMat.current) {
      columnMat.current.color.copy(colours.belief).lerp(colours.recede, 0.7 * v.dim);
      columnMat.current.emissive.copy(columnMat.current.color);
    }
    if (cap.current) cap.current.position.y = h + 0.002;
    if (capMat.current) {
      capMat.current.color.copy(colours.belief).lerp(colours.recede, 0.7 * v.dim);
      capMat.current.emissive.copy(capMat.current.color);
    }
    if (sleeve.current) {
      const lo = v.low * H;
      const span = Math.max(0.02, (v.high - v.low) * H);
      sleeve.current.scale.y = span;
      sleeve.current.position.y = lo + span / 2;
      (sleeve.current.material as THREE.MeshBasicMaterial).opacity = 0.2 * fade;
    }
    if (estRing.current) {
      estRing.current.position.y = v.est * H;
      (estRing.current.material as THREE.MeshBasicMaterial).color.copy(scratch.copy(colours.estimate).lerp(colours.recede, 0.7 * v.dim));
    }
    if (realRing.current) {
      realRing.current.position.y = v.real * H;
      (realRing.current.material as THREE.MeshBasicMaterial).opacity = v.realOn * fade;
      realRing.current.visible = v.realOn > 0.01;
    }
    if (halo.current) {
      const s = 1 + 0.35 * v.drift;
      halo.current.scale.set(s, s, 1);
      (halo.current.material as THREE.MeshBasicMaterial).opacity = (0.12 + 0.68 * v.drift) * fade;
    }
    if (beacon.current) {
      beacon.current.scale.setScalar(Math.max(0.001, v.alarm));
      beacon.current.visible = v.alarm > 0.01;
    }
    if (okRing.current) {
      (okRing.current.material as THREE.MeshBasicMaterial).opacity = 0.55 * (1 - v.alarm) * fade;
      okRing.current.visible = v.alarm < 0.99;
    }
    if (pulse.current) {
      const mat = pulse.current.material as THREE.MeshBasicMaterial;
      pulse.current.visible = v.alarm > 0.01;
      if (still) {
        pulse.current.scale.set(1.3, 1.3, 1);
        mat.opacity = 0.45 * v.alarm * fade;
      } else {
        const phase = (now % PULSE_SECONDS) / PULSE_SECONDS;
        const s = 1 + 0.75 * (1 - Math.pow(1 - phase, 2));
        pulse.current.scale.set(s, s, 1);
        mat.opacity = 0.6 * (1 - phase) * v.alarm * fade;
      }
    }
    if (baseMat.current) baseMat.current.color.copy(colours.base).lerp(colours.baseLit, v.lift);
    // Keep the name on the near side of the base, whichever way the camera has turned.
    if (label.current) {
      const dx = camera.position.x - position[0];
      const dz = camera.position.z - position[2];
      const len = Math.hypot(dx, dz) || 1;
      label.current.position.set((dx / len) * LABEL_OFFSET, 0, (dz / len) * LABEL_OFFSET);
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
    <group position={position}>
      {/* Hit area: the whole column, bigger than the marks so it is easy to point at. */}
      <mesh position={[0, H / 2, 0]} onPointerOver={onOver} onPointerOut={onOut} onClick={onClick}>
        <cylinderGeometry args={[0.9, 0.9, H + 1.2, 16]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>

      <mesh position={[0, 0.04, 0]}>
        <cylinderGeometry args={[0.85, 0.85, 0.08, 64]} />
        <meshStandardMaterial ref={baseMat} color={colours.base} roughness={0.55} metalness={0.2} />
      </mesh>
      {selected && (
        <mesh position={[0, 0.085, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.81, 0.85, 64]} />
          <meshBasicMaterial color={colours.ink} />
        </mesh>
      )}

      <mesh ref={halo} position={[0, 0.012, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.98, 1.08, 72]} />
        <meshBasicMaterial color={colours.drift} transparent opacity={0.2} depthWrite={false} />
      </mesh>

      <mesh ref={column}>
        <cylinderGeometry args={[0.26, 0.26, 1, 48]} />
        <meshStandardMaterial ref={columnMat} color={colours.belief} emissive={colours.belief} emissiveIntensity={0.12} roughness={0.3} metalness={0.15} envMapIntensity={0.9} />
      </mesh>
      {/* A lit cap marks the level, so the height reads at a glance from any angle. */}
      <mesh ref={cap} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.26, 48]} />
        <meshStandardMaterial ref={capMat} color={colours.belief} emissive={colours.belief} emissiveIntensity={0.7} roughness={0.4} />
      </mesh>
      <mesh ref={sleeve}>
        <cylinderGeometry args={[0.4, 0.4, 1, 48, 1, true]} />
        <meshBasicMaterial color={colours.belief} transparent opacity={0.2} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>

      <mesh ref={estRing} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.48, 0.032, 10, 56]} />
        <meshBasicMaterial color={colours.estimate} />
      </mesh>
      <mesh ref={realRing} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.6, 0.045, 10, 56]} />
        <meshBasicMaterial color={colours.grades} transparent opacity={0} />
      </mesh>

      <group ref={beacon} position={[0, H + 0.75, 0]}>
        <mesh>
          <sphereGeometry args={[0.17, 24, 16]} />
          <meshBasicMaterial color={colours.alarm} toneMapped={false} />
        </mesh>
        <sprite scale={[1.5, 1.5, 1]}>
          <spriteMaterial map={glowTexture()} color={colours.alarmFlat} transparent opacity={0.85} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
        </sprite>
      </group>
      <mesh ref={okRing} position={[0, H + 0.75, 0]}>
        <torusGeometry args={[0.13, 0.022, 8, 32]} />
        <meshBasicMaterial color={colours.ink} transparent opacity={0.55} />
      </mesh>
      <mesh ref={pulse} position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.92, 1.0, 72]} />
        <meshBasicMaterial color={colours.alarmFlat} transparent opacity={0} depthWrite={false} />
      </mesh>

      {/* The readout row: this week's believed catch rate under each status light. */}
      <Html position={[0, H + 0.3, 0]} center className="stage-readout" zIndexRange={[6, 0]}>
        <span className={`stage-readout__value num${tone}`}>{pct(w.catch_rate)}</span>
      </Html>

      <group ref={label}>
        <Html center className="stage-label" zIndexRange={[5, 0]}>
          <div className={`stage-label__inner${tone}`}>
            <span className="stage-label__id">{clinic.clinic_id}</span>
            {alarm && d?.reason && <span className="stage-label__alarm">{REASON_LABEL[d.reason]}</span>}
          </div>
        </Html>
      </group>

      {hovered && (
        <Html position={[0, H + 1.25, 0]} center zIndexRange={[30, 20]}>
          <div className="tooltip" role="tooltip">
            <div className="tooltip__title">
              {clinic.clinic_id} <span className="tooltip__sub">{clinic.site}</span>
            </div>
            <dl className="tooltip__rows">
              <div><dt><i className="key key--belief" />ClinicDrift</dt><dd className="num">{pct(w.catch_rate)} <span className="tooltip__sub num">{pct(w.catch_low)}–{pct(w.catch_high)}</span></dd></div>
              <div><dt><i className="key key--estimate" />AI's own estimate</dt><dd className="num">{pct(w.est_sensitivity)}</dd></div>
              <div><dt><i className="key key--drift" />Drift</dt><dd className="num">{num(w.drift_auc)}</dd></div>
              {hindsight && <div><dt><i className="key key--grades" />Real, last 3 weeks</dt><dd className="num">{pct(real)}</dd></div>}
            </dl>
          </div>
        </Html>
      )}
    </group>
  );
}
