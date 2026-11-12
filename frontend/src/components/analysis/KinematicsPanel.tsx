import type { Kinematics } from "@/lib/api-types";
import { formatMetric } from "@/lib/visualization";
import { KinematicsChart } from "./KinematicsChart";

export function MetricCards({ data }: { data: Kinematics | null }) {
  const cards = [
    {
      label: "SWING TEMPO",
      value: formatMetric(data?.tempo_ratio ?? null, " : 1", 2),
      note:
        data?.tempo_ratio != null
          ? `${formatMetric(data.backswing_seconds, "s", 2)} back / ${formatMetric(data.downswing_seconds, "s", 2)} down`
          : "Needs reliable swing timing",
      index: "01",
    },
    {
      label: "POSTURE CHANGE",
      value: formatMetric(data?.spine_delta_deg ?? null, "°"),
      note: data?.quality.posture.eligible
        ? "Impact tilt minus address tilt"
        : "Needs confirmed view and usable tracking",
      index: "02",
    },
    {
      label: "MAX. POSTURE LOSS",
      value: formatMetric(data?.max_posture_loss_deg ?? null, "°"),
      note: data?.posture_eligible
        ? "Largest reduction in forward tilt"
        : "Withheld by view / quality checks",
      index: "03",
    },
    {
      label: "TORSO TRACKING",
      value: data
        ? `${Math.round(data.quality.tracking.torso_valid_fraction * 100)}%`
        : "—",
      note: "Usable torso samples in evaluated window",
      index: "04",
    },
  ];
  return (
    <section className="metrics-grid" aria-label="Swing metrics">
      {cards.map((card) => (
        <article className="panel metric-card" key={card.label}>
          <div className="metric-label">
            {card.label}
            <span>{card.index}</span>
          </div>
          <p className="metric-value">{card.value}</p>
          <p className="help-text">{card.note}</p>
        </article>
      ))}
    </section>
  );
}
export function KinematicsPanel({
  data,
  playhead,
}: {
  data: Kinematics;
  playhead: number;
}) {
  return (
    <section
      className="panel kinematics-panel"
      aria-labelledby="kinematics-title"
    >
      <div className="panel-heading">
        <div>
          <p className="eyebrow">03 / THE DETAILS</p>
          <h2 id="kinematics-title">Your swing, measured.</h2>
        </div>
        <span className="status-pill">{data.status.replaceAll("_", " ")}</span>
      </div>
      <div className="chart-legend">
        <span>
          <i className="line-swatch" />
          Your movement
        </span>
        <span>
          <i className="line-swatch baseline" />
          Address baseline
        </span>
        <span>S / Start · T / Top · I / Impact</span>
      </div>
      <KinematicsChart
        title="2D torso projection"
        description="Projected shoulder-to-hip angle from image vertical. Technique comparisons require the view and quality gates to pass."
        unit="degrees"
        points={data.series.map((point) => ({
          time: point.timestamp_seconds,
          value: point.spine_tilt_deg,
        }))}
        playhead={playhead}
        events={data.events}
        baseline={data.baseline_spine_tilt_deg}
      />
      <KinematicsChart
        title="Wrist motion"
        description="2D wrist speed relative to torso length. This is not clubhead speed."
        unit="torso lengths / s"
        points={data.series.map((point) => ({
          time: point.timestamp_seconds,
          value: point.wrist_speed_torso_per_second,
        }))}
        playhead={playhead}
        events={data.events}
      />
      <div className="chart-footnote">
        {data.event_source
          ? `Swing markers: ${data.event_source}. `
          : "Swing markers unavailable. "}
        {data.timing_reliable
          ? "Timing is reliable."
          : "Timing is uncertain; tempo may be unavailable."}
      </div>
      {data.warnings.length > 0 && (
        <details className="analysis-notices">
          <summary>Measurement notes ({data.warnings.length})</summary>
          <ul>
            {data.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
