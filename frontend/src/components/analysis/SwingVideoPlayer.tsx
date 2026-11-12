"use client";
import { useEffect, useRef, useState } from "react";
import type { VisionDocument } from "@/lib/api-types";
import { nearestPoseFrame, videoPointFromClick } from "@/lib/visualization";
import { Icon } from "@/components/ui/Icon";
import { PoseOverlay } from "./PoseOverlay";

interface Props {
  file: File | null;
  pose: VisionDocument | null;
  onTime: (time: number) => void;
  onDuration: (duration: number | undefined) => void;
  subjectPoint?: [number, number];
  onSubjectPoint: (point: [number, number]) => void;
  disabled: boolean;
  sourceStartSeconds?: number;
  sourceEndSeconds?: number;
}
export function SwingVideoPlayer({
  file,
  pose,
  onTime,
  onDuration,
  subjectPoint,
  onSubjectPoint,
  disabled,
  sourceStartSeconds = 0,
  sourceEndSeconds,
}: Props) {
  const [selecting, setSelecting] = useState(false);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const analysisStart = pose?.video.source_start_seconds ?? sourceStartSeconds;
  useEffect(() => {
    const player = video.current;
    if (player && player.readyState >= 1) {
      player.pause();
      player.currentTime = analysisStart;
    }
    setSelecting(false);
  }, [analysisStart]);
  const [url, setUrl] = useState<string | null>(null);
  const [overlay, setOverlay] = useState(true);
  const [frameIndex, setFrameIndex] = useState(-1);
  const [speed, setSpeed] = useState("1");
  const [nativeRatio, setNativeRatio] = useState<number | null>(null);
  const [playbackError, setPlaybackError] = useState(false);
  useEffect(() => {
    if (!file) {
      setUrl(null);
      return;
    }
    const next = URL.createObjectURL(file);
    setUrl(next);
    setNativeRatio(null);
    setPlaybackError(false);
    setSelecting(false);
    setSelectionError(null);
    setFrameIndex(-1);
    return () => URL.revokeObjectURL(next);
  }, [file]);
  useEffect(() => {
    if (video.current) video.current.playbackRate = Number(speed);
  }, [speed, url]);
  useEffect(() => {
    const element = video.current;
    if (!element || !pose) {
      setFrameIndex(-1);
      return;
    }
    let alive = true,
      callbackId: number | undefined;
    const update = (time: number) =>
      setFrameIndex(
        nearestPoseFrame(
          pose.frames,
          time - analysisStart,
          Math.max(0.1, 1.5 / pose.video.nominal_fps),
        ),
      );
    const frame = (_: number, metadata: VideoFrameCallbackMetadata) => {
      if (!alive) return;
      update(metadata.mediaTime);
      callbackId = element.requestVideoFrameCallback(frame);
    };
    const seek = () => update(element.currentTime);
    element.addEventListener("seeked", seek);
    element.addEventListener("timeupdate", seek);
    seek();
    if ("requestVideoFrameCallback" in element)
      callbackId = element.requestVideoFrameCallback(frame);
    return () => {
      alive = false;
      element.removeEventListener("seeked", seek);
      element.removeEventListener("timeupdate", seek);
      if (callbackId !== undefined)
        element.cancelVideoFrameCallback(callbackId);
    };
  }, [pose, url, analysisStart]);
  const currentFrame = pose && frameIndex >= 0 ? pose.frames[frameIndex] : null;
  const aligned =
    !pose ||
    nativeRatio === null ||
    Math.abs(nativeRatio / (pose.video.width / pose.video.height) - 1) < 0.02;
  const tracked = currentFrame
    ? Object.values(currentFrame.landmarks).filter((point) => point?.xy_px)
        .length
    : 0;
  return (
    <section className="panel video-panel" aria-labelledby="video-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">02 / THE BIG PICTURE</p>
          <h2 id="video-title">See your movement.</h2>
        </div>
        <span className={`status-pill ${pose ? "status-green" : ""}`}>
          {pose ? "Pose ready" : file ? "Video preview" : "Awaiting a swing"}
        </span>
      </div>
      <div className={`video-stage ${file ? "has-video" : ""}`}>
        {url ? (
          <>
            <video
              ref={video}
              src={url}
              controls
              playsInline
              preload="metadata"
              aria-label="Your golf swing video"
              onError={() => setPlaybackError(true)}
              onLoadedMetadata={(event) => {
                const player = event.currentTarget;
                setNativeRatio(player.videoWidth / player.videoHeight);
                onDuration(
                  Number.isFinite(player.duration)
                    ? player.duration
                    : undefined,
                );
                player.playbackRate = Number(speed);
                if (analysisStart > 0) player.currentTime = analysisStart;
              }}
              onDurationChange={(event) => {
                const duration = event.currentTarget.duration;
                if (Number.isFinite(duration)) onDuration(duration);
              }}
              onTimeUpdate={(event) => {
                onTime(
                  Math.max(0, event.currentTarget.currentTime - analysisStart),
                );
                if (
                  sourceEndSeconds !== undefined &&
                  event.currentTarget.currentTime >= sourceEndSeconds
                )
                  event.currentTarget.pause();
              }}
            />
            {overlay && aligned && currentFrame && pose && (
              <PoseOverlay frame={currentFrame} video={pose.video} />
            )}
            {selecting && (
              <button
                type="button"
                className="subject-picker"
                disabled={disabled}
                aria-label="Select your torso in the first analyzed video frame"
                onClick={(event) => {
                  const player = video.current;
                  if (!player) return;
                  const rect = event.currentTarget.getBoundingClientRect();
                  const point = videoPointFromClick(
                    event.clientX - rect.left,
                    event.clientY - rect.top,
                    rect.width,
                    rect.height,
                    player.videoWidth,
                    player.videoHeight,
                  );
                  if (!point) {
                    setSelectionError(
                      "Click inside the video, rather than the surrounding bars.",
                    );
                    return;
                  }
                  onSubjectPoint(point);
                  setSelecting(false);
                  setSelectionError(null);
                }}
              >
                <span>Click inside your torso in the first analyzed frame</span>
              </button>
            )}
          </>
        ) : (
          <div className="video-empty">
            <div className="viewfinder" aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
              <Icon name="flag" width={48} height={48} />
            </div>
            <h3>A better swing starts here.</h3>
            <p>
              Upload a clip or record your swing.
              <br />
              Your movement will come into focus here.
            </p>
            <span className="empty-caption">
              A clear view. A more useful next step.
            </span>
          </div>
        )}
      </div>
      {playbackError && (
        <p className="message message-warning" role="status">
          Your browser cannot play this video format. Analysis may still work.
          MP4 (H.264) or WebM is best for playback.
        </p>
      )}
      {pose && !aligned && (
        <p className="message message-warning" role="status">
          The video’s display orientation differs from the pose coordinates. The
          overlay is hidden to avoid misalignment.
        </p>
      )}
      <div className="video-toolbar">
        <div className="pose-legend">
          <span className="legend-dot" />
          <span>
            {pose
              ? `${tracked} landmarks visible`
              : "Pose overlay after analysis"}
          </span>
          {pose && (
            <span className="interpolation-legend">
              <span className="legend-dot amber" />
              Interpolated
            </span>
          )}
        </div>
        <div className="video-tools">
          <button
            type="button"
            className="overlay-button"
            disabled={!file || disabled || playbackError}
            aria-pressed={selecting}
            onClick={() => {
              if (selecting) {
                setSelecting(false);
                return;
              }
              if (video.current) {
                video.current.pause();
                video.current.currentTime = analysisStart;
                onTime(0);
                setSelecting(true);
              }
            }}
          >
            {selecting
              ? "Cancel selection"
              : subjectPoint
                ? "Change golfer"
                : "Select golfer"}
          </button>
          <label className="speed-select">
            Speed
            <select
              aria-label="Video playback speed"
              value={speed}
              onChange={(event) => setSpeed(event.target.value)}
              disabled={!file}
            >
              <option value="0.25">0.25×</option>
              <option value="0.5">0.5×</option>
              <option value="1">1×</option>
            </select>
          </label>
          <button
            type="button"
            className={`overlay-button ${overlay ? "enabled" : ""}`}
            disabled={!pose || !aligned}
            aria-pressed={overlay}
            onClick={() => setOverlay(!overlay)}
          >
            <Icon name="eye" width={16} />
            Pose
          </button>
        </div>
      </div>
      {subjectPoint && (
        <p className="help-text subject-status" role="status">
          Golfer selected at {(subjectPoint[0] * 100).toFixed(1)}% from left,{" "}
          {(subjectPoint[1] * 100).toFixed(1)}% from top in the first analyzed
          frame.
        </p>
      )}
      {selectionError && (
        <p className="message message-warning" role="status">
          {selectionError}
        </p>
      )}
      {pose && (
        <details className="pose-details">
          <summary>
            Current frame details
            <span>
              {currentFrame
                ? `${currentFrame.timestamp_seconds.toFixed(3)}s`
                : "No nearby tracked frame"}
            </span>
          </summary>
          {currentFrame && (
            <dl className="angle-readout">
              {Object.entries(currentFrame.angles_deg).map(([name, value]) => (
                <div key={name}>
                  <dt>{name.replaceAll("_", " ")}</dt>
                  <dd>
                    {value === null ? "Unavailable" : `${value.toFixed(1)}°`}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </details>
      )}
    </section>
  );
}
