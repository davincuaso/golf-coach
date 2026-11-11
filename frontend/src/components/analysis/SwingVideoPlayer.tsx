"use client";
import { useEffect, useRef, useState } from "react";
import type { VisionDocument } from "@/lib/api-types";
import { nearestPoseFrame } from "@/lib/visualization";
import { Icon } from "@/components/ui/Icon";
import { PoseOverlay } from "./PoseOverlay";

interface Props {
  file: File | null;
  pose: VisionDocument | null;
  onTime: (time: number) => void;
  onDuration: (duration: number | undefined) => void;
}
export function SwingVideoPlayer({ file, pose, onTime, onDuration }: Props) {
  const video = useRef<HTMLVideoElement>(null);
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
          time,
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
  }, [pose, url]);
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
              }}
              onDurationChange={(event) => {
                const duration = event.currentTarget.duration;
                if (Number.isFinite(duration)) onDuration(duration);
              }}
              onTimeUpdate={(event) => onTime(event.currentTarget.currentTime)}
            />
            {overlay && aligned && currentFrame && pose && (
              <PoseOverlay frame={currentFrame} video={pose.video} />
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
