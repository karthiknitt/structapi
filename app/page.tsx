"use client";

import { useEffect, useRef } from "react";
import { useEveAgent } from "eve/react";
import { signOut, useSession } from "../lib/auth-client";
import { ChatInput } from "./_components/ChatInput";
import { MessageBubble } from "./_components/MessageBubble";
import { StatusDot } from "./_components/StatusDot";

export default function Page() {
  const agent = useEveAgent();
  const { data: session } = useSession();
  const scrollRef = useRef<HTMLDivElement>(null);
  const messages = agent.data?.messages ?? [];

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  const busy = agent.status === "submitted" || agent.status === "streaming";

  return (
    <div className="chat-shell">
      <header className="chat-header">
        <div className="chat-title">
          StructAgent <span className="dim">— IS-code structural design</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.9rem" }}>
          <a href="/history" style={{ color: "#9aa4b2", fontSize: "0.85rem" }}>
            History
          </a>
          <a href="/settings" style={{ color: "#9aa4b2", fontSize: "0.85rem" }}>
            Models
          </a>
          {session?.user ? (
            <>
              <span className="dim" style={{ fontSize: "0.85rem" }}>
                {session.user.email}
              </span>
              <button
                onClick={() => {
                  void signOut().then(() => {
                    window.location.href = "/signin";
                  });
                }}
                style={{
                  padding: "0.3rem 0.7rem",
                  borderRadius: 6,
                  border: "1px solid #2d3543",
                  background: "transparent",
                  color: "#9aa4b2",
                  fontSize: "0.8rem",
                  cursor: "pointer",
                }}
              >
                Sign out
              </button>
            </>
          ) : null}
          <StatusDot status={agent.status} />
        </div>
      </header>

      <div className="chat-scroll" ref={scrollRef}>
        <div className="chat-container">
          {messages.length === 0 ? (
            <div className="chat-empty">
              Ask StructAgent to design a beam, column, slab, footing, or
              other RCC member per IS 456:2000.
            </div>
          ) : (
            messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))
          )}
        </div>
      </div>

      {agent.error ? (
        <div className="chat-error">{agent.error.message ?? String(agent.error)}</div>
      ) : null}

      <ChatInput
        disabled={busy}
        onSend={(text) => {
          void agent.send(text);
        }}
      />
    </div>
  );
}
