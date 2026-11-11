import {
  analysisResponseSchema,
  type AnalysisOptions,
  type AnalysisResponse,
} from "./api-types.ts";

export interface UploadProgress {
  phase: "uploading" | "analyzing";
  percent?: number;
}
export function uploadAnalysis(
  file: File,
  options: AnalysisOptions,
  apiKey: string | undefined,
  signal: AbortSignal,
  onProgress: (value: UploadProgress) => void,
): Promise<AnalysisResponse> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Canceled", "AbortError"));
      return;
    }
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    const cleanup = () => signal.removeEventListener("abort", abort);
    xhr.open("POST", "/api/v1/analyses");
    xhr.timeout = 310000;
    xhr.setRequestHeader("Accept", "application/json");
    if (options.llm_enabled) {
      if (!apiKey) {
        reject(
          new Error(
            "Add your OpenAI key in coaching settings, or switch AI coaching off.",
          ),
        );
        return;
      }
      xhr.setRequestHeader("X-OpenAI-API-Key", apiKey);
    }
    xhr.upload.onprogress = (event) =>
      onProgress({
        phase: "uploading",
        percent: event.lengthComputable
          ? Math.min(100, Math.round((event.loaded / event.total) * 100))
          : undefined,
      });
    xhr.upload.onload = () => onProgress({ phase: "analyzing" });
    xhr.onerror = () => {
      cleanup();
      reject(
        new Error(
          "The connection was interrupted. Check your connection and try again.",
        ),
      );
    };
    xhr.ontimeout = () => {
      cleanup();
      reject(new Error("Analysis took too long. Try a shorter video."));
    };
    xhr.onabort = () => {
      cleanup();
      reject(new DOMException("Canceled", "AbortError"));
    };
    xhr.onload = () => {
      cleanup();
      try {
        const payload: unknown = JSON.parse(xhr.responseText);
        if (xhr.status !== 200) {
          const error =
            payload && typeof payload === "object" && "error" in payload
              ? payload.error
              : undefined;
          const message =
            error &&
            typeof error === "object" &&
            "message" in error &&
            typeof error.message === "string"
              ? error.message
              : "The swing could not be analyzed. Check your server connection and try again.";
          reject(new Error(message));
          return;
        }
        const parsed = analysisResponseSchema.safeParse(payload);
        if (!parsed.success) {
          reject(
            new Error("The analysis result was incomplete. Please try again."),
          );
          return;
        }
        resolve(parsed.data);
      } catch {
        reject(
          new Error(
            "The server returned an unreadable response. Please try again.",
          ),
        );
      }
    };
    signal.addEventListener("abort", abort, { once: true });
    const form = new FormData();
    form.append("video", file);
    form.append("options", JSON.stringify(options));
    onProgress({ phase: "uploading", percent: 0 });
    try {
      xhr.send(form);
    } catch {
      cleanup();
      reject(
        new Error(
          "The upload could not be started. Try selecting the video again.",
        ),
      );
    }
  });
}
