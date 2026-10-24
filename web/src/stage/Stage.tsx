// The 3D view: ten clinics on a darkroom floor, the screening standard as a plane through them.
// "This week" stands each clinic up as a column; "All weeks" lays its whole replay out as a ribbon.
import { Environment, Grid, Html, Lightformer, OrbitControls, PerformanceMonitor } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import gsap from "gsap";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { getState, reducedMotion, setState, useBundle, useStore, type Mode } from "../store";
import { ClinicColumn } from "./ClinicColumn";
import { HistoryView, ROW_SPACING, WEEK_DEPTH } from "./HistoryView";
import { COLUMN_HEIGHT as H, SPACING, layout, token } from "./layout";
import { storyCamera } from "../ui/storySteps";

const HOME = {
  now: { target: new THREE.Vector3(0, 2.1, 0.2), direction: new THREE.Vector3(0, 0.44, 1).normalize() },
  // Three-quarter view from the front right: week 1 nearest, later weeks running away from you.
  history: { target: new THREE.Vector3(0.4, 1.1, 0.4), direction: new THREE.Vector3(0.38, 0.72, 1).normalize() },
} as const;

/** The overview: far enough back that the whole scene fits the stage's width. */
function homeShot(mode: Mode, fov: number, aspect: number, halfWidth: number) {
  const across = Math.tan(((fov * Math.PI) / 180) / 2) * aspect;
  const { target, direction } = HOME[mode];
  const distance = Math.min(38, Math.max(17, halfWidth / across + (mode === "now" ? 2.6 : 1)));
  return { target: target.clone(), position: target.clone().addScaledVector(direction, distance) };
}

export function Stage() {
  const view = useStore((s) => s.view);
  // Start sharp; if frames come too slowly (an integrated GPU), drop to plain resolution.
  const [dpr, setDpr] = useState(Math.min(1.5, window.devicePixelRatio || 1));
  return (
    <div className="stage" aria-hidden="true">
      <Canvas
        camera={{ position: homeShot("now", 34, 1.4, 8).position.toArray(), fov: 34, near: 0.1, far: 120 }}
        dpr={dpr}
        gl={{ antialias: true, powerPreference: "high-performance" }}
        frameloop={view === "results" ? "never" : "always"}
        onPointerMissed={() => setState({ hovered: null })}
      >
        <PerformanceMonitor onDecline={() => setDpr(1)} />
        <color attach="background" args={[token("--ground")]} />
        <fog attach="fog" args={[token("--ground"), 22, 50]} />
        <ambientLight intensity={0.35} />
        <directionalLight position={[6, 12, 8]} intensity={1.3} />
        <directionalLight position={[-8, 6, -6]} intensity={0.3} />
        {/* A studio made of soft light panels, rendered once: it gives the columns their sheen. */}
        <Environment resolution={256} frames={1}>
          <Lightformer form="rect" intensity={1.6} position={[0, 6, -10]} scale={[24, 4, 1]} />
          <Lightformer form="rect" intensity={0.9} position={[-10, 3, 2]} rotation={[0, Math.PI / 2, 0]} scale={[12, 3, 1]} />
          <Lightformer form="rect" intensity={0.6} position={[10, 3, 4]} rotation={[0, -Math.PI / 2, 0]} scale={[12, 3, 1]} />
          <Lightformer form="ring" intensity={0.8} position={[0, 12, 0]} rotation={[Math.PI / 2, 0, 0]} scale={6} />
        </Environment>
        <Floor />
        <Scene />
      </Canvas>
    </div>
  );
}

/** A dark satin floor. It catches the studio light as a soft sheen; a true mirror floor was
 *  tried and dropped, since it re-renders the scene every frame and stalls integrated GPUs. */
function Floor() {
  return (
    <>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}>
        <planeGeometry args={[90, 90]} />
        <meshStandardMaterial color={token("--ground")} roughness={0.55} metalness={0.35} envMapIntensity={0.5} />
      </mesh>
      <Grid
        args={[60, 60]}
        position={[0, 0.001, 0]}
        cellSize={0.8}
        cellThickness={0.5}
        cellColor={token("--panel")}
        sectionSize={SPACING}
        sectionThickness={0.9}
        sectionColor={token("--panel-3")}
        fadeDistance={40}
        fadeStrength={1.8}
        infiniteGrid
      />
    </>
  );
}

function Scene() {
  const bundle = useBundle();
  const mode = useStore((s) => s.mode);
  const positions = useMemo(() => layout(bundle.clinics), [bundle]);
  const xs = Object.values(positions).map((p) => p[0]);
  const zs = Object.values(positions).map((p) => p[2]);
  const width = Math.max(...xs) - Math.min(...xs) + SPACING;
  const depth = Math.max(...zs) - Math.min(...zs) + SPACING * 1.2;
  const standard = bundle.settings.min_catch_rate * H;
  const halfWidth = mode === "now" ? width / 2 + 0.6 : (bundle.clinics.length * ROW_SPACING) / 2 + (bundle.settings.n_weeks * WEEK_DEPTH) / 4;

  return (
    <>
      {mode === "now" ? (
        <>
          {bundle.clinics.map((clinic) => (
            <ClinicColumn key={clinic.clinic_id} clinic={clinic} position={positions[clinic.clinic_id]} />
          ))}

          {/* The UK screening standard: a catch rate of 80%. Columns below it are failing. */}
          <mesh position={[0, standard, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[width, depth]} />
            <meshBasicMaterial color={token("--ink")} transparent opacity={0.025} side={THREE.DoubleSide} depthWrite={false} />
          </mesh>
          <lineSegments position={[0, standard, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <edgesGeometry args={[new THREE.PlaneGeometry(width, depth)]} />
            <lineBasicMaterial color={token("--ink")} transparent opacity={0.2} />
          </lineSegments>
          <Html position={[width / 2, standard, depth / 2]} className="stage-note" zIndexRange={[5, 0]}>
            <div className="stage-note__inner">
              <span className="num">{Math.round(bundle.settings.min_catch_rate * 100)}%</span> screening standard
            </div>
          </Html>
        </>
      ) : (
        <HistoryView />
      )}

      {/* No target prop: a fresh array each render would snap the target back. CameraRig sets it. */}
      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.08}
        enablePan={false}
        minDistance={6}
        maxDistance={34}
        minPolarAngle={0.25}
        maxPolarAngle={1.38}
      />
      <CameraRig positions={positions} halfWidth={halfWidth} />
    </>
  );
}

/** Share of the stage's width the detail drawer covers when open (0 on narrow screens, where it is full screen). */
function drawerCover(): number {
  const stage = document.querySelector(".stage")?.getBoundingClientRect();
  const main = document.querySelector(".main")?.getBoundingClientRect();
  if (!stage || !main || window.innerWidth < 900) return 0;
  const drawerLeft = main.right - Math.min(600, main.width);
  return Math.max(0, stage.right - drawerLeft) / stage.width;
}

/** Share of the stage the story card covers, counted as half since it only covers the bottom. */
function storyCover(): number {
  const stage = document.querySelector(".stage")?.getBoundingClientRect();
  if (!stage || window.innerWidth < 900) return 0;
  return (0.5 * Math.min(476, stage.width)) / stage.width;
}

/** Flies the camera to the selected clinic or the story's shot; the person's own drag always wins.
 *  The flight starts from the render loop, not an effect: the orbit controls register a frame or
 *  so after mount, and a request made before then must still be carried out. */
function CameraRig({ positions, halfWidth }: { positions: Record<string, [number, number, number]>; halfWidth: number }) {
  const aspect = useThree((s) => s.size.width / Math.max(1, s.size.height));
  const selected = useStore((s) => s.selected);
  const story = useStore((s) => s.story);
  const mode = useStore((s) => s.mode);
  const nonce = useStore((s) => s.cameraNonce);

  const latest = useRef({ positions, halfWidth, aspect });
  latest.current = { positions, halfWidth, aspect };
  const requested = useRef(0);
  const handled = useRef(-1);
  const flight = useRef<gsap.core.Timeline | null>(null);
  const wired = useRef<OrbitControlsImpl | null>(null);

  useEffect(() => {
    requested.current += 1;
  }, [selected, story, mode, nonce, positions, aspect, halfWidth]);
  useEffect(() => () => void flight.current?.kill(), []);

  useFrame((state) => {
    const controls = state.controls as unknown as OrbitControlsImpl | null;
    const camera = state.camera as THREE.PerspectiveCamera;
    if (!controls) return;
    if (wired.current !== controls) {
      // A drag stops any flight and hides the "drag to turn" hint.
      wired.current = controls;
      controls.addEventListener("start", () => {
        flight.current?.kill();
        if (!getState().orbited) setState({ orbited: true });
      });
    }
    if (handled.current === requested.current) return;
    const first = handled.current < 0;
    handled.current = requested.current;

    const { positions, halfWidth, aspect } = latest.current;
    const { selected, story, mode, bundle } = getState();
    // In "All weeks" a clinic opens without moving the camera: the whole replay stays in view.
    const shot = story !== null ? storyCamera(story, bundle) : mode === "now" ? selected : null;
    const across = Math.tan(((camera.fov * Math.PI) / 180) / 2) * aspect; // half the visible width per unit of distance
    let { position, target } = homeShot(mode, camera.fov, aspect, halfWidth);
    if (shot === "back") {
      // Up high over the front row, looking down on the clinics behind it.
      target = new THREE.Vector3(0, 1.2, -2.5);
      position = target.clone().add(new THREE.Vector3(0, 1.15, 1).normalize().multiplyScalar(Math.max(15, halfWidth / across + 1)));
    } else if (shot && positions[shot]) {
      const [x, , z] = positions[shot];
      target = new THREE.Vector3(x, 2.3, z);
      position = target.clone().add(new THREE.Vector3(0.12, 0.36, 1).normalize().multiplyScalar(13));
    }
    // Something covers part of the stage (the drawer on the right, the story card on the left):
    // aim off-centre by half of it, so the shot sits in the middle of what is still visible.
    const distance = position.distanceTo(target);
    const cover = story !== null ? -storyCover() : selected ? drawerCover() : 0;
    const shift = cover * distance * across;
    target.x += shift;
    position.x += shift;

    flight.current?.kill();
    if (first) {
      // The opening shot is placed, not flown to: there is nowhere sensible to fly from.
      camera.position.copy(position);
      controls.target.copy(target);
      controls.update();
      return;
    }
    const seconds = reducedMotion() ? 0 : 1.2;
    const tl = gsap.timeline({ defaults: { duration: seconds, ease: "power3.inOut" }, onUpdate: () => controls.update() });
    tl.to(camera.position, { x: position.x, y: position.y, z: position.z }, 0);
    tl.to(controls.target, { x: target.x, y: target.y, z: target.z }, 0);
    flight.current = tl;
  });

  return null;
}
