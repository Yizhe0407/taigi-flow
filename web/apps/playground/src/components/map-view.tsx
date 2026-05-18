"use client";

import { useEffect, useImperativeHandle, useRef, forwardRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

// Yunlin county center
const YUNLIN_CENTER: [number, number] = [120.4, 23.7];

const CARTO_DARK_MATTER_STYLE =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

export type MapHandle = {
  focusOn: (lng: number, lat: number, zoom?: number) => void;
  drawRoute: (coords: [number, number][]) => void;
  showStops: (stops: { name: string; lng: number; lat: number }[]) => void;
  clearOverlays: () => void;
};

type Props = {
  center?: [number, number];
  zoom?: number;
  className?: string;
};

const MapView = forwardRef<MapHandle, Props>(function MapView(
  { center = YUNLIN_CENTER, zoom = 10, className = "" },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: CARTO_DARK_MATTER_STYLE,
      center,
      zoom,
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;

    map.on("load", () => {
      for (const layer of map.getStyle().layers ?? []) {
        if (layer.type === "symbol" && map.getLayoutProperty(layer.id, "text-field")) {
          map.setLayoutProperty(layer.id, "text-field", [
            "coalesce",
            ["get", "name:zh-Hant"],
            ["get", "name:zh"],
            ["get", "name"],
          ]);
        }
      }
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useImperativeHandle(ref, () => ({
    focusOn(lng, lat, z = 14) {
      mapRef.current?.flyTo({ center: [lng, lat], zoom: z });
    },

    drawRoute(coords) {
      const map = mapRef.current;
      if (!map) return;

      if (map.getLayer("route")) map.removeLayer("route");
      if (map.getSource("route")) map.removeSource("route");

      map.addSource("route", {
        type: "geojson",
        data: {
          type: "Feature",
          properties: {},
          geometry: { type: "LineString", coordinates: coords },
        },
      });
      map.addLayer({
        id: "route",
        type: "line",
        source: "route",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#38bdf8", "line-width": 4 },
      });

      const bounds = coords.reduce(
        (b, c) => b.extend(c as [number, number]),
        new maplibregl.LngLatBounds(coords[0], coords[0]),
      );
      map.fitBounds(bounds, { padding: 40 });
    },

    showStops(stops) {
      const map = mapRef.current;
      if (!map) return;

      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];

      stops.forEach((stop) => {
        const el = document.createElement("div");
        el.className =
          "w-3 h-3 rounded-full border-2 border-white bg-sky-400 shadow-sm";

        const marker = new maplibregl.Marker({ element: el })
          .setLngLat([stop.lng, stop.lat])
          .setPopup(new maplibregl.Popup({ offset: 10 }).setText(stop.name))
          .addTo(map);

        markersRef.current.push(marker);
      });
    },

    clearOverlays() {
      const map = mapRef.current;
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      if (map?.getLayer("route")) map.removeLayer("route");
      if (map?.getSource("route")) map.removeSource("route");
    },
  }));

  return (
    <div
      ref={containerRef}
      className={`overflow-hidden rounded-lg ${className}`}
    />
  );
});

export default MapView;
