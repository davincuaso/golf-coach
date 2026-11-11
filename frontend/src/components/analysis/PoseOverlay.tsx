import type { LandmarkName, PoseFrame, VisionDocument } from "@/lib/api-types";

const connections: [LandmarkName, LandmarkName][] = [
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
  ["nose", "left_eye"],
  ["nose", "right_eye"],
  ["left_eye", "left_ear"],
  ["right_eye", "right_ear"],
];
export function PoseOverlay({
  frame,
  video,
}: {
  frame: PoseFrame;
  video: VisionDocument["video"];
}) {
  const radius = Math.max(video.width, video.height) * 0.004;
  return (
    <svg
      className="pose-overlay"
      viewBox={`0 0 ${video.width} ${video.height}`}
      preserveAspectRatio="xMidYMid meet"
      aria-label={`Tracked body landmarks at ${frame.timestamp_seconds.toFixed(2)} seconds`}
      role="img"
    >
      <title>Body pose overlay</title>
      {connections.map(([a, b]) => {
        const from = frame.landmarks[a],
          to = frame.landmarks[b];
        if (!from?.xy_px || !to?.xy_px) return null;
        const inferred = from.interpolated || to.interpolated;
        return (
          <line
            key={`${a}-${b}`}
            x1={from.xy_px[0]}
            y1={from.xy_px[1]}
            x2={to.xy_px[0]}
            y2={to.xy_px[1]}
            stroke={inferred ? "#efc77b" : "#87efc3"}
            strokeWidth={radius * 0.65}
            strokeDasharray={inferred ? `${radius * 2} ${radius}` : undefined}
          />
        );
      })}
      {Object.entries(frame.landmarks).map(
        ([name, landmark]) =>
          landmark?.xy_px && (
            <circle
              key={name}
              cx={landmark.xy_px[0]}
              cy={landmark.xy_px[1]}
              r={radius}
              fill={landmark.interpolated ? "#42331f" : "#d6ffed"}
              stroke={landmark.interpolated ? "#efc77b" : "#215d49"}
              strokeWidth={radius * 0.4}
            >
              <title>
                {name.replaceAll("_", " ")}
                {landmark.interpolated ? " (interpolated)" : ""}
              </title>
            </circle>
          ),
      )}
    </svg>
  );
}
