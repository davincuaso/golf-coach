import type { AnalysisResponse } from "@/lib/api-types";
import { Icon } from "@/components/ui/Icon";

export function CoachingFeedback({ result }: { result: AnalysisResponse }) {
  return (
    <section className="panel feedback-panel" aria-labelledby="feedback-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">YOUR PRACTICE NOTES</p>
          <h2 id="feedback-title">Take it to the range.</h2>
        </div>
        <span className="section-icon">
          <Icon name="flag" />
        </span>
      </div>
      <span className="status-pill">Rule-based observations</span>
      <div className="rule-feedback">
        {result.coaching.faults.length === 0 ? (
          <div className="no-faults">
            <span className="file-check">
              <Icon name="check" />
            </span>
            <h3>No rule-based flags in this clip.</h3>
            <p>
              Review the measurement notes and coverage before drawing
              conclusions about your swing.
            </p>
          </div>
        ) : (
          result.coaching.faults.map((fault, index) => (
            <article className="fault-card" key={fault.code}>
              <div className="fault-title">
                <span className="fault-number">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <h3>{fault.title}</h3>
                <span className="severity-pill">{fault.severity}</span>
              </div>
              <p>{fault.explanation}</p>
              <details>
                <summary>View measured evidence</summary>
                <dl>
                  {Object.entries(fault.evidence).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replaceAll("_", " ")}</dt>
                      <dd>
                        {typeof value === "number"
                          ? Number(value.toFixed(3))
                          : value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </details>
            </article>
          ))
        )}
      </div>
      {result.coaching.drills.length > 0 && (
        <div className="drill-list">
          <h3>Make your next rep count.</h3>
          {result.coaching.drills.map((drill, index) => (
            <details className="drill-card" key={drill.id}>
              <summary>
                <span className="drill-index">
                  {String(index + 1).padStart(2, "0")}
                </span>
                {drill.name}
                <span className="ml-auto" aria-hidden="true">
                  +
                </span>
              </summary>
              <ol>
                {drill.instructions.map((instruction, step) => (
                  <li key={step}>{instruction}</li>
                ))}
              </ol>
            </details>
          ))}
        </div>
      )}
      {result.coaching.notices.length > 0 && (
        <div className="feedback-notices">
          {result.coaching.notices.map((notice, index) => (
            <p key={index}>{notice}</p>
          ))}
        </div>
      )}
    </section>
  );
}
