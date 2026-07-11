"use client";

import { useState } from "react";
import type { EveDynamicToolPart } from "eve/react";

function findPngHostPath(value: unknown): string | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  if (typeof record.hostPath === "string" && /\.png$/i.test(record.hostPath)) {
    return record.hostPath;
  }
  return undefined;
}

const STATE_LABEL: Record<string, string> = {
  "input-streaming": "calling…",
  "input-available": "running…",
  "approval-requested": "needs approval",
  "approval-responded": "approved",
  "output-available": "done",
  "output-error": "failed",
  "output-denied": "denied",
};

export function ToolCallView({ part }: { part: EveDynamicToolPart }) {
  const [open, setOpen] = useState(false);
  const displayName = part.toolMetadata?.eve?.name ?? part.toolName;
  const pngPath =
    part.state === "output-available" ? findPngHostPath(part.output) : undefined;

  return (
    <div className="tool-call">
      <button
        type="button"
        className="tool-call-header"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="tool-call-caret">{open ? "▾" : "▸"}</span>
        <span className="tool-call-name">{displayName}</span>
        <span className={`tool-call-badge state-${part.state}`}>
          {STATE_LABEL[part.state] ?? part.state}
        </span>
      </button>
      {open && (
        <div className="tool-call-body">
          {"input" in part && part.input !== undefined ? (
            <div>
              <div className="tool-call-label">input</div>
              <pre>{JSON.stringify(part.input, null, 2)}</pre>
            </div>
          ) : null}
          {part.state === "output-available" ? (
            <div>
              <div className="tool-call-label">output</div>
              <pre>{JSON.stringify(part.output, null, 2)}</pre>
            </div>
          ) : null}
          {part.state === "output-error" ? (
            <div>
              <div className="tool-call-label">error</div>
              <pre className="tool-call-error">{part.errorText}</pre>
            </div>
          ) : null}
        </div>
      )}
      {pngPath ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={pngPath} alt={displayName} className="tool-call-image" />
      ) : null}
    </div>
  );
}
