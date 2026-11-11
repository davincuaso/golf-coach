"use client";
import type { AnalysisResponse } from "@/lib/api-types";
import { useApiKey } from "@/state/ApiKeyContext";
import { Icon } from "@/components/ui/Icon";

export function CoachingFeedback({ result }: { result: AnalysisResponse }) {
  const { apiKey, llmEnabled, hydrated } = useApiKey();
  const showNarrative =
    hydrated &&
    llmEnabled &&
    Boolean(apiKey) &&
    result.llm.status === "complete" &&
    result.llm.narrative !== null;
  const narrative = showNarrative ? result.llm.narrative : null;
  const drills = narrative
    ? result.coaching.drills.filter((drill) =>
        narrative.recommended_drill_ids.includes(drill.id),
      )
    : result.coaching.drills;
  return (
    <section className="panel feedback-panel" aria-labelledby="feedback-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">04 / YOUR NEXT STEP</p>
          <h2 id="feedback-title">Take it to the range.</h2>
        </div>
        <span className="section-icon">
          <Icon name={narrative ? "spark" : "flag"} />
        </span>
      </div>
      <span className={`status-pill ${narrative ? "status-green" : ""}`}>
        {narrative ? "AI coaching synthesis" : "Rule-based observations"}
      </span>
      {narrative ? (
        <div className="narrative">
          <p className="coaching-summary">{narrative.summary}</p>
          {narrative.possible_root_cause && (
            <div className="root-cause">
              <p className="eyebrow">POSSIBLE CONTRIBUTING FACTOR</p>
              <p>{narrative.possible_root_cause}</p>
            </div>
          )}
          {narrative.priorities.length > 0 && (
            <div className="coaching-priorities">
              <h3>Focus for this session</h3>
              <ul>
                {narrative.priorities.map((priority, index) => (
                  <li key={`${priority.fault_code}-${index}`}>
                    {priority.explanation}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="practice-plan">
            <h3>Your practice plan</h3>
            <p>{narrative.practice_plan}</p>
          </div>
          <p className="help-text mt-3">
            AI suggestions build on the measured observations. Treat possible
            causes as hypotheses to explore.
          </p>
        </div>
      ) : (
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
                  <span className="fault-number">0{index + 1}</span>
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
      )}
      {!narrative && llmEnabled && result.llm.reason && (
        <p className="message message-warning" role="status">
          {result.llm.reason}
        </p>
      )}
      {!narrative && llmEnabled && result.llm.status === "disabled" && (
        <p className="help-text mt-4">
          This swing was analyzed with AI coaching off. Analyze again to add a
          coaching narrative.
        </p>
      )}
      {drills.length > 0 && (
        <div className="drill-list">
          <h3>Make your next rep count.</h3>
          {drills.map((drill, index) => (
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
