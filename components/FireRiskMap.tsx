"use client";

import { Loader } from "@googlemaps/js-api-loader";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bounds,
  Building,
  fetchBuildings,
  fetchWildland,
  Wildland,
} from "@/lib/overpass";
import {
  classifyBuilding,
  DEFAULT_THRESHOLDS,
  RISK_COLORS,
  RISK_LABELS,
  RiskLevel,
  RiskThresholds,
  RiskZone,
} from "@/lib/risk";

const FOREST_COLOR = "#2f7d32";

const API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;

// Centre par défaut : Provence (zone fortement exposée aux feux de forêt).
const DEFAULT_CENTER = { lat: 43.7102, lng: 7.262 };
const DEFAULT_ZOOM = 15;
const MIN_LOAD_ZOOM = 14;

type Status = { text: string; kind: "info" | "error" | "success" };

let zoneCounter = 0;

export default function FireRiskMap() {
  const mapRef = useRef<HTMLDivElement>(null);
  const gmapRef = useRef<google.maps.Map | null>(null);
  // Polygones Google indexés par id de bâtiment.
  const polygonsRef = useRef<Map<number, google.maps.Polygon>>(new Map());
  // Cercles Google indexés par id de zone à risque.
  const circlesRef = useRef<Map<string, google.maps.Circle>>(new Map());

  // Polygones Google des forêts indexés par id.
  const forestPolysRef = useRef<Map<number, google.maps.Polygon>>(new Map());

  const buildingsRef = useRef<Building[]>([]);
  const zonesRef = useRef<RiskZone[]>([]);
  const forestsRef = useRef<Wildland[]>([]);
  const addModeRef = useRef(false);
  const radiusRef = useRef(400);
  const thresholdsRef = useRef<RiskThresholds>(DEFAULT_THRESHOLDS);

  const [ready, setReady] = useState(false);
  const [addMode, setAddMode] = useState(false);
  const [radius, setRadius] = useState(400);
  const [thresholds, setThresholds] = useState<RiskThresholds>(DEFAULT_THRESHOLDS);
  const [loading, setLoading] = useState(false);
  const [loadingForests, setLoadingForests] = useState(false);
  const [status, setStatus] = useState<Status>({
    text: "Chargez les habitats, puis les forêts (risque auto) ou posez des zones à risque à la main.",
    kind: "info",
  });
  const [counts, setCounts] = useState({ total: 0, red: 0, orange: 0, blue: 0 });
  const [zoneCount, setZoneCount] = useState(0);
  const [forestCount, setForestCount] = useState(0);

  addModeRef.current = addMode;
  radiusRef.current = radius;
  thresholdsRef.current = thresholds;

  /** Recalcule et applique la couleur de chaque habitat. */
  const recolor = useCallback(() => {
    const tally: Record<RiskLevel, number> = { red: 0, orange: 0, blue: 0 };
    for (const b of buildingsRef.current) {
      const { level } = classifyBuilding(
        b.center,
        zonesRef.current,
        forestsRef.current,
        thresholdsRef.current
      );
      tally[level] += 1;
      const poly = polygonsRef.current.get(b.id);
      if (poly) {
        poly.setOptions({
          fillColor: RISK_COLORS[level],
          strokeColor: RISK_COLORS[level],
        });
      }
    }
    setCounts({
      total: buildingsRef.current.length,
      red: tally.red,
      orange: tally.orange,
      blue: tally.blue,
    });
  }, []);

  const addZone = useCallback(
    (center: { lat: number; lng: number }) => {
      const map = gmapRef.current;
      if (!map) return;
      const id = `zone-${++zoneCounter}`;
      const zone: RiskZone = { id, center, radiusM: radiusRef.current };
      zonesRef.current = [...zonesRef.current, zone];

      const circle = new google.maps.Circle({
        map,
        center,
        radius: zone.radiusM,
        editable: true,
        draggable: true,
        fillColor: "#e63946",
        fillOpacity: 0.12,
        strokeColor: "#e63946",
        strokeOpacity: 0.8,
        strokeWeight: 2,
        zIndex: 5,
      });
      circlesRef.current.set(id, circle);

      const sync = () => {
        const c = circle.getCenter();
        if (!c) return;
        const idx = zonesRef.current.findIndex((z) => z.id === id);
        if (idx >= 0) {
          zonesRef.current[idx] = {
            id,
            center: { lat: c.lat(), lng: c.lng() },
            radiusM: circle.getRadius(),
          };
          recolor();
        }
      };
      circle.addListener("radius_changed", sync);
      circle.addListener("center_changed", sync);
      circle.addListener("dragend", sync);
      // Clic droit sur un cercle : le supprimer.
      circle.addListener("contextmenu", () => removeZone(id));

      setZoneCount(zonesRef.current.length);
      recolor();
    },
    [recolor]
  );

  const removeZone = useCallback(
    (id: string) => {
      const circle = circlesRef.current.get(id);
      if (circle) {
        circle.setMap(null);
        circlesRef.current.delete(id);
      }
      zonesRef.current = zonesRef.current.filter((z) => z.id !== id);
      setZoneCount(zonesRef.current.length);
      recolor();
    },
    [recolor]
  );

  const clearZones = useCallback(() => {
    for (const circle of circlesRef.current.values()) circle.setMap(null);
    circlesRef.current.clear();
    zonesRef.current = [];
    setZoneCount(0);
    recolor();
  }, [recolor]);

  /** Charge les habitats visibles dans la carte via Overpass. */
  const loadBuildings = useCallback(async () => {
    const map = gmapRef.current;
    if (!map) return;
    const zoom = map.getZoom() ?? 0;
    if (zoom < MIN_LOAD_ZOOM) {
      setStatus({
        text: "Zoomez davantage avant de charger les habitats (la zone est trop vaste).",
        kind: "error",
      });
      return;
    }
    const b = map.getBounds();
    if (!b) return;
    const ne = b.getNorthEast();
    const sw = b.getSouthWest();
    const bounds: Bounds = {
      south: sw.lat(),
      west: sw.lng(),
      north: ne.lat(),
      east: ne.lng(),
    };

    setLoading(true);
    setStatus({ text: "Chargement des habitats…", kind: "info" });
    try {
      const buildings = await fetchBuildings(bounds);

      // On efface les anciens polygones.
      for (const poly of polygonsRef.current.values()) poly.setMap(null);
      polygonsRef.current.clear();

      for (const building of buildings) {
        const poly = new google.maps.Polygon({
          map,
          paths: building.ring,
          fillColor: RISK_COLORS.blue,
          fillOpacity: 0.55,
          strokeColor: RISK_COLORS.blue,
          strokeOpacity: 0.9,
          strokeWeight: 1,
          zIndex: 2,
        });
        polygonsRef.current.set(building.id, poly);
      }
      buildingsRef.current = buildings;
      recolor();
      setStatus({
        text:
          buildings.length > 0
            ? `${buildings.length} habitats chargés.`
            : "Aucun habitat trouvé dans cette zone.",
        kind: buildings.length > 0 ? "success" : "error",
      });
    } catch (err) {
      setStatus({
        text:
          "Échec du chargement des habitats. Réessayez dans un instant (Overpass est parfois saturé).",
        kind: "error",
      });
      // eslint-disable-next-line no-console
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [recolor]);

  /** Charge automatiquement les forêts/zones boisées (foyers de risque). */
  const loadForests = useCallback(async () => {
    const map = gmapRef.current;
    if (!map) return;
    const zoom = map.getZoom() ?? 0;
    if (zoom < MIN_LOAD_ZOOM) {
      setStatus({
        text: "Zoomez davantage avant de charger les forêts (la zone est trop vaste).",
        kind: "error",
      });
      return;
    }
    const b = map.getBounds();
    if (!b) return;
    const ne = b.getNorthEast();
    const sw = b.getSouthWest();
    const bounds: Bounds = {
      south: sw.lat(),
      west: sw.lng(),
      north: ne.lat(),
      east: ne.lng(),
    };

    setLoadingForests(true);
    setStatus({ text: "Chargement des forêts / zones boisées…", kind: "info" });
    try {
      const forests = await fetchWildland(bounds);

      for (const poly of forestPolysRef.current.values()) poly.setMap(null);
      forestPolysRef.current.clear();

      for (const forest of forests) {
        const poly = new google.maps.Polygon({
          map,
          paths: forest.ring,
          fillColor: FOREST_COLOR,
          fillOpacity: 0.18,
          strokeColor: FOREST_COLOR,
          strokeOpacity: 0.6,
          strokeWeight: 1,
          clickable: false,
          zIndex: 1,
        });
        forestPolysRef.current.set(forest.id, poly);
      }
      forestsRef.current = forests;
      setForestCount(forests.length);
      recolor();
      setStatus({
        text:
          forests.length > 0
            ? `${forests.length} zones boisées chargées : risque calculé automatiquement.`
            : "Aucune forêt trouvée ici. Posez des zones à risque à la main.",
        kind: forests.length > 0 ? "success" : "info",
      });
    } catch (err) {
      setStatus({
        text: "Échec du chargement des forêts. Réessayez dans un instant.",
        kind: "error",
      });
      // eslint-disable-next-line no-console
      console.error(err);
    } finally {
      setLoadingForests(false);
    }
  }, [recolor]);

  const clearForests = useCallback(() => {
    for (const poly of forestPolysRef.current.values()) poly.setMap(null);
    forestPolysRef.current.clear();
    forestsRef.current = [];
    setForestCount(0);
    recolor();
  }, [recolor]);

  // Initialisation de la carte Google Maps.
  useEffect(() => {
    if (!API_KEY || !mapRef.current) return;
    let cancelled = false;

    const loader = new Loader({ apiKey: API_KEY, version: "weekly" });
    loader
      .importLibrary("maps")
      .then(({ Map }) => {
        if (cancelled || !mapRef.current) return;
        const map = new Map(mapRef.current, {
          center: DEFAULT_CENTER,
          zoom: DEFAULT_ZOOM,
          mapTypeId: "hybrid",
          streetViewControl: false,
          mapTypeControl: true,
          fullscreenControl: false,
          clickableIcons: false,
        });
        gmapRef.current = map;

        map.addListener("click", (e: google.maps.MapMouseEvent) => {
          if (!addModeRef.current || !e.latLng) return;
          addZone({ lat: e.latLng.lat(), lng: e.latLng.lng() });
        });

        setReady(true);
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error(err);
        setStatus({
          text: "Impossible de charger Google Maps. Vérifiez votre clé API.",
          kind: "error",
        });
      });

    return () => {
      cancelled = true;
    };
  }, [addZone]);

  // Recolore les habitats dès que les seuils de danger changent.
  useEffect(() => {
    recolor();
  }, [thresholds, recolor]);

  if (!API_KEY) {
    return <MissingKeyScreen />;
  }

  return (
    <div style={styles.wrapper}>
      <div ref={mapRef} style={styles.map} />

      <div style={styles.panel}>
        <h1 style={styles.title}>🔥 Habitats & risque incendie</h1>

        <button
          onClick={loadBuildings}
          disabled={!ready || loading}
          style={{ ...styles.button, ...styles.primaryButton }}
        >
          {loading ? "Chargement…" : "1. Charger les habitats de cette zone"}
        </button>

        <button
          onClick={loadForests}
          disabled={!ready || loadingForests}
          style={{ ...styles.button, ...styles.forestButton }}
        >
          {loadingForests
            ? "Chargement…"
            : "2. Charger les forêts (risque auto) 🌲"}
        </button>
        {forestCount > 0 && (
          <button
            onClick={clearForests}
            style={{ ...styles.button, ...styles.secondaryButton }}
          >
            Retirer les forêts ({forestCount})
          </button>
        )}

        <div style={styles.field}>
          <label style={styles.fieldLabel}>
            Seuil « risque élevé » (rouge) : <strong>≤ {thresholds.redM} m</strong>
          </label>
          <input
            type="range"
            min={0}
            max={1000}
            step={25}
            value={thresholds.redM}
            onChange={(e) => {
              const redM = Number(e.target.value);
              setThresholds((t) => ({
                redM,
                orangeM: Math.max(redM, t.orangeM),
              }));
            }}
            style={{ width: "100%" }}
          />
          <label style={styles.fieldLabel}>
            Seuil « risque modéré » (orange) : <strong>≤ {thresholds.orangeM} m</strong>
          </label>
          <input
            type="range"
            min={0}
            max={2500}
            step={25}
            value={thresholds.orangeM}
            onChange={(e) => {
              const orangeM = Number(e.target.value);
              setThresholds((t) => ({
                orangeM,
                redM: Math.min(orangeM, t.redM),
              }));
            }}
            style={{ width: "100%" }}
          />
        </div>

        <hr style={styles.divider} />
        <p style={styles.sectionTitle}>Zones à risque manuelles (optionnel)</p>

        <label style={styles.toggle}>
          <input
            type="checkbox"
            checked={addMode}
            onChange={(e) => setAddMode(e.target.checked)}
          />
          <span>
            Mode « ajouter une zone à risque »
            <br />
            <small style={styles.muted}>
              {addMode
                ? "Cliquez sur la carte pour placer une zone."
                : "Activez, puis cliquez sur la carte."}
            </small>
          </span>
        </label>

        <div style={styles.field}>
          <label style={styles.fieldLabel}>
            Rayon de la zone à risque : <strong>{radius} m</strong>
          </label>
          <input
            type="range"
            min={100}
            max={2000}
            step={50}
            value={radius}
            onChange={(e) => setRadius(Number(e.target.value))}
            style={{ width: "100%" }}
          />
        </div>

        <button
          onClick={clearZones}
          disabled={zoneCount === 0}
          style={{ ...styles.button, ...styles.secondaryButton }}
        >
          Effacer les zones ({zoneCount})
        </button>

        <p style={{ ...styles.status, ...statusStyle(status.kind) }}>
          {status.text}
        </p>

        {counts.total > 0 && (
          <div style={styles.counts}>
            <Legend color={RISK_COLORS.red} label={RISK_LABELS.red} n={counts.red} />
            <Legend
              color={RISK_COLORS.orange}
              label={RISK_LABELS.orange}
              n={counts.orange}
            />
            <Legend
              color={RISK_COLORS.blue}
              label={RISK_LABELS.blue}
              n={counts.blue}
            />
          </div>
        )}

        <p style={styles.hint}>
          Astuce : les zones sont déplaçables et redimensionnables. Clic droit sur
          une zone pour la supprimer.
        </p>
      </div>
    </div>
  );
}

function Legend({
  color,
  label,
  n,
}: {
  color: string;
  label: string;
  n: number;
}) {
  return (
    <div style={styles.legendRow}>
      <span style={{ ...styles.swatch, background: color }} />
      <span style={styles.legendLabel}>{label}</span>
      <span style={styles.legendCount}>{n}</span>
    </div>
  );
}

function MissingKeyScreen() {
  return (
    <div style={styles.missingWrapper}>
      <div style={styles.missingCard}>
        <h1 style={{ marginTop: 0 }}>🔥 Habitats & risque incendie</h1>
        <p>
          Cette application a besoin d&apos;une clé <strong>Google Maps
          JavaScript API</strong> pour afficher la carte.
        </p>
        <ol style={{ lineHeight: 1.6 }}>
          <li>
            Créez une clé sur{" "}
            <a href="https://console.cloud.google.com/google/maps-apis" target="_blank" rel="noreferrer">
              Google Cloud Console
            </a>{" "}
            (activez « Maps JavaScript API »).
          </li>
          <li>
            Ajoutez la variable d&apos;environnement suivante (localement dans un
            fichier <code>.env.local</code>, ou dans les réglages du projet Vercel) :
          </li>
        </ol>
        <pre style={styles.pre}>NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=votre_cle_ici</pre>
        <p style={styles.muted}>
          Puis relancez le serveur (ou redéployez sur Vercel).
        </p>
      </div>
    </div>
  );
}

function statusStyle(kind: Status["kind"]): React.CSSProperties {
  if (kind === "error") return { background: "#fdecea", color: "#8a1c13" };
  if (kind === "success") return { background: "#e7f6f2", color: "#0f5f52" };
  return { background: "#eef2f7", color: "#334" };
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: { position: "relative", height: "100%", width: "100%" },
  map: { position: "absolute", inset: 0 },
  panel: {
    position: "absolute",
    top: 16,
    left: 16,
    width: 320,
    maxWidth: "calc(100vw - 32px)",
    maxHeight: "calc(100% - 32px)",
    overflowY: "auto",
    background: "rgba(255,255,255,0.96)",
    borderRadius: 14,
    boxShadow: "0 8px 30px rgba(0,0,0,0.18)",
    padding: 16,
    zIndex: 10,
    backdropFilter: "blur(4px)",
  },
  title: { fontSize: 18, margin: "0 0 12px" },
  button: {
    width: "100%",
    padding: "10px 12px",
    borderRadius: 10,
    border: "none",
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
    marginBottom: 10,
  },
  primaryButton: { background: "#1d6fb8", color: "#fff" },
  forestButton: { background: "#2f7d32", color: "#fff" },
  secondaryButton: { background: "#eef2f7", color: "#33475b" },
  divider: {
    border: "none",
    borderTop: "1px solid #e4e8ee",
    margin: "6px 0 10px",
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: 0.4,
    color: "#6b7785",
    margin: "0 0 10px",
  },
  toggle: {
    display: "flex",
    gap: 8,
    alignItems: "flex-start",
    fontSize: 14,
    marginBottom: 12,
    cursor: "pointer",
  },
  field: { marginBottom: 12 },
  fieldLabel: { fontSize: 13, display: "block", marginBottom: 6 },
  muted: { color: "#6b7785" },
  status: {
    fontSize: 13,
    padding: "8px 10px",
    borderRadius: 8,
    margin: "4px 0 12px",
  },
  counts: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
    marginBottom: 12,
  },
  legendRow: { display: "flex", alignItems: "center", gap: 8, fontSize: 13 },
  swatch: {
    width: 16,
    height: 16,
    borderRadius: 4,
    flexShrink: 0,
    display: "inline-block",
  },
  legendLabel: { flex: 1 },
  legendCount: { fontWeight: 700 },
  hint: { fontSize: 12, color: "#6b7785", margin: 0, lineHeight: 1.5 },
  missingWrapper: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    height: "100%",
    padding: 24,
    background: "#f3f5f8",
  },
  missingCard: {
    maxWidth: 560,
    background: "#fff",
    padding: 28,
    borderRadius: 16,
    boxShadow: "0 8px 30px rgba(0,0,0,0.12)",
    fontSize: 15,
    lineHeight: 1.5,
  },
  pre: {
    background: "#1d2733",
    color: "#e6edf3",
    padding: "12px 14px",
    borderRadius: 8,
    overflowX: "auto",
    fontSize: 13,
  },
};
