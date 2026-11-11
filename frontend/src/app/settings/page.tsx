"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import { useApiKey } from "@/state/ApiKeyContext";

export default function SettingsPage() {
  const context = useApiKey();
  const [key, setKey] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [visible, setVisible] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (context.hydrated) {
      setKey(context.apiKey);
      setEnabled(context.llmEnabled);
    }
  }, [context.hydrated, context.apiKey, context.llmEnabled]);
  const save = (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setMessage(null);
    const result = context.saveSettings(key, enabled);
    if (!result.ok) setError(result.message || "Check your settings.");
    else setMessage("Your coaching preferences are updated.");
  };
  const forget = () => {
    context.clearApiKey();
    setKey("");
    setEnabled(false);
    setVisible(false);
    setError(null);
    setMessage("Key cleared and AI coaching switched off.");
  };
  return (
    <div className="settings-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">MAKE IT YOURS</p>
          <h1>Coaching, on your terms.</h1>
          <p className="page-description">
            Choose how you want to reflect on your swing.
          </p>
        </div>
        <Link href="/" className="button button-secondary">
          Back to Swing Lab
          <Icon name="arrow" />
        </Link>
      </div>
      <div className="settings-grid">
        <form onSubmit={save} className="panel settings-card">
          <div className="section-heading">
            <span className="section-icon">
              <Icon name="spark" />
            </span>
            <div>
              <h2>AI coaching</h2>
              <p>Turn your swing observations into a focused practice plan.</p>
            </div>
          </div>
          <div className="toggle-row">
            <div>
              <label htmlFor="llm-toggle" className="font-semibold text-sm">
                Enable coaching synthesis
              </label>
              <p className="help-text">
                Uses your OpenAI key when you analyze a swing.
              </p>
            </div>
            <button
              id="llm-toggle"
              type="button"
              role="switch"
              aria-checked={enabled}
              className={`toggle ${enabled ? "on" : ""}`}
              disabled={!context.hydrated}
              onClick={() => {
                setEnabled(!enabled);
                setMessage(null);
              }}
            >
              <span />
            </button>
          </div>
          <label htmlFor="api-key" className="field-label">
            OpenAI API key
          </label>
          <div className="key-input-wrap">
            <Icon name="lock" />
            <input
              id="api-key"
              name="openai-key"
              type={visible ? "text" : "password"}
              value={key}
              onChange={(event) => {
                setKey(event.target.value);
                setMessage(null);
              }}
              disabled={!context.hydrated}
              placeholder="Enter your API key"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              maxLength={1024}
              aria-describedby="key-help"
              className="field"
            />
            <button
              type="button"
              className="icon-button"
              aria-label={visible ? "Hide API key" : "Show API key"}
              aria-pressed={visible}
              onClick={() => setVisible(!visible)}
            >
              <Icon name="eye" />
            </button>
          </div>
          <p id="key-help" className="help-text mt-3">
            Saved in this browser’s local storage. Scripts on this site can read
            it; use a trusted, personal device. The key is sent only for an
            analysis with AI coaching enabled.
          </p>
          <div className="notice mt-6">
            <Icon name="info" />
            <p>
              AI coaching is optional. With it switched off, you still get pose
              analysis, swing metrics, rule-based observations, and drills.
            </p>
          </div>
          {context.storageMessage && (
            <p className="message message-warning" role="status">
              {context.storageMessage}
            </p>
          )}
          {error && (
            <p className="message message-error" role="alert">
              {error}
            </p>
          )}
          {message && (
            <p className="message message-success" role="status">
              <Icon name="check" />
              {message}
            </p>
          )}
          <div className="settings-actions">
            <button
              className="button button-primary"
              disabled={!context.hydrated}
              type="submit"
            >
              Save preferences
              <Icon name="check" />
            </button>
            <button
              type="button"
              onClick={forget}
              className="text-button"
              disabled={!context.hydrated || (!key && !context.apiKey)}
            >
              Forget saved key
            </button>
          </div>
        </form>
        <aside className="space-y-5">
          <section className="panel settings-summary">
            <p className="eyebrow">CURRENT PREFERENCES</p>
            <span
              className={`status-pill mt-4 ${context.llmEnabled ? "status-green" : ""}`}
            >
              <span className="status-dot" />
              {context.llmEnabled
                ? "AI coaching enabled"
                : "Rule-based coaching"}
            </span>
            <dl className="settings-facts">
              <div>
                <dt>API key</dt>
                <dd>
                  {!context.hydrated
                    ? "Loading…"
                    : context.apiKey
                      ? "Added"
                      : "Not added"}
                </dd>
              </div>
              <div>
                <dt>Saved on</dt>
                <dd>
                  {context.storageAvailable ? "This browser" : "This page only"}
                </dd>
              </div>
              <div>
                <dt>Analysis</dt>
                <dd>Always available</dd>
              </div>
            </dl>
          </section>
          <section className="settings-note">
            <Icon name="flag" />
            <h3>Keep the next step simple.</h3>
            <p>
              A good coaching plan starts with clear observations. Film from the
              same angle, make one adjustment, and compare your next swing.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
