import { centroid, LatLng } from "./geo";

export interface Building {
  id: number;
  /** Emprise du bâtiment (contour). */
  ring: LatLng[];
  center: LatLng;
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
