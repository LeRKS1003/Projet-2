import { haversineMeters, LatLng } from "./geo";

/** Une zone à risque incendie : un centre et un rayon de danger (en mètres). */
export interface RiskZone {
  id: string;
  center: LatLng;
  /** Rayon du coeur de la zone à risque, en mètres. */
  radiusM: number;
}

export type RiskLevel = "red" | "orange" | "blue";

export const RISK_COLORS: Record<RiskLevel, string> = {
  red: "#e63946", // très proche d'une zone à risque
  orange: "#f4a261", // proximité modérée
  blue: "#2a9d8f", // éloigné / faible risque
};

export const RISK_LABELS: Record<RiskLevel, string> = {
  red: "Risque élevé",
  orange: "Risque modéré",
  blue: "Risque faible",
};

/**
 * Classe un habitat selon sa distance à la zone à risque la plus proche.
 *
 * - rouge  : à l'intérieur du rayon de la zone (distance <= R)
 * - orange : dans la couronne d'approche (R < distance <= R * orangeFactor)
 * - bleu   : au-delà (faible risque)
 *
 * S'il n'y a aucune zone à risque, tout est bleu.
 */
export function classifyBuilding(
  point: LatLng,
  zones: RiskZone[],
  orangeFactor = 2.5
): { level: RiskLevel; nearestZoneId: string | null; distanceM: number } {
  if (zones.length === 0) {
    return { level: "blue", nearestZoneId: null, distanceM: Infinity };
  }

  let nearestZoneId: string | null = null;
  let bestLevel: RiskLevel = "blue";
  let bestDistance = Infinity;
  // Un score numérique pour comparer : plus c'est petit, plus c'est dangereux.
  let bestRank = 3;

  for (const zone of zones) {
    const distance = haversineMeters(point, zone.center);
    let level: RiskLevel;
    if (distance <= zone.radiusM) {
      level = "red";
    } else if (distance <= zone.radiusM * orangeFactor) {
      level = "orange";
    } else {
      level = "blue";
    }

    const rank = level === "red" ? 0 : level === "orange" ? 1 : 2;
    if (rank < bestRank || (rank === bestRank && distance < bestDistance)) {
      bestRank = rank;
      bestLevel = level;
      bestDistance = distance;
      nearestZoneId = zone.id;
    }
  }

  return { level: bestLevel, nearestZoneId, distanceM: bestDistance };
}
