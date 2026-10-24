// "All weeks": every clinic's whole replay at once. Each clinic is a ribbon standing on the floor,
// week 1 nearest the viewer and later weeks further away; the ribbon's band is ClinicDrift's 90%
// belief, the bright edge its best guess, the amber line the AI's own estimate, the floor strip
// drift, and a red light the week the alarm started. An upright sheet marks "now": nothing beyond
// it has happened yet, so the ribbons are clipped there and grow away from you as the replay plays.
import { Html } from "@react-three/drei";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { realCatchRate } from "../data/model";
import type { Clinic } from "../data/types";
import { num, pad2, pct, REASON_LABEL } from "../format";
import { reducedMotion, setState, useBundle, useDecisions, useStore } from "../store";
import { COLUMN_HEIGHT as H, easeInOutCubic, glowTexture, rowOrder, token } from "./layout";

export const ROW_SPACING = 2.0;
export const WEEK_DEPTH = 0.62;
const DATA_SECONDS = 0.6;
const UI_SECONDS = 0.2;

/** Where week w sits along the floor: week 1 nearest the viewer, the last week furthest away. */
export const weekZ = (week: number, n: number) => ((n + 1) / 2 - week) * WEEK_DEPTH;
/** Just beyond week w: where "now" stands once week w has happened. */
const nowZ = (week: number, n: number) => weekZ(week, n) - WEEK_DEPTH / 2;

function polylineTube(points: THREE.Vector3[], radius: number): THREE.TubeGeometry {
  const path = new THREE.CurvePath<THREE.Vector3>();
  for (let i = 0; i < points.length - 1; i++) path.add(new THREE.LineCurve3(points[i], points[i + 1]));
  return new THREE.TubeGeometry(path, Math.max(1, points.length - 1) * 10, radius, 8, false);
}

function bandGeometry(lows: number[], highs: number[], zs: number[]): THREE.BufferGeometry {
  const pos: number[] = [];
  const index: number[] = [];
  zs.forEach((z, i) => pos.push(0, lows[i] * H, z, 0, highs[i] * H, z));
  for (let i = 0; i < zs.length - 1; i++) {
    const a = 2 * i;
    index.push(a, a + 2, a + 1, a + 1, a + 2, a + 3);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(index);
  g.computeVertexNormals();
  return g;
}

/** A floor strip whose colour runs from the ground to aqua as drift rises, week by week. */
function driftStrip(drifts: number[], zs: number[], ground: THREE.Color, drift: THREE.Color): THREE.BufferGeometry {
  const pos: number[] = [];
  const col: number[] = [];
  const index: number[] = [];
  const c = new THREE.Color();
  const half = WEEK_DEPTH / 2 - 0.02;
  // One tile per week, so each week's drift reads on its own.
  drifts.forEach((d, i) => {
    c.copy(ground).lerp(drift, Math.min(1, Math.max(0, (d - 0.5) / 0.5)) * 0.55);
    for (const z of [zs[i] + half, zs[i] - half]) {
      pos.push(-0.4, 0, z, 0.4, 0, z);
      col.push(c.r, c.g, c.b, c.r, c.g, c.b);
    }
    const a = 4 * i;
    index.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
  });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  g.setIndex(index);
  return g;
}

export function HistoryView() {
  const bundle = useBundle();
  const week = useStore((s) => s.week);
  const n = bundle.settings.n_weeks;
  const order = useMemo(() => rowOrder(bundle.clinics), [bundle]);
  const width = order.length * ROW_SPACING;
  const depth = n * WEEK_DEPTH;
  const standard = bundle.settings.min_catch_rate * H;
  const gl = useThree((s) => s.gl);

  // "Now": everything beyond it is clipped away (kept where z >= now). It slides to the new week in 600ms.
  const clip = useMemo(() => new THREE.Plane(new THREE.Vector3(0, 0, 1), -nowZ(week, n)), []); // eslint-disable-line react-hooks/exhaustive-deps
  const slide = useRef({ from: nowZ(week, n), to: nowZ(week, n), t0: 0 });
  const nowSlice = useRef<THREE.Group>(null);
  const still = useMemo(() => reducedMotion(), []);

  useEffect(() => {
    gl.localClippingEnabled = true;
    return () => {
      gl.localClippingEnabled = false;
    };
  }, [gl]);

  useEffect(() => {
    slide.current = { from: -clip.constant, to: nowZ(week, n), t0: performance.now() / 1000 };
  }, [week, n, clip]);

  useFrame(() => {
    const s = slide.current;
    const p = still ? 1 : Math.min(1, (performance.now() / 1000 - s.t0) / DATA_SECONDS);
    const z = s.from + (s.to - s.from) * easeInOutCubic(p);
    clip.constant = -z;
    if (nowSlice.current) nowSlice.current.position.z = z;
  });

  const ink = token("--ink");
  const xOf = (i: number) => (i - (order.length - 1) / 2) * ROW_SPACING;

  return (
    <group>
      {order.map((clinic, i) => (
        <Ribbon key={clinic.clinic_id} clinic={clinic} x={xOf(i)} clip={clip} />
      ))}

      {/* The 80% standard as a level across every clinic and every week. */}
      <mesh position={[0, standard, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[width, depth + WEEK_DEPTH]} />
        <meshBasicMaterial color={ink} transparent opacity={0.03} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      <lineSegments position={[0, standard, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <edgesGeometry args={[new THREE.PlaneGeometry(width, depth + WEEK_DEPTH)]} />
        <lineBasicMaterial color={ink} transparent opacity={0.2} />
      </lineSegments>
      <Html position={[width / 2, standard, (depth + WEEK_DEPTH) / 2]} className="stage-note" zIndexRange={[5, 0]}>
        <div className="stage-note__inner stage-note__inner--after">
          <span className="num">{Math.round(bundle.settings.min_catch_rate * 100)}%</span> standard
        </div>
      </Html>

      {/* Now: an upright sheet at the current week. */}
      <group ref={nowSlice}>
        <mesh position={[0, H / 2, 0]}>
          <planeGeometry args={[width + 0.6, H]} />
          <meshBasicMaterial color={ink} transparent opacity={0.025} side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
        <lineSegments position={[0, H / 2, 0]}>
          <edgesGeometry args={[new THREE.PlaneGeometry(width + 0.6, H)]} />
          <lineBasicMaterial color={ink} transparent opacity={0.28} />
        </lineSegments>
        <Html position={[-(width + 0.6) / 2, H, 0]} className="stage-note" zIndexRange={[5, 0]}>
          <div className="stage-note__inner stage-note__inner--after">
            Week <span className="num">{pad2(week)}</span>
          </div>
        </Html>
      </group>

      {/* Week ticks down the left side. */}
      {[1, 5, 10, 15, n].map((w) => (
        <Html key={w} position={[-width / 2 - 0.5, 0, weekZ(w, n)]} center className="stage-tick" zIndexRange={[5, 0]}>
          <span className="num">{pad2(w)}</span>
        </Html>
      ))}
    </group>
  );
}

function Ribbon({ clinic, x, clip }: { clinic: Clinic; x: number; clip: THREE.Plane }) {
  const bundle = useBundle();
  const n = bundle.settings.n_weeks;
  const week = useStore((s) => s.week);
  const hindsight = useStore((s) => s.hindsight);
  const focus = useStore((s) => s.hovered ?? s.selected);
  const decision = useDecisions()[clinic.clinic_id];
  const [hoverWeek, setHoverWeek] = useState<number | null>(null);
  const dimmed = focus !== null && focus !== clinic.clinic_id;
  const focused = focus === clinic.clinic_id;

  const colours = useMemo(
    () => ({
      belief: new THREE.Color(token("--belief")),
      estimate: new THREE.Color(token("--estimate")),
      grades: new THREE.Color(token("--grades")),
      drift: new THREE.Color(token("--drift")),
      ground: new THREE.Color(token("--panel")),
      recede: new THREE.Color(token("--panel")),
      alarm: new THREE.Color(token("--alarm")).multiplyScalar(1.15),
      alarmFlat: new THREE.Color(token("--alarm")),
      ink: new THREE.Color(token("--ink")),
    }),
    [],
  );

  const geo = useMemo(() => {
    const zs = clinic.weeks.map((w) => weekZ(w.week, n));
    const at = (values: number[]) => values.map((v, i) => new THREE.Vector3(0, v * H, zs[i]));
    let lastReal = clinic.weeks[0].catch_rate;
    const reals = clinic.weeks.map((w) => (lastReal = realCatchRate(clinic, w.week) ?? lastReal));
    return {
      band: bandGeometry(
        clinic.weeks.map((w) => w.catch_low),
        clinic.weeks.map((w) => w.catch_high),
        zs,
      ),
      belief: polylineTube(at(clinic.weeks.map((w) => w.catch_rate)), 0.045),
      estimate: polylineTube(at(clinic.weeks.map((w) => w.est_sensitivity)), 0.028),
      real: polylineTube(at(reals), 0.04),
      drift: driftStrip(clinic.weeks.map((w) => w.drift_auc), zs, colours.ground, colours.drift),
    };
  }, [clinic, n, colours]);
  useEffect(() => () => Object.values(geo).forEach((g) => g.dispose()), [geo]);

  const alarmWeek = decision?.firstAlarm ?? null;
  const alarmReason = alarmWeek ? decision.weeks[alarmWeek - 1].reason : null;
  const alarmZ = alarmWeek ? weekZ(alarmWeek, n) : 0;
  const alarmY = alarmWeek ? clinic.weeks[alarmWeek - 1].catch_high * H + 0.35 : 0;

  // Focus: 200ms fade of everyone else's marks.
  const dim = useRef({ value: dimmed ? 1 : 0, from: 0, to: dimmed ? 1 : 0, t0: 0 });
  useEffect(() => {
    dim.current = { ...dim.current, from: dim.current.value, to: dimmed ? 1 : 0, t0: performance.now() / 1000 };
  }, [dimmed]);
  const bandMat = useRef<THREE.MeshBasicMaterial>(null);
  const beliefMat = useRef<THREE.MeshStandardMaterial>(null);
  const estMat = useRef<THREE.MeshBasicMaterial>(null);
  const realMat = useRef<THREE.MeshBasicMaterial>(null);
  const stripMat = useRef<THREE.MeshBasicMaterial>(null);
  const still = useMemo(() => reducedMotion(), []);
  useFrame(() => {
    const d = dim.current;
    const p = still ? 1 : Math.min(1, (performance.now() / 1000 - d.t0) / UI_SECONDS);
    d.value = d.from + (d.to - d.from) * (1 - Math.pow(1 - p, 3));
    const fade = 1 - 0.75 * d.value;
    if (bandMat.current) bandMat.current.opacity = (focused ? 0.34 : 0.22) * fade;
    if (beliefMat.current) {
      beliefMat.current.color.copy(colours.belief).lerp(colours.recede, 0.75 * d.value);
      beliefMat.current.emissive.copy(beliefMat.current.color);
    }
    if (estMat.current) estMat.current.color.copy(colours.estimate).lerp(colours.recede, 0.75 * d.value);
    if (realMat.current) realMat.current.opacity = fade;
    if (stripMat.current) stripMat.current.opacity = fade;
  });

  const weekAt = (z: number) => Math.max(1, Math.min(week, Math.round((n + 1) / 2 - z / WEEK_DEPTH)));
  const onMove = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    const w = weekAt(e.point.z);
    if (w !== hoverWeek) setHoverWeek(w);
    setState((s) => (s.hovered === clinic.clinic_id ? {} : { hovered: clinic.clinic_id }));
    document.body.style.cursor = "pointer";
  };
  const onOut = () => {
    setHoverWeek(null);
    setState((s) => (s.hovered === clinic.clinic_id ? { hovered: null } : {}));
    document.body.style.cursor = "";
  };
  // Clicking a point in time opens the clinic at that week.
  const onClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    setState({ selected: clinic.clinic_id, week: weekAt(e.point.z), playing: false, story: null });
  };

  const h = hoverWeek ? clinic.weeks[hoverWeek - 1] : null;
  const clipping = [clip];
  const tone = focused ? " is-focus" : dimmed ? " is-dim" : "";

  return (
    <group position={[x, 0, 0]}>
      {/* Hit area: an invisible wall the length and height of the ribbon. */}
      <mesh position={[0, H / 2, 0]} rotation={[0, Math.PI / 2, 0]} onPointerMove={onMove} onPointerOut={onOut} onClick={onClick}>
        <planeGeometry args={[n * WEEK_DEPTH, H + 0.6]} />
        <meshBasicMaterial transparent opacity={0} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>

      <mesh geometry={geo.drift} position={[0, 0.004, 0]} rotation={[0, 0, 0]}>
        <meshBasicMaterial ref={stripMat} vertexColors transparent clippingPlanes={clipping} depthWrite={false} />
      </mesh>
      <mesh geometry={geo.band}>
        <meshBasicMaterial ref={bandMat} color={colours.belief} transparent opacity={0.22} side={THREE.DoubleSide} depthWrite={false} clippingPlanes={clipping} />
      </mesh>
      <mesh geometry={geo.belief}>
        <meshStandardMaterial ref={beliefMat} color={colours.belief} emissive={colours.belief} emissiveIntensity={0.35} roughness={0.35} clippingPlanes={clipping} />
      </mesh>
      <mesh geometry={geo.estimate}>
        <meshBasicMaterial ref={estMat} color={colours.estimate} clippingPlanes={clipping} />
      </mesh>
      {hindsight && (
        <mesh geometry={geo.real}>
          <meshBasicMaterial ref={realMat} color={colours.grades} transparent clippingPlanes={clipping} />
        </mesh>
      )}

      {alarmWeek && (
        <group position={[0, 0, alarmZ]}>
          <mesh position={[0, alarmY, 0]}>
            <sphereGeometry args={[0.16, 24, 16]} />
            <meshBasicMaterial color={colours.alarm} toneMapped={false} clippingPlanes={clipping} />
          </mesh>
          <sprite position={[0, alarmY, 0]} scale={[1.3, 1.3, 1]}>
            <spriteMaterial map={glowTexture()} color={colours.alarmFlat} transparent opacity={0.8} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} clippingPlanes={clipping} />
          </sprite>
          {/* From the alarm onward, a red line along the ribbon's foot: the AI is pulled. */}
          <mesh position={[0.56, 0.006, -((n - alarmWeek + 0.5) * WEEK_DEPTH) / 2]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[0.07, ((n - alarmWeek) + 0.5) * WEEK_DEPTH]} />
            <meshBasicMaterial color={colours.alarmFlat} clippingPlanes={clipping} />
          </mesh>
        </group>
      )}

      <Html position={[0, 0, weekZ(1, n) + 0.9]} center className="stage-label" zIndexRange={[5, 0]}>
        <div className={`stage-label__inner stage-label__inner--row${tone}`}>
          {alarmWeek && alarmWeek <= week && alarmReason && <i className="status-dot status-dot--alarm status-dot--still" aria-label={REASON_LABEL[alarmReason]} />}
          <span className="stage-label__id">{clinic.clinic_id}</span>
        </div>
      </Html>

      {h && (
        <>
          <mesh position={[0, h.catch_rate * H, weekZ(h.week, n)]}>
            <sphereGeometry args={[0.09, 16, 12]} />
            <meshBasicMaterial color={colours.ink} />
          </mesh>
          <Html position={[0, h.catch_high * H + 0.9, weekZ(h.week, n)]} center zIndexRange={[30, 20]}>
            <div className="tooltip" role="tooltip">
              <div className="tooltip__title">
                {clinic.clinic_id}, week <span className="num">{pad2(h.week)}</span>
              </div>
              <dl className="tooltip__rows">
                <div><dt><i className="key key--belief" />ClinicDrift</dt><dd className="num">{pct(h.catch_rate)} <span className="tooltip__sub num">{pct(h.catch_low)}–{pct(h.catch_high)}</span></dd></div>
                <div><dt><i className="key key--estimate" />AI's own estimate</dt><dd className="num">{pct(h.est_sensitivity)}</dd></div>
                <div><dt><i className="key key--drift" />Drift</dt><dd className="num">{num(h.drift_auc)}</dd></div>
                {hindsight && <div><dt><i className="key key--grades" />Real, last 3 weeks</dt><dd className="num">{pct(realCatchRate(clinic, h.week))}</dd></div>}
              </dl>
              <div className="tooltip__hint">Click to open this week</div>
            </div>
          </Html>
        </>
      )}
    </group>
  );
}
