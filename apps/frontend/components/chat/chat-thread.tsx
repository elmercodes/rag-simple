"use client";

import * as React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import MessageBubble from "@/components/chat/message-bubble";
import type { Message } from "@/components/chat/chat-app";

type ChatThreadProps = {
  messages: Message[];
  streamingMessage?: Message | null;
};

export default function ChatThread({
  messages,
  streamingMessage
}: ChatThreadProps) {
  const bottomRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamingMessage]);

  return (
    <div className="flex-1 min-h-0 min-w-0 px-4 py-6 md:px-6">
      <ScrollArea className="h-full">
        <div className="space-y-4 pr-2">
          {messages.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-border bg-card/80 p-8 text-center text-sm text-muted">
              Start a conversation by asking your first question.
            </div>
          ) : (
            messages.map((message, index) => (
              <MessageBubble
                key={message.id ?? `${message.role}-${index}`}
                message={message}
              />
            ))
          )}
          {streamingMessage ? (
            <MessageBubble
              key={`streaming-${streamingMessage.role}`}
              message={streamingMessage}
            />
          ) : null}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>
    </div>
  );
}
