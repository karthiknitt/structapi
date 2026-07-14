"use client";

import { useEffect, useState } from "react";
import { Markdown } from "../_components/Markdown";

interface SessionSummary {
  runId: string;
  title: string;
  status: string;
  createdAt: string;
  updatedAt: string;
}

interface SessionMessage {
  role: "user" | "assistant";
  turnId: string;
  text: string;
}

interface SubagentRun {
  runId: string;
  subagent: string;
  status: string;
}

interface SessionDetail extends SessionSummary {
  messages: SessionMessage[];
  subagents: SubagentRun[];
  artifacts: { runId: string; files: string[] }[];
}

export default function HistoryPage() {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    fetch("/api/history")
      .then((r) => r.json())
      .then((body) => setSessions(body.sessions ?? []));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setLoadingDetail(true);
    setDetail(null);
    fetch(`/api/history/${selectedId}`)
      .then((r) => r.json())
      .then((body) => setDetail(body))
      .finally(() => setLoadingDetail(false));
  }, [selectedId]);

  return (
    <div className="history-shell">
      <header className="chat-header">
        <div className="chat-title">
          Chat History <span className="dim">— past StructAgent sessions</span>
        </div>
        <a href="/" style={{ color: "#9aa4b2", fontSize: "0.85rem" }}>
          Back to chat
        </a>
      </header>

      <div className="history-body">
        <div className="history-list">
          {sessions === null ? (
            <div className="history-empty">Loading…</div>
          ) : sessions.length === 0 ? (
            <div className="history-empty">No sessions yet.</div>
          ) : (
            sessions.map((s) => (
              <button
                key={s.runId}
                className={`history-item${s.runId === selectedId ? " active" : ""}`}
                onClick={() => setSelectedId(s.runId)}
              >
                <div className="history-item-title">{s.title}</div>
                <div className="history-item-meta">
                  <span className={`history-status ${s.status}`}>{s.status}</span>
                  <span>{new Date(s.createdAt).toLocaleString()}</span>
                </div>
              </button>
            ))
          )}
        </div>

        <div className="history-detail">
          {!selectedId ? (
            <div className="history-empty">
              Select a session on the left to view its transcript and outputs.
            </div>
          ) : loadingDetail || !detail ? (
            <div className="history-empty">Loading…</div>
          ) : (
            <>
              <div className="history-detail-header">
                <div className="history-detail-title">{detail.title}</div>
                <div className="history-item-meta">
                  <span className={`history-status ${detail.status}`}>
                    {detail.status}
                  </span>
                  <span>{new Date(detail.createdAt).toLocaleString()}</span>
                </div>
              </div>

              {detail.messages.length === 0 ? (
                <div className="history-empty">
                  No messages captured for this session yet.
                </div>
              ) : (
                <div className="chat-container" style={{ maxWidth: "none" }}>
                  {detail.messages.map((m, i) => (
                    <div key={i} className={`msg-row role-${m.role}`}>
                      <div className={`msg-bubble role-${m.role}`}>
                        {m.role === "user" ? (
                          <span style={{ whiteSpace: "pre-wrap" }}>{m.text}</span>
                        ) : (
                          <Markdown text={m.text} />
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {detail.subagents.length > 0 ? (
                <>
                  <div className="history-section-label">
                    Subagents called ({detail.subagents.length})
                  </div>
                  <div className="history-subagents">
                    {detail.subagents.map((s) => (
                      <span key={s.runId} className="history-subagent-chip">
                        {s.subagent} — {s.status}
                      </span>
                    ))}
                  </div>
                </>
              ) : null}

              {detail.artifacts.length > 0 ? (
                <>
                  <div className="history-section-label">Generated files</div>
                  <div className="history-artifacts">
                    {detail.artifacts.flatMap(({ runId, files }) =>
                      files.map((f) => (
                        <a
                          key={`${runId}/${f}`}
                          className="history-artifact"
                          href={`/outputs/${runId}/${f}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {f}
                        </a>
                      ))
                    )}
                  </div>
                </>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
