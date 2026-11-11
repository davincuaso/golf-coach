"use client";
import { useEffect, useId, useRef, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { copyCoachingPrompt } from "@/lib/clipboard";

export function AiCoachingPrompt({ prompt }: { prompt: string }) {
  const id = useId();
  const text = useRef<HTMLTextAreaElement>(null);
  const active = useRef(true);
  const [copying, setCopying] = useState(false);
  const [copied, setCopied] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  useEffect(() => {
    setCopied(false);
    setMessage(null);
  }, [prompt]);
  const copy = async () => {
    setCopying(true);
    setCopied(false);
    setMessage(null);
    try {
      await copyCoachingPrompt(prompt, navigator.clipboard);
      if (active.current) {
        setCopied(true);
        setMessage(
          "Prompt copied. Open ChatGPT and paste it into a conversation.",
        );
      }
    } catch {
      if (active.current) {
        text.current?.focus();
        text.current?.select();
        setMessage(
          "Clipboard access was unavailable. The prompt is selected; copy it manually with your device’s copy command.",
        );
      }
    } finally {
      if (active.current) setCopying(false);
    }
  };
  return (
    <section
      id="ai-coaching-prompt"
      className="panel feedback-panel prompt-panel"
      aria-labelledby={`${id}-title`}
    >
      <div className="panel-heading">
        <div>
          <p className="eyebrow">04 / YOUR COACHING CONVERSATION</p>
          <h2 id={`${id}-title`}>AI Coaching Prompt</h2>
        </div>
        <span className="section-icon">
          <Icon name="spark" />
        </span>
      </div>
      <p className="prompt-description">
        Turn your measurements into a coaching conversation. Copy the prompt,
        open ChatGPT, and paste it when you’re ready.
      </p>
      <label className="field-label mt-5" htmlFor={`${id}-text`}>
        Your ready-to-use prompt
      </label>
      <textarea
        ref={text}
        id={`${id}-text`}
        className="field coaching-prompt"
        value={prompt}
        readOnly
        rows={12}
        spellCheck={false}
        aria-describedby={`${id}-help`}
      />
      <div className="prompt-actions">
        <button
          type="button"
          className="button button-primary"
          onClick={copy}
          disabled={copying || !prompt.trim()}
        >
          <Icon name={copied ? "check" : "copy"} width={17} />
          {copying ? "Copying…" : copied ? "Copied!" : "Copy to Clipboard"}
        </button>
        <a
          className="button button-secondary"
          href="https://chatgpt.com"
          target="_blank"
          rel="noopener noreferrer"
          referrerPolicy="no-referrer"
        >
          Open ChatGPT
          <Icon name="external" width={15} />
        </a>
      </div>
      {message && (
        <p
          className={`message ${copied ? "message-success" : "message-warning"}`}
          role="status"
        >
          {message}
        </p>
      )}
      <p id={`${id}-help`} className="help-text mt-4">
        Opening ChatGPT only opens a new tab. You choose when to paste and send
        the measurements.
      </p>
    </section>
  );
}
