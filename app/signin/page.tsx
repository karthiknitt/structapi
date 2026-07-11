"use client";

import { useState } from "react";
import { authClient, signIn } from "../../lib/auth-client";

const field: React.CSSProperties = {
  width: "100%",
  padding: "0.6rem 0.8rem",
  borderRadius: 8,
  border: "1px solid #2d3543",
  background: "#0f141d",
  color: "#e6e6e6",
  fontSize: "0.95rem",
};

export default function SignInPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const res =
      mode === "signin"
        ? await authClient.signIn.email({ email, password })
        : await authClient.signUp.email({ email, password, name: name || email });
    setBusy(false);
    if (res.error) {
      setError(res.error.message ?? "Authentication failed");
    } else {
      window.location.href = "/";
    }
  }

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "1.25rem",
        background: "#0b0e14",
        color: "#e6e6e6",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h1 style={{ fontSize: "1.4rem", fontWeight: 600 }}>
        StructAgent — IS-code structural design
      </h1>

      <form
        onSubmit={submit}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.7rem",
          width: 340,
          padding: "1.4rem",
          borderRadius: 12,
          border: "1px solid #1f2634",
          background: "#111622",
        }}
      >
        {mode === "signup" && (
          <input
            style={field}
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        )}
        <input
          style={field}
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          style={field}
          type="password"
          required
          minLength={8}
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && (
          <div style={{ color: "#f87171", fontSize: "0.85rem" }}>{error}</div>
        )}
        <button
          type="submit"
          disabled={busy}
          style={{
            ...field,
            background: "#2563eb",
            border: "none",
            cursor: "pointer",
            fontWeight: 600,
          }}
        >
          {busy ? "…" : mode === "signin" ? "Sign in" : "Create account"}
        </button>
        <button
          type="button"
          onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
          style={{
            background: "none",
            border: "none",
            color: "#9aa4b2",
            fontSize: "0.82rem",
            cursor: "pointer",
          }}
        >
          {mode === "signin"
            ? "No account? Create one"
            : "Have an account? Sign in"}
        </button>
      </form>

      <div style={{ color: "#5b6472", fontSize: "0.8rem" }}>— or —</div>

      <button
        onClick={() => signIn.social({ provider: "google", callbackURL: "/" })}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.6rem",
          padding: "0.65rem 1.3rem",
          borderRadius: 8,
          border: "1px solid #2d3543",
          background: "#161b26",
          color: "#e6e6e6",
          fontSize: "0.95rem",
          cursor: "pointer",
        }}
      >
        <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
          <path fill="#FFC107" d="M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.3 6.1 29.4 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.6-.4-3.9z"/>
          <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.3 6.1 29.4 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>
          <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/>
          <path fill="#1976D2" d="M43.6 20.1H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C41 35.2 44 30 44 24c0-1.3-.1-2.6-.4-3.9z"/>
        </svg>
        Continue with Google
      </button>
    </main>
  );
}
