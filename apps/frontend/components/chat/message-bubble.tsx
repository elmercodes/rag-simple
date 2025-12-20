"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, User } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Message } from "@/components/chat/chat-app";

type MessageBubbleProps = {
  message: Message;
};

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex w-full gap-3",
        isUser ? "justify-end" : "justify-start"
      )}
    >
      {!isUser && (
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-accent/80 text-ink">
          <Bot className="h-5 w-5" />
        </div>
      )}
      <div
        className={cn(
          "max-w-[75%] break-words rounded-3xl border px-5 py-4 text-sm shadow-glow",
          isUser
            ? "border-transparent bg-user text-ink"
            : "border-border bg-assistant text-ink"
        )}
      >
        <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-muted">
          {isUser ? "You" : "Assistant"}
          {message.isStreaming && !isUser ? (
            <span className="rounded-full bg-accent/70 px-2 py-0.5 text-[10px] text-ink">
              Thinking
            </span>
          ) : null}
        </div>
        {message.content ? (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            className="prose prose-sm max-w-none break-words prose-pre:whitespace-pre-wrap prose-pre:break-words prose-pre:overflow-x-hidden"
          >
            {message.content}
          </ReactMarkdown>
        ) : (
          <div className="flex items-center gap-2 text-muted">
            <span className="inline-flex h-2 w-2 animate-pulse rounded-full bg-accent-strong" />
            <span className="text-xs">Generating response...</span>
          </div>
        )}
      </div>
      {isUser && (
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-accent/80 text-ink">
          <User className="h-5 w-5" />
        </div>
      )}
    </div>
  );
}
