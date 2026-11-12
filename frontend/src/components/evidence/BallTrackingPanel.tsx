"use client";
import { useEffect, useRef, useState } from "react";
import type { SessionEntry } from "@/lib/session-client";
import {
  ballTrackSchema,
  evidenceRequest,
  type BallTrack,
  type EvidenceArtifact,
} from "@/lib/evidence-client";
import { videoPointFromClick } from "@/lib/visualization";

export function BallTrackingPanel({
  entry,
  onResult,
  onInvalidate,
}: {
  entry: SessionEntry;
  onResult: (value: EvidenceArtifact) => void;
  onInvalidate: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null),
    controller = useRef<AbortController | null>(null);
  const [url, setUrl] = useState(""),
    [selecting, setSelecting] = useState(false),
    [seed, setSeed] = useState<{
      point: [number, number];
      time: number;
    } | null>(null);
  const [radius, setRadius] = useState("3"),
    [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [duration, setDuration] = useState("2");
  const [result, setResult] = useState<BallTrack | null>(null),
    [time, setTime] = useState(0),
    [ratio, setRatio] = useState<number | null>(null);
  useEffect(() => {
    const value = URL.createObjectURL(entry.file);
    setUrl(value);
    return () => {
      URL.revokeObjectURL(value);
      controller.current?.abort();
    };
  }, [entry.file]);
  const run = async () => {
    if (!seed || !entry.analysis || busy) return;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const form = new FormData();
      form.append("video", entry.file);
      form.append(
        "options",
        JSON.stringify({
          swing_id: entry.swingId.trim(),
          analysis_token: entry.analysis.summary_token,
          seed_source_seconds: seed.time,
          seed_point: seed.point,
          radius_px: Number(radius),
          duration_seconds: Number(duration),
          stationary_confirmed: confirmed,
        }),
      );
      const output = await evidenceRequest(
        "/ball-tracks",
        form,
        ballTrackSchema,
        AbortSignal.any([abort.signal, AbortSignal.timeout(300000)]),
      );
      setResult(output);
      onResult({ kind: "ball_candidate_track", result: output });
    } catch (cause) {
      if (!abort.signal.aborted)
        setError(
          cause instanceof Error ? cause.message : "Ball tracking failed.",
        );
    } finally {
      if (!abort.signal.aborted) setBusy(false);
    }
  };
  const aligned =
    !result ||
    ratio === null ||
    Math.abs(ratio / (result.width / result.height) - 1) < 0.02;
  const visible =
    result?.samples.filter((sample) => sample.source_seconds <= time + 0.01) ??
    [];
  return (
    <div
      className="evidence-section"
      onChange={() => {
        setResult(null);
        onInvalidate();
      }}
    >
      <p>
        Pause just before or at impact, then select the visible ball. The
        installed golf-ball detector follows candidates for the selected window
        and stops when detection becomes unreliable. If no model is installed,
        the result identifies the appearance baseline. No launch monitor is
        required.
      </p>
      <p className="help-text">
        A single-camera tracer shows visible image motion; physical carry, spin
        and launch speed need additional measurement evidence.{" "}
        <a
          href="/capture-guide"
          target="_blank"
          rel="noopener noreferrer"
          className="text-button"
        >
          Capture guidance
        </a>
      </p>
      <div className="video-stage has-video ball-stage">
        {url && (
          <video
            ref={video}
            src={url}
            controls={!selecting}
            playsInline
            preload="metadata"
            aria-label="Ball tracking source video"
            onLoadedMetadata={(event) => {
              event.currentTarget.currentTime =
                entry.analysis?.pose?.video.source_start_seconds ??
                Number(entry.start);
              setRatio(
                event.currentTarget.videoWidth /
                  event.currentTarget.videoHeight,
              );
            }}
            onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)}
          />
        )}
        {result && aligned && result.width > 0 && (
          <svg
            className="pose-overlay"
            viewBox={`0 0 ${result.width} ${result.height}`}
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label="Unconfirmed ball candidate trace"
          >
            <title>Candidate trace, requiring visual confirmation</title>
            <polyline
              points={visible.map((sample) => sample.xy_px.join(",")).join(" ")}
              fill="none"
              stroke="#f2b45f"
              strokeWidth={Math.max(2, result.width / 600)}
            />
            {visible.map((sample, i) => (
              <circle
                key={i}
                cx={sample.xy_px[0]}
                cy={sample.xy_px[1]}
                r={Math.max(3, result.width / 400)}
                fill="#ffda93"
              />
            ))}
          </svg>
        )}
        {selecting && (
          <button
            className="subject-picker"
            aria-label="Select the ball in the paused frame"
            onClick={(event) => {
              const element = video.current;
              if (!element) return;
              const rect = event.currentTarget.getBoundingClientRect();
              const point = videoPointFromClick(
                event.clientX - rect.left,
                event.clientY - rect.top,
                rect.width,
                rect.height,
                element.videoWidth,
                element.videoHeight,
              );
              if (!point) {
                setError("Select inside the video image.");
                return;
              }
              setSeed({ point, time: element.currentTime });
              onInvalidate();
              setSelecting(false);
              setResult(null);
            }}
          >
            <span>Click the centre of the ball</span>
          </button>
        )}
      </div>
      <div className="session-toolbar">
        <button
          className="button button-secondary"
          disabled={busy}
          onClick={() => {
            video.current?.pause();
            setSelecting(!selecting);
            setError("");
          }}
        >
          {selecting ? "Cancel ball selection" : "Select ball at paused frame"}
        </button>
        <label>
          Ball radius (decoded pixels)
          <input
            className="field"
            aria-label="Ball radius in pixels"
            type="number"
            min="2"
            max="20"
            value={radius}
            onChange={(event) => {
              setRadius(event.target.value);
              setResult(null);
            }}
            disabled={busy}
          />
        </label>
        <label>
          Tracking window (seconds)
          <input
            className="field"
            aria-label="Ball tracking duration"
            type="number"
            min="0.1"
            max="5"
            step="0.1"
            value={duration}
            onChange={(event) => setDuration(event.target.value)}
            disabled={busy}
          />
        </label>
      </div>
      {seed && (
        <p className="help-text">
          Seed at {seed.time.toFixed(3)}s in the original recording ·{" "}
          {(seed.point[0] * 100).toFixed(1)}%,{" "}
          {(seed.point[1] * 100).toFixed(1)}%.
        </p>
      )}
      <label className="confirmation-row">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
          disabled={busy}
        />
        The camera stayed stationary. Leave unchecked for handheld footage; its
        image trace includes camera movement. The appearance baseline requires a
        fixed camera.
      </label>
      <button
        className="button button-primary"
        disabled={
          !seed ||
          busy ||
          !Number.isInteger(Number(radius)) ||
          Number(radius) < 2 ||
          Number(radius) > 20 ||
          !Number.isFinite(Number(duration)) ||
          Number(duration) <= 0 ||
          Number(duration) > 5
        }
        onClick={run}
      >
        {busy ? "Tracking visible candidates…" : "Track ball candidates"}
      </button>
      {busy && (
        <button
          className="text-button"
          onClick={() => {
            controller.current?.abort();
            setBusy(false);
          }}
        >
          Cancel tracking
        </button>
      )}
      {error && (
        <p className="message message-error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="evidence-result">
          <h3>
            {result.status === "candidate_track"
              ? "Candidate trace — visually check every point"
              : "Insufficient ball-flight evidence"}
          </h3>
          <p>
            {result.samples.length} samples · stopped:{" "}
            {result.stop_reason.replaceAll("_", " ")}.{" "}
            {result.samples.length
              ? "Play the source to review the amber candidate trace."
              : "No visible trace is supported at this seed."}
          </p>
          <p className="help-text">
            Tracking method:{" "}
            {result.tracker_backend === "onnx_golf_detector"
              ? "local golf-ball detection model"
              : "appearance baseline (no trained detector)"}
            . Every trace needs visual review.
          </p>
          {(result.camera_motion_detected || !result.stationary_confirmed) && (
            <p className="message message-warning">
              Camera stability is unconfirmed or movement was detected. The
              trace includes image motion, so it cannot establish launch angle
              or shot curvature.
            </p>
          )}
          {!aligned && (
            <p className="message message-warning">
              Overlay hidden because decoded and displayed orientations differ.
            </p>
          )}
          <ul className="evidence-notes">
            {result.notices.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
