"use client";

import { signIn } from "../../lib/auth-client";

export default function SignInPage() {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "1.5rem",
        background: "#0b0e14",
        color: "#e6e6e6",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>
        StructAgent — IS-code structural design
      </h1>
      <p style={{ color: "#9aa4b2", maxWidth: 420, textAlign: "center" }}>
        Sign in to design beams, columns, footings, slabs, tanks and concrete
        mixes per the Indian Standards.
      </p>
      <button
        onClick={() =>
          signIn.social({ provider: "google", callbackURL: "/" })
        }
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.6rem",
          padding: "0.7rem 1.4rem",
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
