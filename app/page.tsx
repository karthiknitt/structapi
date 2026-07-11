"use client";

import { useEffect, useRef } from "react";
import { useEveAgent } from "eve/react";
import { ChatInput } from "./_components/ChatInput";
import { MessageBubble } from "./_components/MessageBubble";
import { StatusDot } from "./_components/StatusDot";

export default function Page() {
  const agent = useEveAgent();
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
        <StatusDot status={agent.status} />
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
          void agent.send({ message: text });
        }}
      />
    </div>
  );
}
