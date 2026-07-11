"use client";

import type { EveMessage } from "eve/react";
import { Markdown } from "./Markdown";
import { ToolCallView } from "./ToolCallView";

export function MessageBubble({ message }: { message: EveMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`msg-row role-${message.role}`}>
      <div className={`msg-bubble role-${message.role}`}>
        {message.parts.map((part, i) => {
          switch (part.type) {
            case "text":
              return isUser ? (
                <span key={i} style={{ whiteSpace: "pre-wrap" }}>
                  {part.text}
                </span>
              ) : (
                <Markdown key={i} text={part.text} />
              );
            case "reasoning":
              return (
                <div key={i} className="msg-reasoning">
                  {part.text}
                </div>
              );
            case "dynamic-tool":
              return <ToolCallView key={part.toolCallId} part={part} />;
            case "step-start":
              return null;
            default:
              return null;
          }
        })}
        {message.metadata?.status === "failed" ? (
          <div className="msg-meta">failed to send</div>
        ) : null}
      </div>
    </div>
  );
}
