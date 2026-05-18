"use client";

import type { MediaDeviceFailure } from "livekit-client";
import {
  BarVisualizer,
  DisconnectButton,
  LiveKitRoom,
  RoomAudioRenderer,
  StartAudio,
  useConnectionState,
  useLocalParticipant,
  useRoomContext,
  useVoiceAssistant,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { RoomEvent } from "livekit-client";
import {
  ArrowLeft,
  Mic,
  MicOff,
  Moon,
  PhoneOff,
  RotateCcw,
  Sun,
  User,
} from "lucide-react";
import dynamic from "next/dynamic";
import { useTheme } from "next-themes";
import { useCallback, useEffect, useRef, useState } from "react";
import type { MapHandle } from "@/components/map-view";
import { Button } from "@/components/ui/button";

const MapView = dynamic(() => import("@/components/map-view"), { ssr: false });

// ─── Types ───────────────────────────────────────────────────────────────────

type DispatchStatus = "unknown" | "ok" | "unavailable";

type ConnectionDetails = {
  token: string;
  url: string;
  roomName?: string;
};

type MapPayload =
  | { type: "bus.route_stops"; route: string; stops: { name: string; lat: number; lng: number; sequence: number }[] }
  | { type: "map.route"; from: { lat: number; lng: number }; to: { lat: number; lng: number }; coords: [number, number][]; distance_m: number; duration_s: number }
  | { type: "map.poi"; center: { lat: number; lng: number }; items: { name: string; lat: number; lng: number }[] }
  | { type: "map.focus"; lat: number; lng: number; zoom?: number };

type ConvTurn = { role: "user" | "agent"; text: string; id: number; streaming?: boolean };

// ─── Helpers ─────────────────────────────────────────────────────────────────

function normalizeLiveKitUrl(rawUrl: string): string {
  if (typeof window === "undefined") return rawUrl;
  try {
    const parsed = new URL(rawUrl);
    const localHosts = new Set(["localhost", "127.0.0.1", "::1"]);
    const isServerUrlLocal = localHosts.has(parsed.hostname);
    const isCurrentHostLocal = localHosts.has(window.location.hostname);
    if (isServerUrlLocal && !isCurrentHostLocal) parsed.hostname = window.location.hostname;
    if (window.location.protocol === "https:" && parsed.protocol === "ws:") parsed.protocol = "wss:";
    return parsed.toString();
  } catch {
    return rawUrl;
  }
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <Button variant="outline" size="icon" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="切換主題">
      <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
    </Button>
  );
}

// ─── Map panel (data channel + MapView) ──────────────────────────────────────

function MapPanel({ gpsLocation, className }: { gpsLocation: { lat: number; lng: number } | null; className?: string }) {
  const room = useRoomContext();
  const connectionState = useConnectionState();
  const mapRef = useRef<MapHandle>(null);

  useEffect(() => {
    if (!gpsLocation || connectionState !== "connected") return;
    const payload = JSON.stringify({ type: "client.location", ...gpsLocation });
    void room.localParticipant.publishData(new TextEncoder().encode(payload), { reliable: true, topic: "map" });
  }, [connectionState, gpsLocation, room]);

  useEffect(() => {
    const handler = (payload: Uint8Array) => {
      try {
        const msg = JSON.parse(new TextDecoder().decode(payload)) as MapPayload;
        switch (msg.type) {
          case "bus.route_stops":
            mapRef.current?.showStops(msg.stops);
            if (msg.stops[0]) mapRef.current?.focusOn(msg.stops[0].lng, msg.stops[0].lat, 12);
            break;
          case "map.route":
            mapRef.current?.drawRoute(msg.coords);
            break;
          case "map.poi":
            mapRef.current?.showStops(msg.items);
            mapRef.current?.focusOn(msg.center.lng, msg.center.lat, 13);
            break;
          case "map.focus":
            mapRef.current?.focusOn(msg.lng, msg.lat, msg.zoom);
            break;
        }
      } catch { /* ignore */ }
    };
    room.on(RoomEvent.DataReceived, handler);
    return () => { room.off(RoomEvent.DataReceived, handler); };
  }, [room]);

  return <MapView ref={mapRef} className={className} />;
}

// ─── Split layout (connected state) ──────────────────────────────────────────

const STATE_LABEL: Record<string, string> = {
  idle:     "待機中",
  thinking: "思考中",
  speaking: "說話中",
};

const STATE_COLOR: Record<string, string> = {
  thinking: "bg-yellow-400",
  speaking: "bg-blue-400",
};

function SplitLayout({
  connected,
  onBackToStart,
  gpsLocation,
}: {
  connected: boolean;
  onBackToStart: () => void;
  gpsLocation: { lat: number; lng: number } | null;
}) {
  const { audioTrack } = useVoiceAssistant();
  const { isMicrophoneEnabled, localParticipant, microphoneTrack } = useLocalParticipant();
  const room = useRoomContext();
  const [turns, setTurns] = useState<ConvTurn[]>([]);
  const [agentPhase, setAgentPhase] = useState<"idle" | "thinking" | "speaking">("idle");
  const turnIdRef = useRef(0);
  const logEndRef = useRef<HTMLDivElement>(null);
  const pendingRef = useRef("");
  const agentDoneRef = useRef(false);

  useEffect(() => {
    if (!connected || isMicrophoneEnabled) return;
    void localParticipant.setMicrophoneEnabled(true).catch(() => {});
  }, [connected, isMicrophoneEnabled, localParticipant]);

  // Typewriter: drain pendingRef char by char
  useEffect(() => {
    const id = setInterval(() => {
      if (pendingRef.current.length > 0) {
        // Pop one char (or two if buffer is large, to avoid lag)
        const n = pendingRef.current.length > 40 ? 2 : 1;
        const chars = pendingRef.current.slice(0, n);
        pendingRef.current = pendingRef.current.slice(n);
        setTurns((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "agent" && last.streaming) {
            return [...prev.slice(0, -1), { ...last, text: last.text + chars }];
          }
          return [...prev, { role: "agent", text: chars, id: ++turnIdRef.current, streaming: true }];
        });
      } else if (agentDoneRef.current) {
        agentDoneRef.current = false;
        setTurns((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "agent" && last.streaming) {
            return [...prev.slice(0, -1), { ...last, streaming: false }];
          }
          return prev;
        });
      }
    }, 150);
    return () => clearInterval(id);
  }, []);

  // Data channel: buffer incoming text, don't mutate turns directly
  useEffect(() => {
    const handler = (payload: Uint8Array) => {
      try {
        const msg = JSON.parse(new TextDecoder().decode(payload)) as { type: string; text?: string };
        if (msg.type === "conv.user") {
          if (pendingRef.current) {
            setTurns((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role === "agent" && last.streaming) {
                return [...prev.slice(0, -1), { ...last, text: last.text + pendingRef.current, streaming: false }];
              }
              return prev;
            });
            pendingRef.current = "";
            agentDoneRef.current = false;
          }
          setAgentPhase("thinking");
          setTurns((prev) => [...prev, { role: "user", text: msg.text ?? "", id: ++turnIdRef.current }]);
        } else if (msg.type === "conv.agent_chunk") {
          setAgentPhase("speaking");
          pendingRef.current += msg.text ?? "";
        } else if (msg.type === "conv.agent_done") {
          agentDoneRef.current = true;
          setAgentPhase("idle");
        }
      } catch { /* ignore */ }
    };
    room.on(RoomEvent.DataReceived, handler);
    return () => { room.off(RoomEvent.DataReceived, handler); };
  }, [room]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const dotColor = STATE_COLOR[agentPhase] ?? "bg-muted-foreground/40";
  const stateLabel = STATE_LABEL[agentPhase] ?? agentPhase;

  return (
    <div className="flex h-screen w-full overflow-hidden">

      {/* ── Left: Map 3/4 ── */}
      <div className="flex-[3] relative min-h-0">
        <MapPanel gpsLocation={gpsLocation} className="h-full w-full" />
        {gpsLocation && (
          <span className="absolute bottom-2 left-2 rounded bg-black/50 px-2 py-0.5 text-[10px] text-white/70 font-mono">
            {gpsLocation.lat.toFixed(4)}, {gpsLocation.lng.toFixed(4)}
          </span>
        )}
      </div>

      {/* ── Right: 1/4 ── */}
      <div className="flex-1 flex flex-col border-l bg-background min-w-0 min-h-0">

        {/* Avatar area — reserved for virtual human */}
        <div className="flex-[2] flex flex-col items-center justify-center gap-3 border-b p-4">
          <div className="flex h-24 w-24 items-center justify-center rounded-full border-2 border-dashed border-muted-foreground/30 text-muted-foreground/30">
            <User className="h-10 w-10" />
          </div>
          <p className="text-xs text-muted-foreground/50">虛擬人</p>
          {/* Agent voice waveform */}
          {audioTrack && (
            <BarVisualizer
              track={audioTrack}
              barCount={7}
              options={{ minHeight: 4 }}
              className="h-8 w-24 [--lk-fg:oklch(0.6_0.15_220)]"
            />
          )}
        </div>

        {/* Conversation log */}
        <div className="flex-[3] overflow-y-auto p-3 flex flex-col gap-2 min-h-0">
          {/* Turn list */}
          {turns.length === 0 ? (
            <p className="text-xs text-muted-foreground/40 text-center mt-4">對話記錄</p>
          ) : (
            turns.map((turn) => (
              <div
                key={turn.id}
                className={`rounded-lg px-3 py-2 text-sm leading-snug max-w-[92%] ${
                  turn.role === "user"
                    ? "self-end bg-primary text-primary-foreground"
                    : "self-start bg-muted text-foreground"
                }`}
              >
                {turn.text}
                {turn.streaming && (
                  <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-current opacity-70 animate-pulse align-middle" />
                )}
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>

        {/* Bottom: state + mic + End button */}
        <div className="shrink-0 border-t p-4 flex flex-col gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className={`h-2 w-2 shrink-0 rounded-full ${dotColor} ${agentPhase !== "idle" ? "animate-pulse" : ""}`} />
            <span className="text-xs text-muted-foreground shrink-0">{stateLabel}</span>
            {microphoneTrack?.track && (
              <BarVisualizer
                track={microphoneTrack.track as Parameters<typeof BarVisualizer>[0]["track"]}
                barCount={7}
                options={{ minHeight: 2 }}
                className="h-4 flex-1 [--lk-fg:oklch(0.723_0.219_149.579)]"
              />
            )}
            <DisconnectButton className="shrink-0 inline-flex items-center justify-center rounded-lg bg-destructive px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-destructive/90">
              <PhoneOff className="mr-1.5 h-3.5 w-3.5" />
              結束對話
            </DisconnectButton>
          </div>
          {!connected && (
            <Button variant="ghost" size="sm" onClick={onBackToStart} className="w-full text-muted-foreground">
              <ArrowLeft className="mr-1 h-3 w-3" />
              返回
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function Playground() {
  const [connectionDetails, setConnectionDetails] = useState<ConnectionDetails | null>(null);
  const [dispatchStatus, setDispatchStatus] = useState<DispatchStatus>("unknown");
  const [dispatchMessage, setDispatchMessage] = useState<string | null>(null);
  const [tokenLoading, setTokenLoading] = useState(false);
  const [sessionStarted, setSessionStarted] = useState(false);
  const [shouldConnect, setShouldConnect] = useState(false);
  const [micPermission, setMicPermission] = useState<"unknown" | "granted" | "denied" | "error">("unknown");
  const [startError, setStartError] = useState<string | null>(null);
  const [roomError, setRoomError] = useState<string | null>(null);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [gpsLocation, setGpsLocation] = useState<{ lat: number; lng: number } | null>(null);

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => setGpsLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => {},
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }, []);

  const requestToken = useCallback(async () => {
    setTokenLoading(true);
    setStartError(null);
    try {
      const res = await fetch("/api/livekit/token", { method: "POST" });
      const data = await res.json();
      if (res.ok && data.token && data.url) {
        const details: ConnectionDetails = {
          token: data.token,
          url: normalizeLiveKitUrl(data.url),
          roomName: typeof data.roomName === "string" ? data.roomName : undefined,
        };
        setConnectionDetails(details);
        setDispatchStatus(data.dispatchStatus === "ok" || data.dispatchStatus === "unavailable" ? data.dispatchStatus : "unknown");
        setDispatchMessage(typeof data.dispatchMessage === "string" ? data.dispatchMessage : null);
        return details;
      } else {
        setStartError(data.error ?? "Failed to get connection token");
      }
    } catch (error) {
      setStartError(error instanceof Error ? error.message : "Failed to get connection token");
    } finally {
      setTokenLoading(false);
    }
    return null;
  }, []);

  const onConnectButtonClicked = useCallback(async () => {
    setStartError(null); setRoomError(null); setDeviceError(null);
    const details = connectionDetails ?? (await requestToken());
    if (!details) return;
    try {
      if (!navigator.mediaDevices?.getUserMedia) { setMicPermission("error"); setStartError("Browser does not support microphone access"); return; }
      const micStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      setMicPermission("granted");
      micStream.getTracks().forEach((t) => t.stop());
      setSessionStarted(true);
      setShouldConnect(true);
    } catch (e) {
      if (e instanceof DOMException && e.name === "NotAllowedError") { setMicPermission("denied"); setStartError("Microphone permission denied"); return; }
      setMicPermission("error");
      setStartError(e instanceof Error ? e.message : "Error connecting to server");
    }
  }, [connectionDetails, requestToken]);

  const onRetryConnection = useCallback(async () => {
    setStartError(null); setRoomError(null); setDeviceError(null);
    const details = connectionDetails ?? (await requestToken());
    if (!details) { setShouldConnect(false); return; }
    setSessionStarted(true);
    setShouldConnect(true);
  }, [connectionDetails, requestToken]);

  const onBackToStart = useCallback(() => {
    setSessionStarted(false); setShouldConnect(false); setConnected(false);
    setRoomError(null); setDeviceError(null);
    setConnectionDetails(null);
  }, []);

  // ── Connected: full-screen split layout ──
  if (sessionStarted && connectionDetails) {
    return (
      <LiveKitRoom
        token={connectionDetails.token}
        serverUrl={connectionDetails.url}
        connect={shouldConnect}
        audio={{ echoCancellation: true, noiseSuppression: true, autoGainControl: true }}
        onConnected={() => { setConnected(true); setRoomError(null); }}
        onError={(error: Error) => {
          const msg = error.message.includes("could not establish signal connection")
            ? `${error.message} (serverUrl=${connectionDetails.url})` : error.message;
          setRoomError(msg);
        }}
        onMediaDeviceFailure={(failure?: MediaDeviceFailure, kind?: MediaDeviceKind) => {
          setDeviceError(`${kind ?? "media"} failure: ${failure ?? "unknown"}`);
        }}
        onDisconnected={() => { setConnected(false); setShouldConnect(false); setRoomError((prev) => prev ?? "Disconnected from LiveKit"); }}
      >
        <SplitLayout connected={connected} onBackToStart={onBackToStart} gpsLocation={gpsLocation} />
        <RoomAudioRenderer />
        <StartAudio label="Click to enable audio playback" />
      </LiveKitRoom>
    );
  }

  // ── Pre-connection: centered layout ──
  return (
    <main className="min-h-screen bg-background flex flex-col items-center justify-center gap-6 px-6 py-10">
      <div className="w-full max-w-sm flex flex-col items-center gap-6">
        <div className="flex w-full items-start justify-between">
          <div className="text-center flex-1">
            <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground">Taigi-Flow</p>
            <h1 className="mt-2 text-3xl font-semibold">台語語音助理</h1>
          </div>
          <ThemeToggle />
        </div>

        {startError && <p className="text-sm text-destructive text-center">{startError}</p>}
        {roomError && <p className="text-sm text-destructive text-center">{roomError}</p>}
        {deviceError && <p className="text-sm text-destructive text-center">{deviceError}</p>}

        <Button onClick={onConnectButtonClicked} disabled={tokenLoading} size="lg" className="rounded-full px-10">
          <Mic className="mr-2 h-4 w-4" />
          {tokenLoading ? "準備中…" : "開始對話"}
        </Button>

        {sessionStarted && !connected && (
          <div className="flex gap-3">
            <Button onClick={onRetryConnection} variant="outline" className="rounded-full">
              <RotateCcw className="mr-2 h-4 w-4" />重試
            </Button>
            <Button variant="ghost" onClick={onBackToStart} className="rounded-full">
              <ArrowLeft className="mr-1 h-4 w-4" />返回
            </Button>
          </div>
        )}
      </div>
    </main>
  );
}
