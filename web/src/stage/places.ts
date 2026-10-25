// Where each clinic sits on the globe. The clinics are simulated, so these places are
// illustrative: the non-US ones are near where each dataset was collected (Messidor-2 in Brest,
// APTOS at Aravind in Tamil Nadu, IDRiD in Nanded), the US ones spread across the country, and
// the two clinics that switch scanners sit in the UK, whose screening standard sets our 80%.
import * as THREE from "three";

export interface Place {
  city: string;
  lat: number;
  lon: number;
}

/** Where the AI was validated: EyePACS, Santa Cruz, California. */
export const VALIDATION: Place = { city: "Santa Cruz, CA", lat: 36.97, lon: -122.03 };

export const PLACES: Record<string, Place> = {
  "US-EYE-01": { city: "Los Angeles", lat: 34.05, lon: -118.24 },
  "US-EYE-02": { city: "Chicago", lat: 41.88, lon: -87.63 },
  "US-WEAR-01": { city: "Houston", lat: 29.76, lon: -95.37 },
  "US-UPD-01": { city: "New York", lat: 40.71, lon: -74.01 },
  "SW-MES-01": { city: "Glasgow", lat: 55.86, lon: -4.25 },
  "SW-APT-01": { city: "London", lat: 51.51, lon: -0.13 },
  "FR-MES-01": { city: "Brest", lat: 48.39, lon: -4.49 },
  "IN-APT-01": { city: "Madurai", lat: 9.93, lon: 78.12 },
  "IN-APT-02": { city: "Kolkata", lat: 22.57, lon: 88.36 },
  "IN-IDR-01": { city: "Nanded", lat: 19.15, lon: 77.32 },
};

const COUNTRY: Record<string, Place> = {
  "United States": { city: "United States", lat: 39.5, lon: -98.35 },
  France: { city: "France", lat: 46.6, lon: 2.2 },
  India: { city: "India", lat: 21, lon: 78 },
};

export function placeOf(clinicId: string, country: string): Place {
  return PLACES[clinicId] ?? COUNTRY[country] ?? { city: country, lat: 0, lon: 0 };
}

/** A point on a sphere of radius r: latitude up the y axis, longitude 0 facing +z after the
 *  globe's own turn (see GLOBE_TURN). */
export function latLonToVector(lat: number, lon: number, r: number): THREE.Vector3 {
  const phi = ((90 - lat) * Math.PI) / 180;
  const theta = ((lon + 180) * Math.PI) / 180;
  return new THREE.Vector3(-r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta));
}

/** The globe's turn (about y, then tilt about x) that brings lat/lon to face the viewer. */
export function faceTurn(lat: number, lon: number): { spin: number; tilt: number } {
  return { spin: (-lon * Math.PI) / 180 - Math.PI / 2, tilt: (lat * Math.PI) / 180 };
}

/** Named views for the story. */
export const GLOBE_SHOTS: Record<string, { lat: number; lon: number }> = {
  americas: { lat: 30, lon: -95 },
  "europe-india": { lat: 30, lon: 44 },
  atlantic: { lat: 38, lon: -45 },
};
