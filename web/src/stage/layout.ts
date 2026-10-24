// Where each clinic stands on the floor. Positions follow the clinic, never its rank, so a
// clinic is always in the same place. The story's two clinics sit front and centre, each next
// to a healthy one for comparison; the clinics that differ from day one stand at the back.
import * as THREE from "three";
import type { Clinic } from "../data/types";

export const COLUMN_HEIGHT = 4; // world units for a 100% catch rate
export const SPACING = 3.0;

const FRONT = ["US-EYE-01", "US-WEAR-01", "US-UPD-01", "US-EYE-02", "SW-MES-01"];
const BACK = ["SW-APT-01", "FR-MES-01", "IN-APT-01", "IN-APT-02", "IN-IDR-01"];
const FRONT_Z = 2.3;
const BACK_Z = -2.5;

export function layout(clinics: Clinic[]): Record<string, [number, number, number]> {
  const out: Record<string, [number, number, number]> = {};
  const place = (ids: string[], z: number) =>
    ids.forEach((id, i) => {
      out[id] = [(i - (ids.length - 1) / 2) * SPACING, 0, z];
    });
  const known = new Set([...FRONT, ...BACK]);
  const extra = clinics.map((c) => c.clinic_id).filter((id) => !known.has(id));
  place(FRONT.filter((id) => clinics.some((c) => c.clinic_id === id)), FRONT_Z);
  place([...BACK.filter((id) => clinics.some((c) => c.clinic_id === id)), ...extra], BACK_Z);
  return out;
}

/** The clinics in one row for the "All weeks" view, in the same left-to-right order as the floor. */
export function rowOrder(clinics: Clinic[]): Clinic[] {
  const rank = (id: string) => {
    const i = [...FRONT, ...BACK].indexOf(id);
    return i < 0 ? FRONT.length + BACK.length : i;
  };
  return [...clinics].sort((a, b) => rank(a.clinic_id) - rank(b.clinic_id));
}

export function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

let glow: THREE.Texture | null = null;

/** A soft round falloff, drawn once: the halo behind alarm beacons. A sprite costs next to
 *  nothing, where a bloom pass halved the frame rate on integrated graphics. */
export function glowTexture(): THREE.Texture {
  if (glow) return glow;
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.25, "rgba(255,255,255,0.45)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  glow = new THREE.CanvasTexture(canvas);
  return glow;
}

/** CSS custom property as a colour string, read once from the token sheet. */
export function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
