"use client";
import { useEffect, useRef, useState } from "react";
import type { SessionEntry } from "@/lib/session-client";
import {
  calibrationSchema,
  reconstructionSchema,
  evidenceRequest,
  type CameraCalibration,
  type EvidenceArtifact,
  type Reconstruction,
} from "@/lib/evidence-client";
import { ReconstructionViewer } from "./ReconstructionViewer";
import { BallTrackingPanel } from "./BallTrackingPanel";
import { MonitorImportPanel } from "./MonitorImportPanel";

export function EvidenceWorkbench({
  entries,
  disabled,
  onArtifacts,
}: {
  entries: SessionEntry[];
  disabled: boolean;
  onArtifacts: (values: EvidenceArtifact[]) => void;
}) {
  const available = entries.filter((entry) => entry.analysis?.pose);
  const revision = available
    .map(
      (entry) => `${entry.id}:${entry.analysis?.analysis_id}:${entry.swingId}`,
    )
    .join("|");
  const [a, setA] = useState(""),
    [b, setB] = useState(""),
    [profiles, setProfiles] = useState<(CameraCalibration | null)[]>([
      null,
      null,
    ]);
  const [anchors, setAnchors] = useState(["", ""]),
    [uncertainty, setUncertainty] = useState(""),
    [fixed, setFixed] = useState(false),
    [calibrated, setCalibrated] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [result, setResult] = useState<Reconstruction | null>(null);
  const [ballId, setBallId] = useState("");
  const artifacts = useRef<EvidenceArtifact[]>([]),
    controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    controller.current?.abort();
    setBusy(false);
    artifacts.current = [];
    setResult(null);
    setError("");
    setFixed(false);
    setCalibrated(false);
    setAnchors(["", ""]);
    setUncertainty("");
    onArtifacts([]);
  }, [revision, onArtifacts]);
  const first = available.find((entry) => entry.id === a) ?? available[0];
  const second = available.find((entry) => entry.id === b);
  const ball = available.find((entry) => entry.id === ballId) ?? first;
  const swingIds = Array.from(
    new Set(available.map((entry) => entry.swingId.trim())),
  );
  const save = (value: EvidenceArtifact) => {
    const ids =
      "shots" in value.result
        ? value.result.shots.map((shot) => shot.swing_id)
        : [value.result.swing_id];
    artifacts.current = [
      ...artifacts.current.filter((item) => {
        const previous =
          "shots" in item.result
            ? item.result.shots.map((shot) => shot.swing_id)
            : [item.result.swing_id];
        return (
          item.kind !== value.kind ||
          (!ids.some((id) => previous.includes(id)) &&
            value.kind !== "launch_monitor_import")
        );
      }),
      value,
    ];
    onArtifacts([...artifacts.current]);
  };
  const invalidate = (kind: EvidenceArtifact["kind"], swingId?: string) => {
    const next = artifacts.current.filter(
      (item) =>
        item.kind !== kind ||
        (swingId !== undefined &&
          "swing_id" in item.result &&
          item.result.swing_id !== swingId),
    );
    if (next.length !== artifacts.current.length) {
      artifacts.current = next;
      onArtifacts([...next]);
    }
  };
  const loadProfile = async (index: number, file: File | undefined) => {
    if (!file) return;
    setError("");
    setResult(null);
    setCalibrated(false);
    try {
      if (file.size > 32000)
        throw new Error("Choose a camera profile below 32 kB.");
      const profile = calibrationSchema.parse(JSON.parse(await file.text()));
      setProfiles((previous) =>
        previous.map((item, i) => (i === index ? profile : item)),
      );
    } catch {
      setProfiles((previous) =>
        previous.map((item, i) => (i === index ? null : item)),
      );
      setError(
        "This is not a valid camera calibration profile. Use the calibration guide.",
      );
    }
  };
  const run = async () => {
    if (busy || !first || !second) return;
    setError("");
    setResult(null);
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    try {
      if (
        first.id === second.id ||
        first.swingId.trim() !== second.swingId.trim()
      )
        throw new Error(
          "Choose two different views with the same physical Swing ID.",
        );
      if (!fixed || !calibrated || profiles.some((profile) => !profile))
        throw new Error(
          "Load both profiles and confirm the capture and shared-world calibration.",
        );
      const times = anchors.map((value) => Number(value));
      const precision = Number(uncertainty);
      if (
        anchors.some((value) => !value.trim()) ||
        times.some((value) => !Number.isFinite(value) || value < 0) ||
        !uncertainty.trim() ||
        !Number.isFinite(precision) ||
        precision < 0 ||
        precision > 10
      )
        throw new Error(
          "Enter both shared-event times and known synchronization uncertainty between 0 and 10 ms.",
        );
      const output = await evidenceRequest(
        "/reconstructions",
        {
          swing_id: first.swingId.trim(),
          same_swing_stationary_confirmed: fixed,
          physical_timebase_confirmed: fixed,
          sync_uncertainty_ms: precision,
          views: [first, second].map((entry, index) => ({
            calibration: {
              ...profiles[index],
              scale_and_orientation_verified: calibrated,
            },
            pose: entry.analysis!.pose,
            analysis_token: entry.analysis!.summary_token,
            sync_anchor_seconds: times[index],
          })),
        },
        reconstructionSchema,
        AbortSignal.any([abort.signal, AbortSignal.timeout(60000)]),
      );
      setResult(output);
      save({ kind: "calibrated_3d", result: output });
    } catch (cause) {
      if (!abort.signal.aborted)
        setError(
          cause instanceof Error ? cause.message : "Reconstruction failed.",
        );
    } finally {
      if (!abort.signal.aborted) setBusy(false);
    }
  };
  if (!available.length) return null;
  return (
    <section
      className="panel evidence-workbench"
      aria-labelledby="evidence-workbench-title"
    >
      <p className="eyebrow">MORE COMPLETE EVIDENCE</p>
      <h2 id="evidence-workbench-title">Movement. Launch. Result.</h2>
      <p>
        Start with visible-ball tracking for single-camera swings. Calibrated
        two-camera capture and imported shot readings are optional. Refresh the
        session report afterward to include this evidence in the combined
        coaching prompt.
      </p>
      <fieldset disabled={disabled}>
        <details key="ball" className="evidence-disclosure">
          <summary>Visible-ball candidate tracking</summary>
          <div className="evidence-section">
            <label>
              Ball source video
              <select
                className="field"
                aria-label="Ball source video"
                value={ball?.id ?? ""}
                onChange={(event) => setBallId(event.target.value)}
              >
                {available.map((entry) => (
                  <option value={entry.id} key={entry.id}>
                    {entry.swingId} · {entry.file.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {ball && (
            <BallTrackingPanel
              key={`${ball.id}:${revision}`}
              entry={ball}
              onResult={save}
              onInvalidate={() =>
                invalidate("ball_candidate_track", ball.swingId.trim())
              }
            />
          )}
        </details>
        <details key="calibration" className="evidence-disclosure">
          <summary>Calibrated 3D reconstruction</summary>
          <div className="evidence-section">
            <p>
              Use two stationary cameras recording the exact same swing.
              Calibrate the lens at the same focus/zoom, resolution and
              orientation, then place both cameras in one measured world
              reference. Separate swings cannot be reconstructed together.
            </p>
            <p className="help-text">
              <a
                href="/capture-guide"
                target="_blank"
                rel="noopener noreferrer"
                className="text-button"
              >
                Read the camera and ball-capture guide
              </a>
              . A matching calibration and verified shared timing signal are
              required.
            </p>
            <fieldset
              disabled={busy}
              onChange={() => {
                setResult(null);
                invalidate("calibrated_3d", first?.swingId.trim());
              }}
            >
              <div className="session-fields">
                <label>
                  Camera A video
                  <select
                    className="field"
                    aria-label="Reconstruction camera A video"
                    value={first?.id ?? ""}
                    onChange={(event) => {
                      setA(event.target.value);
                      setProfiles((previous) => [null, previous[1]]);
                      setAnchors(["", ""]);
                      setCalibrated(false);
                      setFixed(false);
                      setResult(null);
                    }}
                  >
                    {available.map((entry) => (
                      <option value={entry.id} key={entry.id}>
                        Video{" "}
                        {entries.findIndex((item) => item.id === entry.id) + 1}{" "}
                        · {entry.swingId} · {entry.file.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Camera B video
                  <select
                    className="field"
                    aria-label="Reconstruction camera B video"
                    value={b}
                    onChange={(event) => {
                      setB(event.target.value);
                      setProfiles((previous) => [previous[0], null]);
                      setAnchors(["", ""]);
                      setCalibrated(false);
                      setFixed(false);
                      setResult(null);
                    }}
                  >
                    <option value="">Choose another view</option>
                    {available
                      .filter((entry) => entry.id !== first?.id)
                      .map((entry) => (
                        <option value={entry.id} key={entry.id}>
                          {entry.swingId} · {entry.file.name}
                        </option>
                      ))}
                  </select>
                </label>
                {[0, 1].map((index) => (
                  <label key={index} className="evidence-file">
                    Camera {index === 0 ? "A" : "B"} calibration JSON
                    <input
                      aria-label={`Camera ${index === 0 ? "A" : "B"} calibration file`}
                      type="file"
                      accept=".json"
                      onChange={(event) =>
                        loadProfile(index, event.target.files?.[0])
                      }
                    />
                    {profiles[index] && (
                      <small>
                        {profiles[index]!.camera_id} ·{" "}
                        {profiles[index]!.image_width}×
                        {profiles[index]!.image_height} · RMS{" "}
                        {profiles[index]!.calibration_rms_px.toFixed(2)} px
                      </small>
                    )}
                  </label>
                ))}
                {[0, 1].map((index) => (
                  <label key={index}>
                    Shared flash/trigger time in {index === 0 ? "A" : "B"}{" "}
                    (seconds into window)
                    <input
                      aria-label={`Camera ${index === 0 ? "A" : "B"} sync anchor`}
                      className="field"
                      type="number"
                      min="0"
                      max="30"
                      step="any"
                      value={anchors[index]}
                      onChange={(event) =>
                        setAnchors((previous) =>
                          previous.map((value, i) =>
                            i === index ? event.target.value : value,
                          ),
                        )
                      }
                    />
                  </label>
                ))}
                <label>
                  Known sync uncertainty (ms, ≤10)
                  <input
                    className="field"
                    aria-label="Synchronization uncertainty in milliseconds"
                    type="number"
                    min="0"
                    max="10"
                    step="any"
                    value={uncertainty}
                    onChange={(event) => setUncertainty(event.target.value)}
                  />
                </label>
              </div>
              <label className="confirmation-row">
                <input
                  type="checkbox"
                  checked={fixed}
                  onChange={(event) => setFixed(event.target.checked)}
                />
                These are the same physical swing, both cameras stayed fixed,
                and both videos preserve original physical timing.
              </label>
              <label className="confirmation-row">
                <input
                  type="checkbox"
                  checked={calibrated}
                  onChange={(event) => setCalibrated(event.target.checked)}
                />
                I verified measured square size, identical physical reference
                corners, a level ground board, and X-right / Y-up / Z-target
                axes in both profiles.
              </label>
              <p className="help-text">
                Matching impact frames alone does not prove synchronization
                within 10 ms. Use a shared timing signal or a verified hardware
                trigger. Independently filtered/interpolated joints are
                excluded.
              </p>
              <button
                className="button button-primary"
                disabled={!second || !fixed || !calibrated || busy}
                onClick={run}
              >
                {busy
                  ? "Reconstructing supported joints…"
                  : "Reconstruct in 3D"}
              </button>
            </fieldset>
            {error && (
              <p className="message message-error" role="alert">
                {error}
              </p>
            )}
            {result && (
              <ReconstructionViewer
                key={result.evidence_token}
                result={result}
              />
            )}
          </div>
        </details>
        <details key="monitor" className="evidence-disclosure">
          <summary>Launch monitor / shot-intent analysis</summary>
          <MonitorImportPanel
            key={revision}
            swingIds={swingIds}
            onResult={save}
            onInvalidate={() => invalidate("launch_monitor_import")}
          />
        </details>
      </fieldset>
      {artifacts.current.length > 0 && (
        <p className="message message-success" role="status">
          {artifacts.current.length} evidence report(s) attached. Build /
          refresh the session report to combine them. Source reports are
          included when you save the session.
        </p>
      )}
    </section>
  );
}
