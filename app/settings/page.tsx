"use client";

import { useEffect, useState } from "react";

type Model = { id: string; name: string; context?: number };

const box: React.CSSProperties = {
  width: "100%",
  padding: "0.55rem 0.7rem",
  borderRadius: 8,
  border: "1px solid #2d3543",
  background: "#0f141d",
  color: "#e6e6e6",
  fontSize: "0.9rem",
};

export default function SettingsPage() {
  const [models, setModels] = useState<Model[]>([]);
  const [source, setSource] = useState("");
  const [orchestrator, setOrchestrator] = useState("");
  const [subagents, setSubagents] = useState("");
  const [filter, setFilter] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/models")
      .then((r) => r.json())
      .then((d) => {
        setModels(d.models ?? []);
        setSource(d.source ?? "");
        setOrchestrator(d.selection?.orchestrator ?? "");
        setSubagents(d.selection?.subagents ?? "");
      })
      .catch(() => setMsg("Failed to load models"));
  }, []);

  const shown = filter
    ? models.filter((m) =>
        m.id.toLowerCase().includes(filter.toLowerCase()))
    : models;

  async function save() {
    setBusy(true);
    setMsg(null);
    const res = await fetch("/api/models", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ orchestrator, subagents }),
    });
    const d = await res.json();
    setBusy(false);
    setMsg(res.ok ? `Saved. ${d.note}` : d.error ?? "Save failed");
  }

  const select = (value: string, set: (v: string) => void) => (
    <select style={box} value={value} onChange={(e) => set(e.target.value)}>
      {value && !shown.some((m) => m.id === value) && (
        <option value={value}>{value} (current)</option>
      )}
      {shown.map((m) => (
        <option key={m.id} value={m.id}>
          {m.id}
          {m.context ? ` — ${Math.round(m.context / 1000)}k ctx` : ""}
        </option>
      ))}
    </select>
  );

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#0b0e14",
        color: "#e6e6e6",
        fontFamily: "system-ui, sans-serif",
        display: "flex",
        justifyContent: "center",
        paddingTop: "4rem",
      }}
    >
      <div style={{ width: 520, display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <h1 style={{ fontSize: "1.2rem", fontWeight: 600 }}>Model settings</h1>
          <a href="/" style={{ color: "#60a5fa", fontSize: "0.85rem" }}>← back to chat</a>
        </div>
        <p style={{ color: "#9aa4b2", fontSize: "0.85rem", margin: 0 }}>
          Models are served via OpenRouter ({models.length} available,
          source: {source || "…"}). Changes apply after restarting the agent
          host (<code>pnpm dev</code> / <code>pnpm tui</code>).
        </p>

        <input
          style={box}
          placeholder="Filter models (e.g. claude, gpt, gemini)"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />

        <label style={{ fontSize: "0.85rem", color: "#9aa4b2" }}>
          Orchestrator (main agent)
          {select(orchestrator, setOrchestrator)}
        </label>

        <label style={{ fontSize: "0.85rem", color: "#9aa4b2" }}>
          Specialist subagents (all 8: loads, beam, column, footing, slab,
          tank, sump, mixdesign)
          {select(subagents, setSubagents)}
        </label>

        <button
          onClick={save}
          disabled={busy || !orchestrator || !subagents}
          style={{
            ...box,
            background: "#2563eb",
            border: "none",
            cursor: "pointer",
            fontWeight: 600,
          }}
        >
          {busy ? "Saving…" : "Save"}
        </button>
        {msg && (
          <div style={{ fontSize: "0.85rem", color: msg.startsWith("Saved") ? "#4ade80" : "#f87171" }}>
            {msg}
          </div>
        )}
      </div>
    </main>
  );
}
