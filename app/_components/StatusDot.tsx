"use client";

import type { UseEveAgentStatus } from "eve/react";

const COLORS: Record<UseEveAgentStatus, string> = {
  ready: "var(--green)",
  submitted: "var(--amber)",
  streaming: "var(--amber)",
  resuming: "var(--amber)",
  error: "var(--red)",
};

const LABELS: Record<UseEveAgentStatus, string> = {
  ready: "Ready",
  submitted: "Sending",
  streaming: "Streaming",
  resuming: "Resuming",
  error: "Error",
};

export function StatusDot({ status }: { status: UseEveAgentStatus }) {
  const color = COLORS[status];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 12,
        color: "var(--text-dim)",
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: color,
          boxShadow:
            status === "streaming" ||
            status === "submitted" ||
            status === "resuming"
              ? `0 0 0 3px ${color}22`
              : "none",
          transition: "box-shadow 0.2s ease",
        }}
      />
      {LABELS[status]}
    </span>
  );
}
