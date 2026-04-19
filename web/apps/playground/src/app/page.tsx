"use client";

import {
  LiveKitRoom,
  RoomAudioRenderer,
  BarVisualizer,
  useVoiceAssistant,
  DisconnectButton,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { useCallback, useState } from "react";

export default function Playground() {
  const [connectionDetails, setConnectionDetails] = useState<{
    token: string;
    url: string;
  } | null>(null);

  const onConnectButtonClicked = useCallback(async () => {
    try {
      const res = await fetch("/api/livekit/token", { method: "POST" });
      const data = await res.json();
      if (data.token && data.url) {
        setConnectionDetails(data);
      } else {
        alert("Failed to get connection token: " + data.error);
      }
    } catch (e) {
      console.error(e);
      alert("Error connecting to server");
    }
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24 bg-zinc-950 text-white">
      <div className="z-10 max-w-5xl w-full items-center justify-between font-mono text-sm flex flex-col gap-8">
        <h1 className="text-4xl font-bold">Taigi-Flow Playground</h1>

        {!connectionDetails ? (
          <button
            onClick={onConnectButtonClicked}
            className="bg-white text-black px-6 py-3 rounded-full font-semibold hover:bg-gray-200 transition-colors"
          >
            Start Conversation
          </button>
        ) : (
          <LiveKitRoom
            token={connectionDetails.token}
            serverUrl={connectionDetails.url}
            connect={true}
            audio={{
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            }}
            onDisconnected={() => setConnectionDetails(null)}
            className="flex flex-col items-center gap-8 w-full"
          >
            <PlaygroundUI />
            <RoomAudioRenderer />
          </LiveKitRoom>
        )}
      </div>
    </main>
  );
}

function PlaygroundUI() {
  const { state, audioTrack } = useVoiceAssistant();

  return (
    <div className="flex flex-col items-center gap-8 bg-zinc-900 p-8 rounded-2xl w-full max-w-md shadow-xl border border-zinc-800">
      <div className="flex flex-col items-center gap-4">
        <div className="text-sm uppercase tracking-widest text-zinc-400 font-semibold">
          Agent Status
        </div>
        <div className="text-2xl font-bold capitalize text-white">
          {state}
        </div>
      </div>

      <div className="h-32 w-full flex items-center justify-center bg-black/50 rounded-xl overflow-hidden">
        {audioTrack ? (
          <BarVisualizer
            trackRef={audioTrack}
            barCount={7}
            options={{ minHeight: 4 }}
            className="h-24"
          />
        ) : (
          <div className="text-zinc-600">Waiting for agent audio...</div>
        )}
      </div>

      <DisconnectButton className="bg-red-500 hover:bg-red-600 text-white px-6 py-2 rounded-full font-medium transition-colors">
        End Conversation
      </DisconnectButton>
    </div>
  );
}
