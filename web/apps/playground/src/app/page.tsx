"use client";

import type { MediaDeviceFailure } from "livekit-client";
import {
  BarVisualizer,
  DisconnectButton,
  LiveKitRoom,
  RoomAudioRenderer,
  StartAudio,
  TrackReferenceOrPlaceholder,
  useConnectionState,
  useLocalParticipant,
  useVoiceAssistant,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { LocalAudioTrack, RemoteAudioTrack } from "livekit-client";
import {
  ArrowLeft,
  ChevronDown,
  Mic,
  MicOff,
  Moon,
  PhoneOff,
  Radio,
  RotateCcw,
  Sun,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

type DispatchStatus = "unknown" | "ok" | "unavailable";

type ConnectionDetails = {
  token: string;
  url: string;
  roomName?: string;
};

function normalizeLiveKitUrl(rawUrl: string): string {
  if (typeof window === "undefined") return rawUrl;
  try {
    const parsed = new URL(rawUrl);
    const localHosts = new Set(["localhost", "127.0.0.1", "::1"]);
    const currentHost = window.location.hostname;
    const isServerUrlLocal = localHosts.has(parsed.hostname);
    const isCurrentHostLocal = localHosts.has(currentHost);

    // If the page is opened from another host/device, rebind localhost to current host.
    if (isServerUrlLocal && !isCurrentHostLocal) {
      parsed.hostname = currentHost;
    }
    if (window.location.protocol === "https:" && parsed.protocol === "ws:") {
      parsed.protocol = "wss:";
    }
    return parsed.toString();
  } catch {
    return rawUrl;
  }
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <Button
      variant="outline"
      size="icon"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      aria-label="切換主題"
    >
      <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
    </Button>
  );
}

export default function Playground() {
  const [connectionDetails, setConnectionDetails] =
    useState<ConnectionDetails | null>(null);
  const [dispatchStatus, setDispatchStatus] = useState<DispatchStatus>("unknown");
  const [dispatchMessage, setDispatchMessage] = useState<string | null>(null);
  const [tokenLoading, setTokenLoading] = useState(true);
  const [sessionStarted, setSessionStarted] = useState(false);
  const [shouldConnect, setShouldConnect] = useState(false);
  const [micPermission, setMicPermission] = useState<
    "unknown" | "granted" | "denied" | "error"
  >("unknown");
  const [startError, setStartError] = useState<string | null>(null);
  const [roomError, setRoomError] = useState<string | null>(null);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

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
        setDispatchStatus(
          data.dispatchStatus === "ok" || data.dispatchStatus === "unavailable"
            ? data.dispatchStatus
            : "unknown"
        );
        setDispatchMessage(
          typeof data.dispatchMessage === "string" ? data.dispatchMessage : null
        );
        return details;
      } else {
        setStartError(data.error ?? "Failed to get connection token");
      }
    } catch (error) {
      setStartError(
        error instanceof Error ? error.message : "Failed to get connection token"
      );
    } finally {
      setTokenLoading(false);
    }
    return null;
  }, []);

  useEffect(() => {
    void requestToken();
  }, [requestToken]);

  const onConnectButtonClicked = useCallback(async () => {
    setStartError(null);
    setRoomError(null);
    setDeviceError(null);

    const details = connectionDetails ?? (await requestToken());
    if (!details) return;

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        setMicPermission("error");
        setStartError("Browser does not support microphone access");
        return;
      }

      // AEC/NS/AGC must stay true — disabling any causes TTS echo to trigger barge-in.
      const micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      setMicPermission("granted");
      micStream.getTracks().forEach((track) => track.stop());
      setSessionStarted(true);
      setShouldConnect(true);
    } catch (e) {
      console.error(e);
      if (e instanceof DOMException && e.name === "NotAllowedError") {
        setMicPermission("denied");
        setStartError("Microphone permission denied");
        return;
      }
      setMicPermission("error");
      setStartError(e instanceof Error ? e.message : "Error connecting to server");
    }
  }, [connectionDetails, requestToken]);

  const onRetryConnection = useCallback(async () => {
    setStartError(null);
    setRoomError(null);
    setDeviceError(null);
    const details = connectionDetails ?? (await requestToken());
    if (!details) {
      setShouldConnect(false);
      return;
    }
    setSessionStarted(true);
    setShouldConnect(true);
  }, [connectionDetails, requestToken]);

  const onBackToStart = useCallback(() => {
    setSessionStarted(false);
    setShouldConnect(false);
    setConnected(false);
    setRoomError(null);
    setDeviceError(null);
    void requestToken();
  }, [requestToken]);

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto flex min-h-screen w-full max-w-4xl flex-col items-center justify-center gap-6 px-6 py-10">
        <div className="w-full flex items-start justify-between">
          <div className="text-center flex-1">
            <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground">
              LiveKit Voice Playground
            </p>
            <h1 className="mt-2 text-4xl font-semibold">Taigi-Flow</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              即時語音互動（ASR → LLM → TTS）
            </p>
          </div>
          <ThemeToggle />
        </div>

        <StartDiagnostics
          micPermission={micPermission}
          startError={startError}
          roomError={roomError}
          deviceError={deviceError}
          connected={connected}
          tokenLoading={tokenLoading}
          tokenReady={!!connectionDetails}
          roomName={connectionDetails?.roomName ?? null}
          liveKitUrl={connectionDetails?.url ?? null}
          dispatchStatus={dispatchStatus}
          dispatchMessage={dispatchMessage}
        />

        {!sessionStarted ? (
          <Button
            onClick={onConnectButtonClicked}
            disabled={tokenLoading}
            size="lg"
            className="rounded-full px-8"
          >
            <Mic className="mr-2 h-4 w-4" />
            {tokenLoading ? "Preparing..." : "Start Conversation"}
          </Button>
        ) : connectionDetails ? (
          <div className="flex w-full flex-col gap-4">
            {/* AEC/NS/AGC must stay true — see getUserMedia comment above. */}
            <LiveKitRoom
              token={connectionDetails.token}
              serverUrl={connectionDetails.url}
              connect={shouldConnect}
              audio={{
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
              }}
              onConnected={() => {
                setConnected(true);
                setRoomError(null);
              }}
              onError={(error: Error) => {
                const currentUrl = connectionDetails.url;
                const message = error.message.includes("could not establish signal connection")
                  ? `${error.message} (serverUrl=${currentUrl})`
                  : error.message;
                setRoomError(message);
              }}
              onMediaDeviceFailure={(failure?: MediaDeviceFailure, kind?: MediaDeviceKind) => {
                setDeviceError(`${kind ?? "media"} failure: ${failure ?? "unknown"}`);
              }}
              onDisconnected={() => {
                setConnected(false);
                setShouldConnect(false);
                setRoomError((prev) => prev ?? "Disconnected from LiveKit");
              }}
              className="w-full"
            >
              <PlaygroundUI connected={connected} onBackToStart={onBackToStart} />
              <RoomAudioRenderer />
              <StartAudio label="Click to enable audio playback" />
            </LiveKitRoom>
            {!connected && (
              <div className="mx-auto flex gap-3">
                <Button onClick={onRetryConnection} className="rounded-full">
                  <RotateCcw className="mr-2 h-4 w-4" />
                  Retry connection
                </Button>
                <Button variant="outline" onClick={onBackToStart} className="rounded-full">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  Back
                </Button>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </main>
  );
}

function StartDiagnostics({
  micPermission,
  startError,
  roomError,
  deviceError,
  connected,
  tokenLoading,
  tokenReady,
  roomName,
  liveKitUrl,
  dispatchStatus,
  dispatchMessage,
}: {
  micPermission: "unknown" | "granted" | "denied" | "error";
  startError: string | null;
  roomError: string | null;
  deviceError: string | null;
  connected: boolean;
  tokenLoading: boolean;
  tokenReady: boolean;
  roomName: string | null;
  liveKitUrl: string | null;
  dispatchStatus: DispatchStatus;
  dispatchMessage: string | null;
}) {
  const rows: Array<{ label: string; value: string; multiline?: boolean }> = [
    {
      label: "Token",
      value: tokenReady ? "ready" : tokenLoading ? "loading" : "not ready",
    },
    { label: "Room", value: roomName ?? "-" },
    { label: "LiveKit URL", value: liveKitUrl ?? "-", multiline: true },
    { label: "Agent dispatch", value: dispatchStatus },
    { label: "Mic permission", value: micPermission },
    { label: "LiveKit", value: connected ? "connected" : "disconnected" },
    { label: "Startup error", value: startError ?? "-", multiline: true },
    { label: "Room error", value: roomError ?? "-", multiline: true },
    { label: "Media device error", value: deviceError ?? "-", multiline: true },
    { label: "Dispatch message", value: dispatchMessage ?? "-", multiline: true },
  ];

  return (
    <Collapsible className="w-full">
      <Card className="w-full">
        <CardHeader className="pb-3">
          <CollapsibleTrigger className="group flex w-full items-center gap-2 text-left cursor-pointer">
            {connected ? (
              <Wifi className="h-4 w-4 shrink-0 text-green-500" />
            ) : (
              <WifiOff className="h-4 w-4 shrink-0 text-muted-foreground" />
            )}
            <CardTitle className="flex-1 text-sm">Connection Diagnostics</CardTitle>
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-data-[open]:rotate-180" />
          </CollapsibleTrigger>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="pt-0">
            <div className="grid gap-2 text-sm md:grid-cols-2">
              {rows.map((row) => (
                <div
                  key={row.label}
                  className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2"
                >
                  <span className="text-muted-foreground shrink-0">{row.label}</span>
                  <span
                    className={`ml-3 max-w-[60%] text-right ${
                      row.multiline ? "break-all whitespace-pre-wrap" : "truncate"
                    }`}
                  >
                    {row.value}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}

function PlaygroundUI({
  connected,
  onBackToStart,
}: {
  connected: boolean;
  onBackToStart: () => void;
}) {
  const { state, audioTrack } = useVoiceAssistant();
  const connectionState = useConnectionState();
  const { isMicrophoneEnabled, localParticipant, microphoneTrack, lastMicrophoneError } =
    useLocalParticipant();
  const [micEnableError, setMicEnableError] = useState<string | null>(null);
  const statusLabel = connected ? state : "idle";

  useEffect(() => {
    if (!connected || isMicrophoneEnabled) return;
    void localParticipant
      .setMicrophoneEnabled(true)
      .then(() => setMicEnableError(null))
      .catch((error) => {
        setMicEnableError(
          error instanceof Error ? error.message : "unknown microphone error"
        );
      });
  }, [connected, isMicrophoneEnabled, localParticipant]);

  return (
    <Card className="w-full">
      <CardContent className="flex flex-col gap-5 pt-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
              Agent Status
            </p>
            <div className="mt-1 text-2xl font-bold capitalize">{statusLabel}</div>
          </div>
          <Badge variant={connected ? "default" : "secondary"}>
            {connected ? (
              <Wifi className="mr-1 h-3 w-3" />
            ) : (
              <WifiOff className="mr-1 h-3 w-3" />
            )}
            {connected ? "Connected" : "Disconnected"}
          </Badge>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <WaveformCard
            title="Your voice"
            icon={isMicrophoneEnabled ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
            active={isMicrophoneEnabled}
            subtitle={isMicrophoneEnabled ? "Mic is on" : "Mic is off"}
            trackAvailable={!!microphoneTrack}
            track={microphoneTrack?.track as LocalAudioTrack | undefined}
            emptyText="Waiting for local mic track..."
          />
          <WaveformCard
            title="Agent voice"
            icon={<Radio className="h-4 w-4" />}
            active={state === "speaking" || !!audioTrack}
            subtitle={state === "speaking" ? "Agent is speaking" : "Listening / idle"}
            trackAvailable={!!audioTrack}
            track={audioTrack ?? undefined}
            emptyText="Waiting for agent audio..."
          />
        </div>

        <Card className="bg-muted/30">
          <CardContent className="pt-4 text-sm text-muted-foreground space-y-1">
            <div>Room state: {connectionState}</div>
            <div>Local microphone enabled: {isMicrophoneEnabled ? "yes" : "no"}</div>
            <div>Local microphone track: {microphoneTrack ? "published" : "none"}</div>
            <div>
              Microphone error: {lastMicrophoneError?.message ?? micEnableError ?? "-"}
            </div>
          </CardContent>
        </Card>

        <DisconnectButton className="self-center inline-flex items-center rounded-full bg-destructive px-7 py-2 text-sm font-medium text-white transition-colors hover:bg-destructive/90">
          <PhoneOff className="mr-2 h-4 w-4" />
          End Conversation
        </DisconnectButton>

        {!connected && (
          <Button
            variant="ghost"
            onClick={onBackToStart}
            className="self-center text-sm text-muted-foreground"
          >
            <ArrowLeft className="mr-1 h-4 w-4" />
            Back to start
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function WaveformCard({
  title,
  icon,
  subtitle,
  active,
  trackAvailable,
  track,
  emptyText,
}: {
  title: string;
  icon: React.ReactNode;
  subtitle: string;
  active: boolean;
  trackAvailable: boolean;
  track?: TrackReferenceOrPlaceholder | LocalAudioTrack | RemoteAudioTrack;
  emptyText: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            <span className={active ? "text-foreground" : "text-muted-foreground"}>
              {icon}
            </span>
            {title}
          </div>
          <div
            className={`h-2 w-2 rounded-full transition-colors ${
              active ? "bg-green-500 shadow-[0_0_8px_theme(colors.green.500)]" : "bg-muted-foreground/30"
            }`}
          />
        </CardTitle>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </CardHeader>
      <CardContent>
        <div className="flex h-24 items-center justify-center rounded-lg bg-muted/40">
          {trackAvailable && track ? (
            <BarVisualizer
              track={track}
              barCount={9}
              options={{ minHeight: 6 }}
              className="h-16 [--lk-fg:oklch(0.723_0.219_149.579)]"
            />
          ) : (
            <span className="text-xs text-muted-foreground">{emptyText}</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
