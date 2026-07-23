import {
  distanceToBBoxMeters,
  distanceToPolygonMeters,
  haversineMeters,
  LatLng,
} from "./geo";
import { Wildland } from "./overpass";

/** Une zone à risque incendie dessinée à la main : un centre et un rayon (m). */
export interface RiskZone {
  id: string;
  center: LatLng;
  /** Rayon de l'emprise de la zone à risque, en mètres. */
  radiusM: number;
}

export type RiskLevel = "red" | "orange" | "blue";

/** Seuils de danger (distance au bord du foyer de risque le plus proche). */
export interface RiskThresholds {
  /** À cette distance ou moins (ou à l'intérieur) : rouge. */
  redM: number;
  /** À cette distance ou moins : orange. Au-delà : bleu. */
  orangeM: number;
}

export const DEFAULT_THRESHOLDS: RiskThresholds = { redM: 100, orangeM: 500 };

export const RISK_COLORS: Record<RiskLevel, string> = {
  red: "#e63946", // à l'intérieur / au contact d'un foyer de risque
  orange: "#f4a261", // proximité modérée
  blue: "#2a9d8f", // éloigné / faible risque
};

export const RISK_LABELS: Record<RiskLevel, string> = {
  red: "Risque élevé",
  orange: "Risque modéré",
  blue: "Risque faible",
};

function levelFromDistance(distanceM: number, t: RiskThresholds): RiskLevel {
  if (distanceM <= t.redM) return "red";
  if (distanceM <= t.orangeM) return "orange";
  return "blue";
}

/**
 * Classe un habitat selon sa distance au foyer de risque le plus proche.
 *
 * Les foyers de risque sont de deux natures, traités de la même façon :
 *  - les **zones manuelles** (cercles), distance = distance au bord du cercle ;
 *  - les **zones boisées** (forêts OSM), distance = distance au bord du polygone.
 *
 * La distance retenue est la plus petite des deux (le danger le plus proche).
 * Sans aucun foyer de risque, tout est bleu.
 */
export function classifyBuilding(
  point: LatLng,
  zones: RiskZone[],
  forests: Wildland[],
  thresholds: RiskThresholds
): { level: RiskLevel; distanceM: number } {
  let best = Infinity;

  for (const zone of zones) {
    // Distance au bord du cercle (0 si à l'intérieur).
    const d = Math.max(0, haversineMeters(point, zone.center) - zone.radiusM);
    if (d < best) best = d;
    if (best === 0) break;
  }

  if (best > 0) {
    for (const forest of forests) {
      // Filtre grossier : si même le rectangle englobant est plus loin
      // que le meilleur candidat, inutile de calculer la distance exacte.
      if (distanceToBBoxMeters(point, forest.bbox) >= best) continue;
      const d = distanceToPolygonMeters(point, forest.ring);
      if (d < best) best = d;
      if (best === 0) break;
    }
  }

  if (best === Infinity) return { level: "blue", distanceM: Infinity };
  return { level: levelFromDistance(best, thresholds), distanceM: best };
}
