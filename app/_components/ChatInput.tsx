"use client";

import { useRef, useState } from "react";

export function ChatInput({
  disabled,
  onSend,
}: {
  disabled: boolean;
  onSend: (text: string) => void;
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
    requestAnimationFrame(() => {
      if (textareaRef.current) textareaRef.current.style.height = "auto";
    });
  };

  return (
    <div className="chat-input-bar">
      <div className="chat-input-row">
        <textarea
          ref={textareaRef}
          value={value}
          placeholder="Describe the member to design, e.g. “RCC beam, 6 m span, 15 kN/m live load, M25/Fe500”"
          rows={1}
          onChange={(e) => {
            setValue(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button type="button" disabled={disabled || !value.trim()} onClick={submit}>
          Send
        </button>
      </div>
    </div>
  );
}
