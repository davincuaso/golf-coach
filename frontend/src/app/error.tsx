"use client";
import { Icon } from "@/components/ui/Icon";
export default function ErrorPage({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="panel error-panel">
      <Icon name="info" width={32} height={32} />
      <h1>Let’s try that again.</h1>
      <p>
        The workspace could not finish loading. Your saved coaching settings are
        still in this browser.
      </p>
      <button className="button button-primary" onClick={reset}>
        Reload workspace
      </button>
    </div>
  );
}
