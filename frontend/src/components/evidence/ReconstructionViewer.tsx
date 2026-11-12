"use client";
import { useMemo, useState } from "react";
import type { Reconstruction } from "@/lib/evidence-client";
const bones = [
  ["left_shoulder", "right_shoulder"],
  ["left_shoulder", "left_elbow"],
  ["left_elbow", "left_wrist"],
  ["right_shoulder", "right_elbow"],
  ["right_elbow", "right_wrist"],
  ["left_shoulder", "left_hip"],
  ["right_shoulder", "right_hip"],
  ["left_hip", "right_hip"],
  ["left_hip", "left_knee"],
  ["left_knee", "left_ankle"],
  ["right_hip", "right_knee"],
  ["right_knee", "right_ankle"],
];
export function ReconstructionViewer({ result }: { result: Reconstruction }) {
  const [frameIndex, setFrameIndex] = useState(0),
    [yaw, setYaw] = useState(25);
  const bounds = useMemo(() => {
    const points = result.frames.flatMap((frame) =>
      Object.values(frame.joints).map((joint) => joint.xyz_m),
    );
    const center = [0, 1, 0];
    let span = 2;
    if (points.length) {
      for (let axis = 0; axis < 3; axis++) {
        const values = points.map((point) => point[axis]);
        const low = Math.min(...values),
          high = Math.max(...values);
        center[axis] = (low + high) / 2;
        span = Math.max(span, high - low);
      }
    }
    return { center, span };
  }, [result]);
  const frame = result.frames[Math.min(frameIndex, result.frames.length - 1)];
  const project = (point: number[]) => {
    const [x, y, z] = point.map(
      (value, axis) => (value - bounds.center[axis]) / bounds.span,
    );
    const angle = (yaw * Math.PI) / 180;
    return [
      300 + (x * Math.cos(angle) + z * Math.sin(angle)) * 330,
      210 - y * 330 + (z * Math.cos(angle) - x * Math.sin(angle)) * 65,
    ];
  };
  return (
    <div className="evidence-result">
      <p className="status-pill status-green">
        {result.status.replaceAll("_", " ")}
      </p>
      <p>
        {result.accepted_joints} accepted joint samples ·{" "}
        {result.matched_frames} matched frames ·{" "}
        {result.median_reprojection_error_px?.toFixed(2) ?? "—"} px median
        reprojection error
      </p>
      <p className="help-text">
        Current frame mismatch: {frame?.matching_error_ms.toFixed(2) ?? "—"} ms.
        Coordinate gaps remain unknown.
      </p>
      <svg
        viewBox="0 0 600 420"
        className="reconstruction-view"
        role="img"
        aria-label="Rotatable reconstructed skeleton in metres"
      >
        <title>Calibrated 3D landmark estimates; gaps remain missing</title>
        <path
          d="M60 360H540M300 40V380"
          stroke="#d9e1d7"
          strokeDasharray="4 5"
        />
        {frame &&
          bones.map(([a, b]) => {
            const from = frame.joints[a],
              to = frame.joints[b];
            if (!from || !to) return null;
            const p = project(from.xyz_m),
              q = project(to.xyz_m);
            return (
              <line
                key={a + b}
                x1={p[0]}
                y1={p[1]}
                x2={q[0]}
                y2={q[1]}
                stroke="#32634c"
                strokeWidth={3}
              />
            );
          })}
        {frame &&
          Object.entries(frame.joints).map(([name, joint]) => {
            const p = project(joint.xyz_m);
            return (
              <circle key={name} cx={p[0]} cy={p[1]} r={4} fill="#76af87">
                <title>
                  {name}: {joint.xyz_m.map((x) => x.toFixed(3)).join(", ")} m
                </title>
              </circle>
            );
          })}
        <text x="20" y="26" fill="#526451" fontSize="13">
          {result.coordinate_system}
        </text>
        <text x="20" y="402" fill="#526451" fontSize="13">
          Torso tilt from vertical: {frame?.torso_tilt_deg?.toFixed(1) ?? "—"}°
        </text>
      </svg>
      <div className="session-fields">
        <label>
          Frame · {frame?.timestamp_seconds.toFixed(3) ?? "—"}s from sync event
          <input
            aria-label="3D frame"
            type="range"
            min="0"
            max={Math.max(0, result.frames.length - 1)}
            value={Math.min(frameIndex, Math.max(0, result.frames.length - 1))}
            onChange={(e) => setFrameIndex(Number(e.target.value))}
          />
        </label>
        <label>
          Rotate view · {yaw}°
          <input
            aria-label="Rotate 3D view"
            type="range"
            min="-180"
            max="180"
            value={yaw}
            onChange={(e) => setYaw(Number(e.target.value))}
          />
        </label>
      </div>
      <details className="analysis-notices">
        <summary>Reconstruction quality and limits</summary>
        <ul>
          {result.notices.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
        <p>
          Rejected samples:{" "}
          {Object.entries(result.rejected_joints)
            .map(([name, count]) => `${name.replaceAll("_", " ")}: ${count}`)
            .join(" · ") || "none"}
          . Unmatched frames: {result.unmatched_frames}.
        </p>
      </details>
    </div>
  );
}
