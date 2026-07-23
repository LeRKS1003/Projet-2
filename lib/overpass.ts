import { BBox, centroid, LatLng, ringBBox } from "./geo";

export interface Building {
  id: number;
  /** Emprise du bâtiment (contour). */
  ring: LatLng[];
  center: LatLng;
}

export interface Wildland {
  id: number;
  /** Contour de la zone boisée / végétation (facteur de risque incendie). */
  ring: LatLng[];
  bbox: BBox;
}

interface OverpassElement {
  type: string;
  id: number;
  geometry?: { lat: number; lon: number }[];
}

interface OverpassResponse {
  elements: OverpassElement[];
}

const ENDPOINTS = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
];

export interface Bounds {
  south: number;
  west: number;
  north: number;
  east: number;
}

/**
 * Récupère les emprises des bâtiments (habitats) dans une zone donnée
 * depuis l'API Overpass d'OpenStreetMap.
 */
export async function fetchBuildings(
  bounds: Bounds,
  limit = 1200
): Promise<Building[]> {
  const { south, west, north, east } = bounds;
  const query = `[out:json][timeout:25];
(way["building"](${south},${west},${north},${east}););
out geom ${limit};`;

  let lastError: unknown = null;
  for (const endpoint of ENDPOINTS) {
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "data=" + encodeURIComponent(query),
      });
      if (!res.ok) {
        lastError = new Error(`Overpass a répondu ${res.status}`);
        continue;
      }
      const data: OverpassResponse = await res.json();
      return parseBuildings(data);
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError instanceof Error
    ? lastError
    : new Error("Impossible de contacter Overpass");
}

function parseBuildings(data: OverpassResponse): Building[] {
  const buildings: Building[] = [];
  for (const el of data.elements) {
    if (el.type !== "way" || !el.geometry || el.geometry.length < 3) continue;
    const ring: LatLng[] = el.geometry.map((g) => ({ lat: g.lat, lng: g.lon }));
    buildings.push({ id: el.id, ring, center: centroid(ring) });
  }
  return buildings;
}

/**
 * Récupère les zones boisées / de végétation (forêts, bois, landes, garrigue)
 * dans une zone donnée : ce sont les vrais foyers de risque « feu de forêt ».
 */
export async function fetchWildland(
  bounds: Bounds,
  limit = 400
): Promise<Wildland[]> {
  const { south, west, north, east } = bounds;
  const filters = [
    'way["landuse"="forest"]',
    'way["natural"="wood"]',
    'way["natural"="scrub"]',
    'way["natural"="heath"]',
  ]
    .map((f) => `${f}(${south},${west},${north},${east});`)
    .join("");
  const query = `[out:json][timeout:25];
(${filters});
out geom ${limit};`;

  let lastError: unknown = null;
  for (const endpoint of ENDPOINTS) {
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "data=" + encodeURIComponent(query),
      });
      if (!res.ok) {
        lastError = new Error(`Overpass a répondu ${res.status}`);
        continue;
      }
      const data: OverpassResponse = await res.json();
      return parseWildland(data);
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError instanceof Error
    ? lastError
    : new Error("Impossible de contacter Overpass");
}

function parseWildland(data: OverpassResponse): Wildland[] {
  const zones: Wildland[] = [];
  for (const el of data.elements) {
    if (el.type !== "way" || !el.geometry || el.geometry.length < 3) continue;
    const ring: LatLng[] = el.geometry.map((g) => ({ lat: g.lat, lng: g.lon }));
    zones.push({ id: el.id, ring, bbox: ringBBox(ring) });
  }
  return zones;
}
