"use client";
import { useEffect, useRef, useState } from "react";
import {
  downloadJson,
  evidenceRequest,
  monitorTemplate,
  shotImportSchema,
  type EvidenceArtifact,
  type ShotImport,
} from "@/lib/evidence-client";
const metrics = [
  ["ball_speed", "Ball speed"],
  ["launch_angle", "Launch angle"],
  ["launch_direction", "Launch direction"],
  ["spin_rate", "Spin rate"],
  ["spin_axis", "Spin axis"],
  ["carry", "Carry"],
  ["offline", "Offline"],
  ["apex", "Apex"],
  ["total_distance", "Total distance"],
] as const;
export function MonitorImportPanel({
  swingIds,
  onResult,
  onInvalidate,
}: {
  swingIds: string[];
  onResult: (value: EvidenceArtifact) => void;
  onInvalidate: () => void;
}) {
  const [mode, setMode] = useState("file"),
    [content, setContent] = useState(""),
    [format, setFormat] = useState<"csv" | "json">("csv"),
    [device, setDevice] = useState("");
  const [direction, setDirection] = useState("right"),
    [spinDirection, setSpinDirection] = useState("unknown"),
    [conditions, setConditions] = useState("unknown");
  const [carryMin, setCarryMin] = useState(""),
    [carryMax, setCarryMax] = useState(""),
    [launchMin, setLaunchMin] = useState("-3"),
    [launchMax, setLaunchMax] = useState("3"),
    [corridor, setCorridor] = useState("15"),
    [shape, setShape] = useState("unspecified"),
    [hand, setHand] = useState("right");
  const [manualSwing, setManualSwing] = useState(swingIds[0] ?? ""),
    [manual, setManual] = useState<Record<string, string>>({}),
    [speedUnit, setSpeedUnit] = useState("mph"),
    [distanceUnit, setDistanceUnit] = useState("yd");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [result, setResult] = useState<ShotImport | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const run = async () => {
    if (busy) return;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setError("");
    try {
      if (!device.trim())
        throw new Error("Name the device or enter “Manual readings”.");
      const numeric = (value: string) => {
        if (!value.trim() || !Number.isFinite(Number(value)))
          throw new Error("Enter finite numbers for the chosen intent ranges.");
        return Number(value);
      };
      const row: Record<string, string> = {
        shot_id: "manual-shot",
        swing_id: manualSwing,
      };
      for (const [name] of metrics)
        if (manual[name]?.trim()) {
          row[name] = manual[name];
          row[name + "_unit"] =
            name === "ball_speed"
              ? speedUnit
              : ["carry", "offline", "apex", "total_distance"].includes(name)
                ? distanceUnit
                : name === "spin_rate"
                  ? "rpm"
                  : "deg";
          row[name + "_method"] = "manual";
        }
      const output = await evidenceRequest(
        "/shot-imports",
        {
          format: mode === "manual" ? "json" : format,
          content: mode === "manual" ? JSON.stringify([row]) : content,
          device: device.trim(),
          positive_direction: direction,
          positive_spin_axis_curve: spinDirection,
          conditions,
          intent: {
            carry_min_m: carryMin.trim() ? numeric(carryMin) : null,
            carry_max_m: carryMax.trim() ? numeric(carryMax) : null,
            launch_direction_min_deg: numeric(launchMin),
            launch_direction_max_deg: numeric(launchMax),
            offline_tolerance_m: numeric(corridor),
            desired_shape: shape,
            handedness: hand,
            straight_spin_axis_tolerance_deg: 5,
          },
        },
        shotImportSchema,
        AbortSignal.any([abort.signal, AbortSignal.timeout(60000)]),
      );
      if (output.shots.some((shot) => !swingIds.includes(shot.swing_id)))
        throw new Error(
          "Match every imported swing_id to an analyzed swing in this session.",
        );
      setResult(output);
      onResult({ kind: "launch_monitor_import", result: output });
    } catch (cause) {
      if (!abort.signal.aborted)
        setError(cause instanceof Error ? cause.message : "Import failed.");
    } finally {
      if (!abort.signal.aborted) setBusy(false);
    }
  };
  const templateCsv = () => {
    const row = monitorTemplate[0];
    const csv =
      Object.keys(row).join(",") + "\n" + Object.values(row).join(",") + "\n";
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "golf-monitor-template.csv";
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <div className="evidence-section">
      <p>
        Import one monitor shot per physical Swing ID, or enter readings
        yourself. Map vendor columns to the template, including each value’s
        unit and method: measured, device_calculated, manual, or unknown. Empty
        values stay unknown.
      </p>
      <div className="session-toolbar">
        <button className="text-button" onClick={templateCsv}>
          Download CSV template
        </button>
        <button
          className="text-button"
          onClick={() =>
            downloadJson("golf-monitor-template.json", monitorTemplate)
          }
        >
          Download JSON template
        </button>
      </div>
      <fieldset
        disabled={busy}
        onChange={() => {
          setResult(null);
          onInvalidate();
        }}
      >
        <div className="session-fields">
          <label>
            Input
            <select
              className="field"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
            >
              <option value="file">CSV / JSON file</option>
              <option value="manual">Enter one shot</option>
            </select>
          </label>
          <label>
            Device / source
            <input
              className="field"
              aria-label="Monitor device or source"
              value={device}
              maxLength={80}
              onChange={(e) => setDevice(e.target.value)}
              placeholder="Device name or Manual readings"
            />
          </label>
          <label>
            Positive launch/offline means
            <select
              className="field"
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
            >
              <option value="right">Right of target</option>
              <option value="left">Left of target</option>
            </select>
          </label>
          <label>
            Positive spin axis curves
            <select
              className="field"
              value={spinDirection}
              onChange={(e) => setSpinDirection(e.target.value)}
            >
              <option value="unknown">Not verified — withhold shape</option>
              <option value="right">Rightward</option>
              <option value="left">Leftward</option>
            </select>
          </label>
          <label>
            Reading conditions
            <select
              className="field"
              value={conditions}
              onChange={(e) => setConditions(e.target.value)}
            >
              <option value="unknown">Not recorded</option>
              <option value="outdoor">Outdoor</option>
              <option value="indoor">Indoor / modelled flight</option>
              <option value="normalized">Normalized by device</option>
            </select>
          </label>
        </div>
        {mode === "file" ? (
          <label className="evidence-file">
            Monitor data file (up to 500 kB)
            <input
              type="file"
              aria-label="Launch monitor data file"
              accept=".csv,.json"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                if (file.size > 500000) {
                  setError("Choose a data file below 500 kB.");
                  return;
                }
                setFormat(
                  file.name.toLowerCase().endsWith(".json") ? "json" : "csv",
                );
                setContent(await file.text());
                setError("");
              }}
            />
            {content && (
              <span className="help-text">
                File loaded. Match swing_id values to: {swingIds.join(", ")}.
              </span>
            )}
          </label>
        ) : (
          <>
            <div className="session-fields">
              <label>
                Match shot to Swing ID
                <select
                  aria-label="Manual shot Swing ID"
                  className="field"
                  value={manualSwing}
                  onChange={(e) => setManualSwing(e.target.value)}
                >
                  {swingIds.map((id) => (
                    <option key={id}>{id}</option>
                  ))}
                </select>
              </label>
              <label>
                Speed unit
                <select
                  className="field"
                  value={speedUnit}
                  onChange={(e) => setSpeedUnit(e.target.value)}
                >
                  <option>mph</option>
                  <option>m/s</option>
                  <option>km/h</option>
                </select>
              </label>
              <label>
                Distance unit
                <select
                  className="field"
                  value={distanceUnit}
                  onChange={(e) => setDistanceUnit(e.target.value)}
                >
                  <option>yd</option>
                  <option>m</option>
                  <option>ft</option>
                </select>
              </label>
            </div>
            <div className="session-fields">
              {metrics.map(([name, label]) => (
                <label key={name}>
                  {label}
                  {name.includes("angle") ||
                  name.includes("direction") ||
                  name === "spin_axis"
                    ? " (degrees)"
                    : name === "spin_rate"
                      ? " (rpm)"
                      : ""}
                  <input
                    className="field"
                    type="number"
                    step="any"
                    aria-label={`Manual ${label.toLowerCase()}`}
                    value={manual[name] ?? ""}
                    onChange={(e) =>
                      setManual({ ...manual, [name]: e.target.value })
                    }
                  />
                </label>
              ))}
            </div>
            <p className="help-text">
              All entered values are labelled manual. Leave unavailable readings
              blank.
            </p>
          </>
        )}
        <h3 className="mt-5">What shot did you intend?</h3>
        <div className="session-fields">
          <label>
            Carry minimum (metres, optional)
            <input
              className="field"
              type="number"
              aria-label="Intended carry minimum"
              value={carryMin}
              onChange={(e) => setCarryMin(e.target.value)}
              min="0"
              max="500"
            />
          </label>
          <label>
            Carry maximum (metres, optional)
            <input
              className="field"
              type="number"
              aria-label="Intended carry maximum"
              value={carryMax}
              onChange={(e) => setCarryMax(e.target.value)}
              min="0"
              max="500"
            />
          </label>
          <label>
            Launch direction minimum (°)
            <input
              className="field"
              type="number"
              step="any"
              value={launchMin}
              onChange={(e) => setLaunchMin(e.target.value)}
            />
          </label>
          <label>
            Launch direction maximum (°)
            <input
              className="field"
              type="number"
              step="any"
              value={launchMax}
              onChange={(e) => setLaunchMax(e.target.value)}
            />
          </label>
          <label>
            Landing corridor ±metres
            <input
              className="field"
              type="number"
              step="any"
              value={corridor}
              onChange={(e) => setCorridor(e.target.value)}
              min="0"
              max="200"
            />
          </label>
          <label>
            Desired shape
            <select
              className="field"
              value={shape}
              onChange={(e) => setShape(e.target.value)}
            >
              <option value="unspecified">Not specified</option>
              <option value="straight">Straight</option>
              <option value="draw">Draw</option>
              <option value="fade">Fade</option>
            </select>
          </label>
          <label>
            Handedness
            <select
              className="field"
              value={hand}
              onChange={(e) => setHand(e.target.value)}
            >
              <option value="right">Right handed</option>
              <option value="left">Left handed</option>
            </select>
          </label>
        </div>
        <p className="help-text">
          Positive/right and negative/left are relative to your target,
          regardless of handedness. Intent ranges are your practice choices.
          Shape uses a 5° straight-spin-axis tolerance and stays a tendency, not
          an observed flight.
        </p>
        <button
          className="button button-primary mt-4"
          disabled={busy || (mode === "file" && !content)}
          onClick={run}
        >
          {busy ? "Checking shot evidence…" : "Analyze shot readings"}
        </button>
      </fieldset>
      {error && (
        <p className="message message-error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="evidence-result">
          <h3>Shot results · {result.device}</h3>
          <svg
            viewBox="0 0 600 280"
            className="shot-dispersion"
            role="img"
            aria-label="Imported landing dispersion, not a trajectory"
          >
            <title>
              Carry and offline readings, in metres. No flight path is
              simulated.
            </title>
            <path d="M300 30V240M40 240H560" stroke="#afbcae" />
            <text x="12" y="20" fill="#526451" fontSize="13">
              Carry ↑ · Offline: left ← | → right (m)
            </text>
            {result.shots.map((shot) => {
              const carry = shot.metrics.carry,
                offline = shot.metrics.offline;
              if (!carry || !offline) return null;
              const x = 300 + (offline.value / 200) * 250,
                y = 240 - (carry.value / 500) * 200;
              return (
                <g key={shot.shot_id}>
                  <circle cx={x} cy={y} r={6} fill="#32634c" />
                  <text x={x + 8} y={y} fontSize="12">
                    {shot.swing_id}
                  </text>
                </g>
              );
            })}
            <text x="285" y="260" fontSize="12">
              Target line
            </text>
          </svg>
          {result.shots.map((shot) => (
            <article className="shot-result" key={shot.shot_id}>
              <h4>
                {shot.swing_id} · {shot.shot_id}
              </h4>
              <dl className="angle-readout">
                {Object.entries(shot.metrics).map(([name, value]) => (
                  <div key={name}>
                    <dt>{name.replaceAll("_", " ")}</dt>
                    <dd>
                      {value.value.toFixed(2)} {value.unit}
                      <small>
                        {value.method.replaceAll("_", " ")} · originally{" "}
                        {value.original_value} {value.original_unit}
                      </small>
                    </dd>
                  </div>
                ))}
              </dl>
              <ul className="shot-checks">
                {shot.checks.map((check) => (
                  <li
                    key={check.metric}
                    className={
                      check.status === "outside_intent" ? "message-warning" : ""
                    }
                  >
                    <strong>
                      {check.metric.replaceAll("_", " ")} ·{" "}
                      {check.status.replaceAll("_", " ")}
                    </strong>
                    <span>{check.explanation}</span>
                  </li>
                ))}
              </ul>
            </article>
          ))}
          <ul className="evidence-notes">
            {result.notices.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
