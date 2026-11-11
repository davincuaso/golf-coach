"use client";
import { useEffect, useRef, useState } from "react";
import {
  bestRecordingMime,
  MAX_RECORDING_SECONDS,
  MAX_VIDEO_BYTES,
} from "@/lib/capture";
import { Icon } from "@/components/ui/Icon";

export function VideoRecorder({
  disabled,
  onSelect,
  onRecordingChange,
}: {
  disabled: boolean;
  onSelect: (file: File) => void;
  onRecordingChange: (value: boolean) => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const mounted = useRef(true);
  const [cameraOn, setCameraOn] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const clearTimer = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  };
  const stopTracks = () => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  };
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      clearTimer();
      if (recorder.current) {
        recorder.current.onstop = null;
        recorder.current.ondataavailable = null;
        recorder.current.onerror = null;
        if (recorder.current.state !== "inactive") recorder.current.stop();
      }
      stopTracks();
    };
  }, []);
  useEffect(() => {
    if (cameraOn && video.current) {
      video.current.srcObject = stream.current;
      void video.current.play().catch(() => {});
    }
  }, [cameraOn]);
  const openCamera = async () => {
    setError(null);
    if (
      !window.isSecureContext ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setError(
        "Camera recording needs a supported browser on HTTPS or localhost. You can upload a video instead.",
      );
      return;
    }
    setRequesting(true);
    try {
      const next = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
          frameRate: { ideal: 60 },
        },
        audio: false,
      });
      if (!mounted.current) {
        next.getTracks().forEach((track) => track.stop());
        return;
      }
      stream.current = next;
      setCameraOn(true);
    } catch {
      if (mounted.current)
        setError(
          "Camera access was unavailable. Allow camera access in your browser, or upload a video.",
        );
    } finally {
      if (mounted.current) setRequesting(false);
    }
  };
  const stopRecording = () => {
    if (recorder.current?.state === "recording") recorder.current.stop();
  };
  const start = () => {
    if (!stream.current || disabled) return;
    setError(null);
    chunks.current = [];
    let size = 0;
    let failed = false;
    try {
      const mimeType = bestRecordingMime(MediaRecorder);
      const next = new MediaRecorder(stream.current, {
        ...(mimeType ? { mimeType } : {}),
        videoBitsPerSecond: 8000000,
      });
      recorder.current = next;
      next.ondataavailable = (event) => {
        size += event.data.size;
        if (size > MAX_VIDEO_BYTES) {
          failed = true;
          stopRecording();
        } else if (event.data.size) chunks.current.push(event.data);
      };
      next.onerror = () => {
        failed = true;
        stopRecording();
        if (mounted.current)
          setError(
            "Recording was interrupted. Please try again or upload a video.",
          );
      };
      next.onstop = () => {
        clearTimer();
        stopTracks();
        if (!mounted.current) return;
        setCameraOn(false);
        setRecording(false);
        onRecordingChange(false);
        if (failed || !chunks.current.length) {
          setError(
            "The recording could not be saved. Try a shorter recording.",
          );
          return;
        }
        const type = next.mimeType || mimeType || "video/webm";
        const extension = type.includes("mp4") ? "mp4" : "webm";
        const file = new File(
          chunks.current,
          `swing-${Date.now()}.${extension}`,
          { type },
        );
        chunks.current = [];
        onSelect(file);
      };
      next.start(250);
      setElapsed(0);
      setRecording(true);
      onRecordingChange(true);
      const started = performance.now();
      timer.current = setInterval(() => {
        const seconds = (performance.now() - started) / 1000;
        setElapsed(Math.min(MAX_RECORDING_SECONDS, seconds));
        if (seconds >= MAX_RECORDING_SECONDS) stopRecording();
      }, 100);
    } catch {
      setError(
        "This browser could not start video recording. Upload a video instead.",
      );
      stopTracks();
      setCameraOn(false);
    }
  };
  return (
    <div>
      {!cameraOn ? (
        <button
          type="button"
          className="upload-zone"
          onClick={openCamera}
          disabled={disabled || requesting}
        >
          <span className="upload-icon">
            <Icon name="camera" width={26} height={26} />
          </span>
          <strong>
            {requesting ? "Opening your camera…" : "Bring your swing into view"}
          </strong>
          <span>Open camera to frame your shot</span>
          <small>Video only · Automatically stops at 30 seconds</small>
        </button>
      ) : (
        <div className="camera-view">
          <video
            ref={video}
            autoPlay
            muted
            playsInline
            aria-label="Live camera preview"
          />
          <div className="camera-controls">
            <span className="status-pill">
              {recording && <span className="record-dot" />}
              {elapsed.toFixed(1)} / 30s
            </span>
            {recording ? (
              <button
                type="button"
                className="button button-primary"
                onClick={stopRecording}
              >
                Stop recording
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="button button-primary"
                  onClick={start}
                  disabled={disabled}
                >
                  <span className="record-dot" />
                  Record swing
                </button>
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Close camera"
                  onClick={() => {
                    stopTracks();
                    setCameraOn(false);
                  }}
                >
                  <Icon name="close" />
                </button>
              </>
            )}
          </div>
        </div>
      )}
      {error && (
        <p className="message message-error" role="alert">
          {error}
        </p>
      )}
      <p className="help-text mt-3">
        Keep your full body in frame, with room for the club. Use a fixed camera
        and good light.
      </p>
    </div>
  );
}
