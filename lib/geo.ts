export interface LatLng {
  lat: number;
  lng: number;
}

const EARTH_RADIUS_M = 6371000;

/** Distance en mètres entre deux points (formule de Haversine). */
export function haversineMeters(a: LatLng, b: LatLng): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);

  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Centroïde (moyenne) d'un anneau de coordonnées. */
export function centroid(ring: LatLng[]): LatLng {
  if (ring.length === 0) return { lat: 0, lng: 0 };
  let lat = 0;
  let lng = 0;
  for (const p of ring) {
    lat += p.lat;
    lng += p.lng;
  }
  return { lat: lat / ring.length, lng: lng / ring.length };
}

export interface BBox {
  south: number;
  west: number;
  north: number;
  east: number;
}

/** Rectangle englobant d'un anneau de coordonnées. */
export function ringBBox(ring: LatLng[]): BBox {
  let south = Infinity;
  let west = Infinity;
  let north = -Infinity;
  let east = -Infinity;
  for (const p of ring) {
    if (p.lat < south) south = p.lat;
    if (p.lat > north) north = p.lat;
    if (p.lng < west) west = p.lng;
    if (p.lng > east) east = p.lng;
  }
  return { south, west, north, east };
}

/**
 * Distance approximative (m) d'un point au rectangle englobant.
 * Sert de filtre grossier bon marché avant le calcul exact au polygone.
 * Renvoie 0 si le point est à l'intérieur du rectangle.
 */
export function distanceToBBoxMeters(p: LatLng, box: BBox): number {
  const dLat = Math.max(box.south - p.lat, 0, p.lat - box.north);
  const dLng = Math.max(box.west - p.lng, 0, p.lng - box.east);
  if (dLat === 0 && dLng === 0) return 0;
  const mPerDegLat = 111320;
  const mPerDegLng = 111320 * Math.cos((p.lat * Math.PI) / 180);
  return Math.hypot(dLat * mPerDegLat, dLng * mPerDegLng);
}

/** Test d'appartenance d'un point à un polygone (lancer de rayon). */
export function pointInRing(p: LatLng, ring: LatLng[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const yi = ring[i].lat;
    const xi = ring[i].lng;
    const yj = ring[j].lat;
    const xj = ring[j].lng;
    const intersect =
      yi > p.lat !== yj > p.lat &&
      p.lng < ((xj - xi) * (p.lat - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

/** Distance (m) d'un point à un segment, en projection équirectangulaire locale. */
function distanceToSegmentMeters(p: LatLng, a: LatLng, b: LatLng): number {
  const latRef = (p.lat * Math.PI) / 180;
  const mPerDegLat = 111320;
  const mPerDegLng = 111320 * Math.cos(latRef);
  const px = p.lng * mPerDegLng;
  const py = p.lat * mPerDegLat;
  const ax = a.lng * mPerDegLng;
  const ay = a.lat * mPerDegLat;
  const bx = b.lng * mPerDegLng;
  const by = b.lat * mPerDegLat;

  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy;
  let t = len2 === 0 ? 0 : ((px - ax) * dx + (py - ay) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  const cx = ax + t * dx;
  const cy = ay + t * dy;
  return Math.hypot(px - cx, py - cy);
}

/**
 * Distance (m) d'un point à un polygone.
 * Renvoie 0 si le point est à l'intérieur ; sinon la distance au bord le plus proche.
 */
export function distanceToPolygonMeters(p: LatLng, ring: LatLng[]): number {
  if (ring.length < 3) return Infinity;
  if (pointInRing(p, ring)) return 0;
  let min = Infinity;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const d = distanceToSegmentMeters(p, ring[j], ring[i]);
    if (d < min) min = d;
  }
  return min;
}
