import type { AnalysisQuality, CameraView } from "@/lib/api-types";
import { Icon } from "@/components/ui/Icon";

const views: Record<CameraView, string> = {
  down_the_line: "Down the line",
  face_on: "Face on",
  oblique: "Oblique / diagonal",
  rear: "Rear body view",
  overhead: "Overhead / elevated",
  unknown: "Not specified",
};
export function CaptureQualityPanel({
  quality,
  eventSource,
}: {
  quality: AnalysisQuality;
  eventSource: "manual" | "estimated" | null;
}) {
  const tracking = quality.tracking;
  const stats = [
    ["Torso tracking", tracking.torso_valid_fraction],
    ["Hands + torso", tracking.wrist_pair_valid_fraction],
    ["Body anchors", tracking.full_body_valid_fraction],
  ] as const;
  return (
    <section className="panel quality-panel" aria-labelledby="quality-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">CHECK THE EVIDENCE FIRST</p>
          <h2 id="quality-title">View & tracking quality</h2>
        </div>
        <span
          className={`status-pill ${quality.status === "usable" ? "status-green" : ""}`}
        >
          {quality.status === "usable"
            ? "Checks passed"
            : quality.status === "limited"
              ? "Some measurements withheld"
              : "Insufficient tracking"}
        </span>
      </div>
      <div className="quality-view">
        <Icon name="camera" width={18} />
        <div>
          <strong>{views[quality.camera.declared_view]}</strong>
          <p>
            {quality.camera.assessment === "projection_conflict"
              ? "Body projection conflicts with the selected view. Recheck the camera setup."
              : quality.camera.alignment_confirmed
                ? "Alignment confirmed by you; this does not calibrate the camera."
                : "Camera alignment has not been confirmed."}
          </p>
        </div>
        <span className="quality-window">
          {quality.window_source === "swing" ? "Swing window" : "Whole clip"}:{" "}
          {quality.window_start_seconds.toFixed(2)}–
          {quality.window_end_seconds.toFixed(2)}s
        </span>
      </div>
      <div className="quality-stats">
        {stats.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{Math.round(value * 100)}%</strong>
          </div>
        ))}
        <div>
          <span>Longest torso gap</span>
          <strong>
            {Math.round(tracking.largest_torso_gap_seconds * 1000)} ms
          </strong>
        </div>
      </div>
      <div className="measurement-gates">
        {(
          [
            ["Posture change", quality.posture],
            ["Swing tempo", quality.tempo],
          ] as const
        ).map(([title, gate]) => {
          const measurement = gate;
          return (
            <div
              className={`measurement-gate ${measurement.eligible ? "available" : ""}`}
              key={String(title)}
            >
              <h3>
                <Icon
                  name={measurement.eligible ? "check" : "info"}
                  width={16}
                />
                {String(title)}
                <span>
                  {measurement.eligible
                    ? eventSource === "estimated"
                      ? "Provisional"
                      : "Available"
                    : "Withheld"}
                </span>
              </h3>
              {measurement.reasons.length > 0 ? (
                <ul>
                  {measurement.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              ) : (
                <p>
                  {eventSource === "estimated"
                    ? "Based on estimated swing markers. Review start/top/impact and reanalyze with manual markers before acting on technique alerts."
                    : "The required view, timing, and tracking checks for this measurement passed."}
                </p>
              )}
            </div>
          );
        })}
      </div>
      {quality.issues.length > 0 && (
        <details className="analysis-notices">
          <summary>
            How to improve this capture ({quality.issues.length})
          </summary>
          <ul>
            {quality.issues.map((issue) => (
              <li key={issue.code}>{issue.message}</li>
            ))}
          </ul>
        </details>
      )}
      <p className="quality-footnote">
        Coverage measures usable samples, not the probability that an angle is
        correct. {quality.camera.note}
      </p>
    </section>
  );
}
