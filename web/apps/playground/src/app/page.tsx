"use client";

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
import { useCallback, useEffect, useState } from "react";

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

    // If the page is opened from another host/device, localhost in token response
    // points to the wrong machine. Rebind to current host while preserving port.
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
    <main className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-950 text-white">
      <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col items-center justify-center gap-6 px-6 py-10">
        <div className="text-center">
          <div className="text-xs uppercase tracking-[0.3em] text-zinc-400">
            LiveKit Voice Playground
          </div>
          <h1 className="mt-2 text-4xl font-semibold">Taigi-Flow</h1>
          <p className="mt-2 text-sm text-zinc-400">
            即時語音互動（ASR → LLM → TTS）
          </p>
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
          <button
            onClick={onConnectButtonClicked}
            disabled={tokenLoading}
            className="rounded-full bg-emerald-400 px-8 py-3 text-sm font-semibold text-black transition-colors hover:bg-emerald-300 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-300"
          >
            {tokenLoading ? "Preparing..." : "Start Conversation"}
          </button>
        ) : connectionDetails ? (
          <div className="flex w-full flex-col gap-4">
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
              onError={(error) => {
                const currentUrl = connectionDetails.url;
                const message = error.message.includes("could not establish signal connection")
                  ? `${error.message} (serverUrl=${currentUrl})`
                  : error.message;
                setRoomError(message);
              }}
              onMediaDeviceFailure={(failure, kind) => {
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
                <button
                  onClick={onRetryConnection}
                  className="rounded-full bg-emerald-400 px-5 py-2 text-sm font-semibold text-black transition-colors hover:bg-emerald-300"
                >
                  Retry connection
                </button>
                <button
                  onClick={onBackToStart}
                  className="rounded-full border border-zinc-700 px-5 py-2 text-sm font-semibold text-zinc-200 transition-colors hover:bg-zinc-800"
                >
                  Back
                </button>
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
    <div className="w-full rounded-2xl border border-zinc-800 bg-zinc-900/70 p-5 text-sm shadow-xl">
      <div className="mb-3 font-semibold text-zinc-100">Connection Diagnostics</div>
      <div className="grid gap-2 text-zinc-300 md:grid-cols-2">
        {rows.map((row) => (
          <div
            key={row.label}
            className="flex items-center justify-between rounded-lg border border-zinc-800/80 bg-zinc-950/70 px-3 py-2"
          >
            <span className="text-zinc-400">{row.label}</span>
            <span
              className={`ml-3 max-w-[70%] text-right text-zinc-200 ${
                row.multiline ? "break-all whitespace-pre-wrap" : "truncate"
              }`}
            >
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </div>
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
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-5 rounded-2xl border border-zinc-800 bg-zinc-900/80 p-6 shadow-2xl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-zinc-400">
            Agent Status
          </div>
          <div className="mt-1 text-2xl font-bold capitalize text-white">
            {statusLabel}
          </div>
        </div>
        <div
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            connected ? "bg-emerald-500/20 text-emerald-300" : "bg-zinc-800 text-zinc-300"
          }`}
        >
          {connected ? "Connected" : "Disconnected"}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <WaveformCard
          title="Your voice"
          active={isMicrophoneEnabled}
          subtitle={isMicrophoneEnabled ? "Mic is on" : "Mic is off"}
          trackAvailable={!!microphoneTrack}
          track={microphoneTrack?.track as LocalAudioTrack | undefined}
          emptyText="Waiting for local mic track..."
        />
        <WaveformCard
          title="Agent voice"
          active={state === "speaking" || !!audioTrack}
          subtitle={state === "speaking" ? "Agent is speaking" : "Listening / idle"}
          trackAvailable={!!audioTrack}
          track={audioTrack ?? undefined}
          emptyText="Waiting for agent audio..."
        />
      </div>

      <div className="w-full rounded-xl border border-zinc-800 bg-black/30 p-4 text-sm text-zinc-300">
        <div>Room state: {connectionState}</div>
        <div>Local microphone enabled: {isMicrophoneEnabled ? "yes" : "no"}</div>
        <div>Local microphone track: {microphoneTrack ? "published" : "none"}</div>
        <div>
          Microphone error: {lastMicrophoneError?.message ?? micEnableError ?? "-"}
        </div>
      </div>

      <DisconnectButton className="self-center rounded-full bg-red-500 px-7 py-2 text-white transition-colors hover:bg-red-600">
        End Conversation
      </DisconnectButton>
      {!connected && (
        <button
          onClick={onBackToStart}
          className="self-center text-sm text-zinc-400 underline-offset-4 hover:text-zinc-200 hover:underline"
        >
          Back to start
        </button>
      )}
    </div>
  );
}

function WaveformCard({
  title,
  subtitle,
  active,
  trackAvailable,
  track,
  emptyText,
}: {
  title: string;
  subtitle: string;
  active: boolean;
  trackAvailable: boolean;
  track?: TrackReferenceOrPlaceholder | LocalAudioTrack | RemoteAudioTrack;
  emptyText: string;
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-zinc-100">{title}</div>
          <div className="text-xs text-zinc-400">{subtitle}</div>
        </div>
        <div
          className={`h-2.5 w-2.5 rounded-full ${
            active ? "bg-emerald-400 shadow-[0_0_12px_#34d399]" : "bg-zinc-600"
          }`}
        />
      </div>
      <div className="flex h-28 items-center justify-center rounded-lg bg-black/40">
        {trackAvailable && track ? (
          <BarVisualizer
            track={track}
            barCount={9}
            options={{ minHeight: 6 }}
            className="h-20 [--lk-fg:#34d399]"
          />
        ) : (
          <span className="text-sm text-zinc-500">{emptyText}</span>
        )}
      </div>
    </div>
  );
}
