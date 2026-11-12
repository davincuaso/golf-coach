"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { EvidenceWorkbench } from "@/components/evidence/EvidenceWorkbench";
import type { EvidenceArtifact } from "@/lib/evidence-client";
import { Icon } from "@/components/ui/Icon";
import { SwingVideoPlayer } from "@/components/analysis/SwingVideoPlayer";
import { CaptureQualityPanel } from "@/components/analysis/CaptureQualityPanel";
import {
  KinematicsPanel,
  MetricCards,
} from "@/components/analysis/KinematicsPanel";
import { CoachingFeedback } from "@/components/analysis/CoachingFeedback";
import { AiCoachingPrompt } from "@/components/analysis/AiCoachingPrompt";
import { validateVideo, VIDEO_ACCEPT } from "@/lib/capture";
import { uploadAnalysis } from "@/lib/analysis-client";
import {
  combineSession,
  MAX_SESSION_CLIPS,
  readSourceDuration,
  sessionOptions,
  type SessionEntry,
  type SessionResponse,
} from "@/lib/session-client";
import type { CameraView } from "@/lib/api-types";

const views: [CameraView, string][] = [
  ["unknown", "Not sure yet"],
  ["down_the_line", "Down the line"],
  ["face_on", "Face on"],
  ["oblique", "Oblique / diagonal"],
  ["rear", "Rear body view"],
  ["overhead", "Overhead / elevated"],
];
export function SessionWorkspace() {
  const [entries, setEntries] = useState<SessionEntry[]>([]);
  const [activeId, setActiveId] = useState("");
  const [report, setReport] = useState<SessionResponse | null>(null);
  const [artifacts, setArtifacts] = useState<EvidenceArtifact[]>([]);
  const onArtifacts = useCallback((values: EvidenceArtifact[]) => {
    setArtifacts(values);
    setReport(null);
  }, []);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [playhead, setPlayhead] = useState(0);
  const [compareId, setCompareId] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, []);
  const active = entries.find((entry) => entry.id === activeId) ?? entries[0];
  const comparison = entries.find(
    (entry) =>
      entry.id === compareId &&
      entry.id !== active?.id &&
      entry.swingId === active?.swingId,
  );
  const update = (
    id: string,
    patch: Partial<SessionEntry>,
    invalidate = true,
  ) => {
    setEntries((previous) =>
      previous.map((entry) =>
        entry.id === id
          ? {
              ...entry,
              ...patch,
              ...(invalidate
                ? {
                    analysis: undefined,
                    status: "ready" as const,
                    error: undefined,
                  }
                : {}),
            }
          : entry,
      ),
    );
    setReport(null);
  };
  const addFiles = (files: FileList | null) => {
    if (!files || busy) return;
    setError(null);
    if (entries.length + files.length > MAX_SESSION_CLIPS) {
      setError(
        `Choose at most ${MAX_SESSION_CLIPS} video windows in one session.`,
      );
      return;
    }
    const next: SessionEntry[] = [];
    for (const file of Array.from(files)) {
      const issue = validateVideo(file);
      if (issue) {
        setError(`${file.name}: ${issue}`);
        continue;
      }
      next.push({
        id: crypto.randomUUID(),
        file,
        swingId: `Swing ${entries.length + next.length + 1}`,
        start: "0",
        end: "",
        cameraView: "unknown",
        alignment: false,
        markers: ["", "", ""],
        subject: ["", ""],
        status: "ready",
      });
    }
    setEntries((previous) => [...previous, ...next]);
    setReport(null);
    if (!active && next[0]) setActiveId(next[0].id);
    for (const entry of next)
      void readSourceDuration(entry.file).then((duration) => {
        if (!mounted.current) return;
        setEntries((previous) =>
          previous.map((value) =>
            value.id === entry.id
              ? {
                  ...value,
                  duration,
                  end:
                    value.end ||
                    (duration ? Math.min(30, duration).toFixed(3) : ""),
                }
              : value,
          ),
        );
      });
  };
  const addWindow = () => {
    if (!active || entries.length >= MAX_SESSION_CLIPS || busy) return;
    const start = Math.min(
      Number(active.end) || 0,
      Math.max(0, (active.duration ?? 30) - 5),
    );
    const entry: SessionEntry = {
      ...active,
      id: crypto.randomUUID(),
      swingId: `Swing ${entries.length + 1}`,
      start: start.toFixed(3),
      end: Math.min(start + 5, active.duration ?? start + 5).toFixed(3),
      markers: ["", "", ""],
      subject: ["", ""],
      alignment: false,
      analysis: undefined,
      status: "ready",
      error: undefined,
    };
    setEntries((previous) => [...previous, entry]);
    setActiveId(entry.id);
    setReport(null);
  };
  const combine = async (
    values: SessionEntry[],
    attempted: number,
    signal: AbortSignal,
  ) => {
    if (!values.some((entry) => entry.analysis))
      throw new Error("No completed clips are available yet.");
    const result = await combineSession(
      values,
      attempted,
      signal,
      artifacts.map((item) => item.result.evidence_token),
    );
    if (mounted.current) setReport(result);
  };
  const analyze = async () => {
    if (!entries.length || busy) return;
    setError(null);
    setReport(null);
    try {
      for (const entry of entries) sessionOptions(entry);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Check the clip windows.",
      );
      return;
    }
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    const completed = entries.map((entry) => ({ ...entry }));
    try {
      for (let index = 0; index < completed.length; index++) {
        const entry = completed[index];
        if (entry.analysis) continue;
        if (abort.signal.aborted) break;
        setActiveId(entry.id);
        update(entry.id, { status: "uploading", error: undefined }, false);
        try {
          const result = await uploadAnalysis(
            entry.file,
            sessionOptions(entry),
            abort.signal,
            (value) => {
              if (!mounted.current) return;
              setProgress(
                `Video ${index + 1} / ${completed.length} · ${value.phase === "uploading" ? `Uploading${value.percent === undefined ? "" : ` ${value.percent}%`}` : "Analyzing selected window"}`,
              );
              setEntries((previous) =>
                previous.map((item) =>
                  item.id === entry.id
                    ? { ...item, status: value.phase }
                    : item,
                ),
              );
            },
          );
          entry.analysis = result;
          entry.status = "done";
          if (mounted.current)
            update(entry.id, { analysis: result, status: "done" }, false);
        } catch (cause) {
          entry.status = "failed";
          entry.error = abort.signal.aborted
            ? "Canceled. Completed videos are still available."
            : cause instanceof Error
              ? cause.message
              : "This clip could not be analyzed.";
          if (mounted.current)
            update(entry.id, { status: "failed", error: entry.error }, false);
          if (abort.signal.aborted) break;
        }
      }
      if (abort.signal.aborted) {
        setError(
          "Session processing canceled. You can combine completed videos or retry the remaining windows.",
        );
        return;
      }
      setProgress("Combining supported evidence across the session…");
      await combine(completed, completed.length, abort.signal);
    } catch (cause) {
      if (mounted.current)
        setError(
          cause instanceof Error
            ? cause.message
            : "Session analysis could not be completed.",
        );
    } finally {
      if (mounted.current) {
        setBusy(false);
        setProgress("");
        controller.current = null;
      }
    }
  };
  const combineCompleted = async () => {
    if (busy) return;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setError(null);
    try {
      await combine(entries, entries.length, abort.signal);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Session report unavailable.",
      );
    } finally {
      if (mounted.current) {
        setBusy(false);
        controller.current = null;
      }
    }
  };
  const download = () => {
    const data = {
      session: report,
      additional_evidence_reports: artifacts,
      clips: entries.map((entry, index) => ({
        clip_id: entry.id,
        label: `Video ${index + 1}`,
        swing_id: entry.swingId,
        source_start_seconds: Number(entry.start),
        source_end_seconds: Number(entry.end),
        analysis: entry.analysis ?? null,
        error: entry.error ?? null,
      })),
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `golf-session-${report?.session_id ?? "partial"}.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <div>
      <div className="page-heading">
        <div>
          <p className="eyebrow">THE SESSION LAB</p>
          <h1>One session. Every useful view.</h1>
          <p className="page-description">
            Combine separate swings and linked views, with the source and
            quality of every measurement preserved.
          </p>
        </div>
        {entries.some((entry) => entry.analysis) && (
          <button className="button button-secondary" onClick={download}>
            <Icon name="download" />
            Save session
          </button>
        )}
      </div>
      <div className="notice session-intro">
        <Icon name="info" />
        <p>
          Add up to eight video windows, with source recordings up to 250 MiB
          each. Choose up to 30 seconds per window around one swing. Use the
          same swing ID only for views of the exact same swing. Different swings
          keep different IDs. Keep this page open while processing and save the
          session JSON to retain the report.
        </p>
      </div>
      <div className="session-toolbar">
        <input
          ref={input}
          className="sr-only"
          type="file"
          multiple
          accept={VIDEO_ACCEPT}
          disabled={busy}
          aria-label="Choose session videos"
          onChange={(event) => {
            addFiles(event.currentTarget.files);
            event.currentTarget.value = "";
          }}
        />
        <button
          className="button button-secondary"
          disabled={busy || entries.length >= MAX_SESSION_CLIPS}
          onClick={() => input.current?.click()}
        >
          <Icon name="upload" />
          Add videos
        </button>
        <button
          className="button button-secondary"
          disabled={busy || !active || entries.length >= MAX_SESSION_CLIPS}
          onClick={addWindow}
        >
          Another window from this recording
        </button>
        <button
          className="button button-primary"
          disabled={busy || !entries.length}
          onClick={analyze}
        >
          {busy ? "Processing session…" : "Analyze session"}
          <Icon name="arrow" />
        </button>
        {busy && (
          <button
            className="text-button"
            onClick={() => controller.current?.abort()}
          >
            Cancel
          </button>
        )}
      </div>
      {progress && (
        <p className="message message-success" role="status">
          {progress}
        </p>
      )}
      {error && (
        <p className="message message-error" role="alert">
          {error}
        </p>
      )}
      {entries.length > 0 && (
        <div className="session-editor">
          <aside className="panel session-list" aria-label="Session videos">
            {entries.map((entry, index) => (
              <button
                key={entry.id}
                className={`session-entry ${entry.id === active?.id ? "selected" : ""}`}
                onClick={() => {
                  setActiveId(entry.id);
                  setCompareId("");
                  setPlayhead(0);
                }}
              >
                <span className="eyebrow">
                  VIDEO {index + 1} · {entry.status}
                </span>
                <strong>{entry.file.name}</strong>
                <span>
                  {entry.swingId} · {entry.start || "0"}–{entry.end || "?"}s
                </span>
                {entry.error && (
                  <span className="session-row-error">{entry.error}</span>
                )}
              </button>
            ))}
          </aside>
          {active && (
            <section className="panel session-options">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">SELECTED VIDEO WINDOW</p>
                  <h2>{active.file.name}</h2>
                  <p className="help-text">
                    {active.duration === undefined
                      ? "Duration unavailable; enter a valid end time."
                      : `${active.duration.toFixed(2)}s source · ${(active.file.size / 1048576).toFixed(1)} MiB`}
                  </p>
                </div>
                <button
                  className="icon-button"
                  disabled={busy}
                  aria-label="Remove selected video window"
                  onClick={() => {
                    setEntries((previous) =>
                      previous.filter((entry) => entry.id !== active.id),
                    );
                    setReport(null);
                    setActiveId("");
                  }}
                >
                  <Icon name="close" />
                </button>
              </div>
              {active.analysis && (
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() =>
                    update(active.id, { status: "ready", error: undefined })
                  }
                >
                  Clear this result to reanalyze
                </button>
              )}
              <fieldset disabled={busy}>
                <div className="session-fields">
                  <label>
                    Swing ID
                    <input
                      className="field"
                      aria-label="Swing ID"
                      maxLength={40}
                      value={active.swingId}
                      onChange={(event) =>
                        update(
                          active.id,
                          { swingId: event.target.value },
                          false,
                        )
                      }
                    />
                  </label>
                  <label>
                    Camera view
                    <select
                      className="field"
                      aria-label="Session camera view"
                      value={active.cameraView}
                      onChange={(event) =>
                        update(active.id, {
                          cameraView: event.target.value as CameraView,
                          alignment: false,
                        })
                      }
                    >
                      {views.map(([value, text]) => (
                        <option key={value} value={value}>
                          {text}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Source start (seconds)
                    <input
                      className="field"
                      type="number"
                      min="0"
                      step="any"
                      aria-label="Source window start"
                      value={active.start}
                      onChange={(event) =>
                        update(active.id, {
                          start: event.target.value,
                          markers: ["", "", ""],
                          subject: ["", ""],
                          alignment: false,
                        })
                      }
                    />
                  </label>
                  <label>
                    Source end (seconds)
                    <input
                      className="field"
                      type="number"
                      min="0"
                      step="any"
                      aria-label="Source window end"
                      value={active.end}
                      onChange={(event) =>
                        update(active.id, {
                          end: event.target.value,
                          alignment: false,
                        })
                      }
                    />
                  </label>
                </div>
                {active.cameraView === "down_the_line" && (
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={active.alignment}
                      onChange={(event) =>
                        update(active.id, { alignment: event.target.checked })
                      }
                    />
                    This camera is level, stationary, and aligned down the
                    target line.
                  </label>
                )}
                <p className="help-text mt-3">
                  Mark start/top/impact in seconds from the beginning of this
                  selected window. Use the preview time buttons, then check each
                  marker. Blank markers use provisional estimation.
                </p>
                <div className="marker-inputs mt-3">
                  {["Start", "Top", "Impact"].map((label, index) => (
                    <label key={label}>
                      {label}
                      <input
                        className="field"
                        type="number"
                        min="0"
                        step="any"
                        aria-label={`Session ${label.toLowerCase()} marker`}
                        value={active.markers[index]}
                        onChange={(event) => {
                          const markers = [...active.markers] as [
                            string,
                            string,
                            string,
                          ];
                          markers[index] = event.target.value;
                          update(active.id, { markers });
                        }}
                      />
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => {
                          const markers = [...active.markers] as [
                            string,
                            string,
                            string,
                          ];
                          markers[index] = playhead.toFixed(3);
                          update(active.id, { markers });
                        }}
                      >
                        Use preview time
                      </button>
                    </label>
                  ))}
                </div>
                <p className="help-text mt-3">
                  Select your torso in the preview if other golfers are visible.
                  The point applies to the first frame of this window.
                </p>
              </fieldset>
            </section>
          )}
        </div>
      )}
      {active && (
        <div className={`session-preview ${comparison ? "comparing" : ""}`}>
          <SwingVideoPlayer
            file={active.file}
            pose={active.analysis?.pose ?? null}
            onTime={setPlayhead}
            onDuration={() => {}}
            sourceStartSeconds={Number(active.start) || 0}
            sourceEndSeconds={Number(active.end) || undefined}
            subjectPoint={
              active.subject.every((value) => value.trim() !== "")
                ? [Number(active.subject[0]), Number(active.subject[1])]
                : undefined
            }
            onSubjectPoint={(point) =>
              update(active.id, {
                subject: [point[0].toFixed(5), point[1].toFixed(5)],
              })
            }
            disabled={busy}
          />
          {comparison && (
            <SwingVideoPlayer
              file={comparison.file}
              pose={comparison.analysis?.pose ?? null}
              onTime={() => {}}
              onDuration={() => {}}
              sourceStartSeconds={Number(comparison.start) || 0}
              sourceEndSeconds={Number(comparison.end) || undefined}
              onSubjectPoint={() => {}}
              disabled
            />
          )}
        </div>
      )}
      {active &&
        entries.some(
          (entry) => entry.id !== active.id && entry.swingId === active.swingId,
        ) && (
          <label className="field-label mt-4">
            Compare another view of {active.swingId}
            <select
              className="field"
              aria-label="Compare session view"
              value={comparison?.id ?? ""}
              onChange={(event) => setCompareId(event.target.value)}
            >
              <option value="">Single view</option>
              {entries
                .filter(
                  (entry) =>
                    entry.id !== active.id && entry.swingId === active.swingId,
                )
                .map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.file.name}
                  </option>
                ))}
            </select>
            <span className="help-text">
              Independent playback. Linking swing IDs does not verify
              synchronization or calibrate a 3D reconstruction.
            </span>
          </label>
        )}
      <EvidenceWorkbench
        entries={entries}
        disabled={busy}
        onArtifacts={onArtifacts}
      />
      {entries.some((entry) => entry.analysis) && !busy && (
        <button
          className="button button-secondary mt-5"
          onClick={combineCompleted}
        >
          Build / refresh session report
        </button>
      )}
      {report && (
        <section className="session-report">
          <div className="page-heading">
            <div>
              <p className="eyebrow">COMBINED EVIDENCE</p>
              <h2>Session report</h2>
              <p className="help-text">
                {report.analyzed_clips} / {report.attempted_clips} windows
                analyzed · {report.unique_swings} distinct swing groups ·{" "}
                {report.status}
              </p>
            </div>
          </div>
          <div className="metrics-grid">
            <div className="panel metric-card">
              <p className="eyebrow">REVIEWED TEMPO</p>
              <p className="metric-value">
                {report.tempo.median === null
                  ? "—"
                  : `${report.tempo.median.toFixed(2)} : 1`}
              </p>
              <p className="help-text">
                Median across {report.tempo.swings} reviewed swings
              </p>
            </div>
            <div className="panel metric-card">
              <p className="eyebrow">REVIEWED POSTURE LOSS</p>
              <p className="metric-value">
                {report.posture_loss.median === null
                  ? "—"
                  : `${report.posture_loss.median.toFixed(1)}°`}
              </p>
              <p className="help-text">
                Median across {report.posture_loss.swings} supported swings
              </p>
            </div>
          </div>
          <p className="help-text mb-4">
            Session statistics use reviewed manual markers and eligible
            measurements. Provisional per-video measurements remain available
            below.
          </p>
          <div className="session-swings">
            {report.swings.map((swing) => (
              <article className="panel" key={swing.swing_id}>
                <h3>{swing.swing_id}</h3>
                <p className="help-text">
                  {swing.clip_ids.length} view(s) · Tempo:{" "}
                  {swing.tempo_ratio?.toFixed(2) ?? "unavailable"} · Posture
                  loss:{" "}
                  {swing.max_posture_loss_deg === null
                    ? "unavailable"
                    : `${swing.max_posture_loss_deg.toFixed(1)}°`}
                </p>
                <p className="help-text">
                  Sources:{" "}
                  {swing.clip_ids
                    .map(
                      (id) =>
                        `Video ${entries.findIndex((entry) => entry.id === id) + 1}`,
                    )
                    .join(", ")}
                </p>
                {(swing.tempo_source || swing.posture_source) && (
                  <p className="help-text">
                    Selected measurements:{" "}
                    {[
                      swing.tempo_source &&
                        `tempo from Video ${entries.findIndex((entry) => entry.id === swing.tempo_source) + 1}`,
                      swing.posture_source &&
                        `posture from Video ${entries.findIndex((entry) => entry.id === swing.posture_source) + 1}`,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                    .
                  </p>
                )}
                {swing.conflicts.map((conflict) => (
                  <p className="message message-warning" key={conflict}>
                    {conflict}
                  </p>
                ))}
              </article>
            ))}
          </div>
          {report.patterns.map((pattern) => (
            <p className="notice mt-3" key={pattern.code}>
              {pattern.code.replaceAll("_", " ")} was flagged in{" "}
              {pattern.swing_count} reviewed swing group(s):{" "}
              {pattern.swing_ids.join(", ")}.
            </p>
          ))}
          <div className="mt-5">
            <AiCoachingPrompt prompt={report.prompt_payload} />
          </div>
          <details className="analysis-notices mt-4">
            <summary>Session evidence notes</summary>
            <ul>
              {report.notices.map((notice) => (
                <li key={notice}>{notice}</li>
              ))}
            </ul>
          </details>
        </section>
      )}
      {active?.analysis && (
        <>
          <CaptureQualityPanel
            quality={active.analysis.kinematics.quality}
            eventSource={active.analysis.kinematics.event_source}
          />
          <MetricCards data={active.analysis.kinematics} />
          <div className="analysis-grid">
            <KinematicsPanel
              data={active.analysis.kinematics}
              playhead={playhead}
            />
            <CoachingFeedback result={active.analysis} />
          </div>
        </>
      )}
    </div>
  );
}
