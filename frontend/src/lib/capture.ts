import type { SwingEvents } from "./api-types";
export const MAX_VIDEO_BYTES = 100 * 1024 * 1024;
export const MAX_RECORDING_SECONDS = 30;
export const VIDEO_ACCEPT =
  ".mp4,.mov,.webm,.avi,.m4v,video/mp4,video/quicktime,video/webm,video/x-msvideo";
export function validateVideo(
  file: Pick<File, "name" | "size">,
): string | null {
  if (!/\.(mp4|mov|webm|avi|m4v)$/i.test(file.name))
    return "Choose an MP4, MOV, WebM, AVI, or M4V video.";
  if (file.size === 0) return "That file is empty. Choose another video.";
  if (file.size > MAX_VIDEO_BYTES) return "Choose a video smaller than 100 MB.";
  return null;
}
export function parseSwingMarkers(
  values: [string, string, string],
  duration?: number,
): SwingEvents | undefined {
  if (values.every((value) => value.trim() === "")) return undefined;
  if (values.some((value) => value.trim() === ""))
    throw new Error("Add all three swing markers, or leave all three blank.");
  const [start, top, impact] = values.map(Number);
  if (
    ![start, top, impact].every(Number.isFinite) ||
    start < 0 ||
    start >= top ||
    top >= impact
  )
    throw new Error("Swing markers must follow start < top < impact.");
  if (duration !== undefined && impact > duration)
    throw new Error("Keep your swing markers inside the video’s duration.");
  return { start_seconds: start, top_seconds: top, impact_seconds: impact };
}
export function bestRecordingMime(
  recorder: Pick<typeof MediaRecorder, "isTypeSupported">,
): string | undefined {
  return [
    "video/webm;codecs=vp9",
    "video/webm;codecs=vp8",
    "video/mp4",
    "video/webm",
  ].find((mime) => recorder.isTypeSupported(mime));
}
