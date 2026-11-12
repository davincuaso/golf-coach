"use client";
import { useId, useRef, useState } from "react";
import { validateVideo, VIDEO_ACCEPT } from "@/lib/capture";
import { Icon } from "@/components/ui/Icon";

export function VideoUpload({
  disabled,
  onSelect,
}: {
  disabled: boolean;
  onSelect: (file: File) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const id = useId();
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const select = (files: FileList | null) => {
    if (disabled || !files?.length) return;
    if (files.length !== 1) {
      setError("Choose one swing video at a time.");
      return;
    }
    const issue = validateVideo(files[0]);
    setError(issue);
    if (!issue) onSelect(files[0]);
  };
  return (
    <div>
      <input
        ref={input}
        id={id}
        type="file"
        accept={VIDEO_ACCEPT}
        disabled={disabled}
        className="sr-only"
        onChange={(event) => {
          select(event.currentTarget.files);
          event.currentTarget.value = "";
        }}
      />
      <button
        type="button"
        className={`upload-zone ${dragging ? "dragging" : ""}`}
        disabled={disabled}
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          select(event.dataTransfer.files);
        }}
      >
        <span className="upload-icon">
          <Icon name="upload" width={24} height={24} />
        </span>
        <strong>Drop your swing here</strong>
        <span>
          or{" "}
          <span className="text-[var(--green)] underline underline-offset-4">
            browse files
          </span>
        </span>
        <small>MP4, MOV, WebM · Up to 30 sec / 250 MB</small>
      </button>
      {error && (
        <p className="message message-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
