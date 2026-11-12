"use client";
import { useCallback, useState } from "react";
import Link from "next/link";
import type { AnalysisResponse } from "@/lib/api-types";
import { CapturePanel } from "./capture/CapturePanel";
import { SwingVideoPlayer } from "./analysis/SwingVideoPlayer";
import { MetricCards, KinematicsPanel } from "./analysis/KinematicsPanel";
import { CoachingFeedback } from "./analysis/CoachingFeedback";
import { AiCoachingPrompt } from "./analysis/AiCoachingPrompt";
import { Icon } from "./ui/Icon";
import { CaptureQualityPanel } from "./analysis/CaptureQualityPanel";

export function SwingWorkspace() {
  const [subject, setSubject] = useState<[string, string]>(["", ""]);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [playhead, setPlayhead] = useState(0);
  const [duration, setDuration] = useState<number | undefined>();
  const [session, setSession] = useState(0);
  const select = useCallback((next: File) => {
    setFile(next);
    setSubject(["", ""]);
    setResult(null);
    setPlayhead(0);
    setDuration(undefined);
  }, []);
  const optionsChanged = useCallback(() => setResult(null), []);
  const activity = useCallback((value: boolean) => {
    setBusy(value);
    if (value) setResult(null);
  }, []);
  const reset = () => {
    setSession((value) => value + 1);
    setFile(null);
    setSubject(["", ""]);
    setResult(null);
    setBusy(false);
    setPlayhead(0);
    setDuration(undefined);
  };
  const download = () => {
    if (!result) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `golf-coach-${result.analysis_id}.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <div className="swing-workspace">
      <div className="page-heading">
        <div>
          <p className="eyebrow">THE SWING LAB</p>
          <h1>Your swing, in focus.</h1>
          <p className="page-description">
            See the movement. Understand the pattern. Make your next rep count.
          </p>
          <Link href="/sessions" className="text-button">
            Multiple views or a longer recording? Analyze a session →
          </Link>
        </div>
        <div className="heading-actions">
          {result && (
            <button
              type="button"
              className="button button-secondary"
              onClick={download}
            >
              <Icon name="download" />
              Save results
            </button>
          )}
          <button
            type="button"
            className="button button-secondary"
            onClick={reset}
            disabled={busy || !file}
          >
            <span aria-hidden="true">+</span>New swing
          </button>
        </div>
      </div>
      <div className="workspace-top">
        <CapturePanel
          key={session}
          file={file}
          playhead={playhead}
          duration={duration}
          onSelect={select}
          onResult={setResult}
          onBusyChange={activity}
          onOptionsChange={optionsChanged}
          subject={subject}
          onSubjectChange={setSubject}
        />
        <SwingVideoPlayer
          file={file}
          pose={result?.pose ?? null}
          onTime={setPlayhead}
          onDuration={setDuration}
          subjectPoint={
            subject.every(
              (value) => value.trim() !== "" && Number.isFinite(Number(value)),
            )
              ? [Number(subject[0]), Number(subject[1])]
              : undefined
          }
          onSubjectPoint={(point) => {
            setSubject([point[0].toFixed(5), point[1].toFixed(5)]);
            setResult(null);
          }}
          disabled={busy}
        />
      </div>
      {result && (
        <CaptureQualityPanel
          quality={result.kinematics.quality}
          eventSource={result.kinematics.event_source}
        />
      )}
      <MetricCards data={result?.kinematics ?? null} />
      {result ? (
        <>
          <div className="results-heading" role="status">
            <span className="status-dot" />
            Your swing analysis is ready
            <span>Review the measurements alongside your video.</span>
          </div>
          <div className="analysis-grid">
            <KinematicsPanel data={result.kinematics} playhead={playhead} />
            <div className="space-y-5 min-w-0">
              <AiCoachingPrompt prompt={result.prompt_payload} />
              <CoachingFeedback result={result} />
            </div>
          </div>
        </>
      ) : (
        <section className="practice-strip">
          <span className="section-icon">
            <Icon name="flag" width={24} height={24} />
          </span>
          <div>
            <p className="eyebrow">A LITTLE SETUP GOES A LONG WAY</p>
            <h3>One swing. One steady camera.</h3>
            <p>
              Film a single swing, keep your whole body visible, and choose the
              camera perspective that matches your clip.
            </p>
          </div>
          <span className="strip-number" aria-hidden="true">
            01
          </span>
        </section>
      )}
      <p className="workspace-note">
        <Icon name="info" width={15} />
        2D video gives perspective-dependent estimates. Use consistent filming
        conditions to make comparisons useful.
      </p>
    </div>
  );
}
