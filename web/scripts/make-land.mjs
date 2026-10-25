// Writes public/data/land.json: evenly spread points on the globe that fall on land, for the
// World view's dotted map. Run once (the output is committed): node scripts/make-land.mjs
import { readFileSync, writeFileSync } from "node:fs";
import { geoContains } from "d3-geo";
import { feature } from "topojson-client";

const world = JSON.parse(readFileSync(new URL("../node_modules/world-atlas/land-110m.json", import.meta.url)));
const land = feature(world, world.objects.land);
const N = 16000; // points on the whole sphere; about 30% land on
const golden = Math.PI * (3 - Math.sqrt(5));
const out = [];
for (let i = 0; i < N; i++) {
  const y = 1 - (2 * (i + 0.5)) / N; // Fibonacci sphere: even spacing, no pole clumping
  const lat = (Math.asin(y) * 180) / Math.PI;
  const lon = ((((i * golden * 180) / Math.PI) % 360) + 540) % 360 - 180;
  if (lat < -60) continue; // Antarctica adds nothing here
  if (geoContains(land, [lon, lat])) out.push(+lat.toFixed(1), +lon.toFixed(1));
}
writeFileSync(new URL("../public/data/land.json", import.meta.url), JSON.stringify(out));
console.log(`land.json: ${out.length / 2} points`);
