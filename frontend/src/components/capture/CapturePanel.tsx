"use client";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { VideoUpload } from "./VideoUpload";
import { VideoRecorder } from "./VideoRecorder";
import { Icon } from "@/components/ui/Icon";
import { parseSwingMarkers, validateVideo } from "@/lib/capture";
import { uploadAnalysis, type UploadProgress } from "@/lib/analysis-client";
import type {
  AnalysisOptions,
  AnalysisResponse,
  CameraView,
} from "@/lib/api-types";

interface Props {
  file: File | null;
  playhead: number;
  duration: number | undefined;
  onSelect: (file: File) => void;
  onResult: (result: AnalysisResponse) => void;
  onBusyChange: (busy: boolean) => void;
}
export function CapturePanel({
  file,
  playhead,
  duration,
  onSelect,
  onResult,
  onBusyChange,
}: Props) {
  const [mode, setMode] = useState<"upload" | "record">("upload");
  const [cameraView, setCameraView] = useState<CameraView>("unknown");
  const [markers, setMarkers] = useState<[string, string, string]>([
    "",
    "",
    "",
  ]);
  const [subject, setSubject] = useState<[string, string]>(["", ""]);
  const [constantRate, setConstantRate] = useState(false);
  const [recording, setRecording] = useState(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const busy = progress !== null;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (!busy) return;
    const started = performance.now();
    const timer = setInterval(
      () => setElapsed(Math.floor((performance.now() - started) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, [busy]);
  const select = useCallback(
    (next: File) => {
      setError(null);
      setMarkers(["", "", ""]);
      onSelect(next);
    },
    [onSelect],
  );
  const analyze = async (event: FormEvent) => {
    event.preventDefault();
    if (!file || busy || recording) return;
    setError(null);
    let options: AnalysisOptions;
    try {
      const fileError = validateVideo(file);
      if (fileError) throw new Error(fileError);
      const events = parseSwingMarkers(markers, duration);
      let point: [number, number] | undefined;
      if (subject.some((value) => value.trim() !== "")) {
        if (
          subject.some(
            (value) =>
              value.trim() === "" ||
              !Number.isFinite(Number(value)) ||
              Number(value) < 0 ||
              Number(value) > 1,
          )
        )
          throw new Error("Choose both subject coordinates between 0 and 1.");
        point = [Number(subject[0]), Number(subject[1])];
      }
      options = {
        camera_view: cameraView,
        events,
        estimate_events: !events,
        confirm_constant_frame_rate: constantRate,
        subject_point: point,
        include_pose: true,
      };
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Check the swing options.",
      );
      return;
    }
    const next = new AbortController();
    controller.current = next;
    setElapsed(0);
    setProgress({ phase: "uploading", percent: 0 });
    onBusyChange(true);
    try {
      const result = await uploadAnalysis(
        file,
        options,
        next.signal,
        (value) => {
          if (mounted.current) setProgress(value);
        },
      );
      if (mounted.current) onResult(result);
    } catch (cause) {
      if (mounted.current)
        setError(
          cause instanceof DOMException && cause.name === "AbortError"
            ? "Analysis canceled. You can try again when ready."
            : cause instanceof Error
              ? cause.message
              : "Analysis could not be completed.",
        );
    } finally {
      if (mounted.current) {
        controller.current = null;
        setProgress(null);
        onBusyChange(false);
      }
    }
  };
  return (
    <section className="panel capture-panel" aria-labelledby="capture-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">01 / YOUR SWING</p>
          <h2 id="capture-title">Start with a clear view.</h2>
        </div>
        <span className="section-icon">
          <Icon name="upload" />
        </span>
      </div>
      <div className="capture-tabs" role="group" aria-label="Video source">
        <button
          type="button"
          aria-pressed={mode === "upload"}
          className={mode === "upload" ? "selected" : ""}
          disabled={busy || recording}
          onClick={() => setMode("upload")}
        >
          <Icon name="upload" width={16} />
          Upload video
        </button>
        <button
          type="button"
          aria-pressed={mode === "record"}
          className={mode === "record" ? "selected" : ""}
          disabled={busy || recording}
          onClick={() => setMode("record")}
        >
          <Icon name="camera" width={16} />
          Record swing
        </button>
      </div>
      {mode === "upload" ? (
        <VideoUpload disabled={busy} onSelect={select} />
      ) : (
        <VideoRecorder
          disabled={busy}
          onSelect={select}
          onRecordingChange={setRecording}
        />
      )}
      {file && (
        <div className="selected-file">
          <span className="file-check">
            <Icon name="check" width={15} />
          </span>
          <div>
            <strong title={file.name}>{file.name}</strong>
            <span>
              {(file.size / 1048576).toFixed(1)} MB · Ready for review
            </span>
          </div>
        </div>
      )}
      <form onSubmit={analyze} className="capture-options">
        <label htmlFor="camera-view" className="field-label">
          Camera perspective
        </label>
        <select
          id="camera-view"
          className="field"
          value={cameraView}
          disabled={busy || recording}
          onChange={(event) => setCameraView(event.target.value as CameraView)}
        >
          <option value="unknown">Not sure yet</option>
          <option value="down_the_line">
            Down the line (behind the golfer)
          </option>
          <option value="face_on">Face on (facing the golfer)</option>
        </select>
        <p className="help-text mt-2">
          Posture comparisons need a fixed, down-the-line view.
        </p>
        <details className="advanced-options">
          <summary>
            Fine-tune this analysis<span aria-hidden="true">+</span>
          </summary>
          <fieldset disabled={busy || recording}>
            <legend className="field-label">
              Swing markers{" "}
              <span className="font-normal">(optional, seconds)</span>
            </legend>
            <p className="help-text mb-3">
              Scrub the video to each moment and use its current time. Leave all
              blank to estimate.
            </p>
            <div className="marker-inputs">
              {["Start", "Top", "Impact"].map((label, index) => (
                <div key={label}>
                  <label htmlFor={`marker-${index}`}>{label}</label>
                  <input
                    id={`marker-${index}`}
                    className="field"
                    type="number"
                    min="0"
                    step="any"
                    value={markers[index]}
                    placeholder="—"
                    onChange={(event) =>
                      setMarkers((previous) => {
                        const next = [...previous] as [string, string, string];
                        next[index] = event.target.value;
                        return next;
                      })
                    }
                  />
                  <button
                    className="text-button"
                    type="button"
                    disabled={!file}
                    aria-label={`Use video time for ${label.toLowerCase()}`}
                    onClick={() =>
                      setMarkers((previous) => {
                        const next = [...previous] as [string, string, string];
                        next[index] = playhead.toFixed(3);
                        return next;
                      })
                    }
                  >
                    Use time
                  </button>
                </div>
              ))}
            </div>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={constantRate}
                onChange={(event) => setConstantRate(event.target.checked)}
              />
              I know this video has a constant frame rate.
            </label>
            <p className="help-text">
              Confirm only if known. This permits tempo estimates when decoded
              timestamps are unavailable.
            </p>
            <p className="field-label mt-4">
              Multiple golfers? <span className="font-normal">(optional)</span>
            </p>
            <p className="help-text mb-3">
              Choose a point inside your body in the first frame: x from left, y
              from top, each 0–1.
            </p>
            <div className="subject-inputs">
              {["x", "y"].map((axis, index) => (
                <label key={axis}>
                  {axis}
                  <input
                    className="field"
                    aria-label={`Subject ${axis} coordinate`}
                    type="number"
                    min="0"
                    max="1"
                    step="any"
                    placeholder="0.50"
                    value={subject[index]}
                    onChange={(event) =>
                      setSubject((previous) => {
                        const next = [...previous] as [string, string];
                        next[index] = event.target.value;
                        return next;
                      })
                    }
                  />
                </label>
              ))}
            </div>
          </fieldset>
        </details>
        <div className="coaching-mode">
          <Icon name="spark" width={17} />
          <span>Includes a prompt for your ChatGPT conversation</span>
        </div>
        <button
          className="button button-primary analyze-button"
          type="submit"
          disabled={!file || busy || recording}
        >
          {busy ? (
            <>
              <span className="spinner" />
              {progress.phase === "uploading"
                ? "Uploading swing…"
                : "Reading your swing…"}
            </>
          ) : (
            <>
              Analyze my swing
              <Icon name="arrow" />
            </>
          )}
        </button>
      </form>
      {progress && (
        <div className="analysis-progress" role="status" aria-live="polite">
          <div className="flex items-center justify-between gap-3">
            <span>
              {progress.phase === "uploading"
                ? `Uploading${progress.percent !== undefined ? ` · ${progress.percent}%` : ""}`
                : `Analysis in progress · ${elapsed}s`}
            </span>
            <button
              type="button"
              className="text-button"
              onClick={() => controller.current?.abort()}
            >
              Cancel
            </button>
          </div>
          {progress.phase === "uploading" && progress.percent !== undefined && (
            <progress
              value={progress.percent}
              max={100}
              aria-label="Video upload progress"
            />
          )}
          <p className="help-text">
            Processing can take a few minutes. Keep this page open.
          </p>
        </div>
      )}
      {error && (
        <p className="message message-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
