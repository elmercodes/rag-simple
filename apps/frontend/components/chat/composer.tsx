"use client";

import * as React from "react";
import { Paperclip, SendHorizontal, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type ComposerProps = {
  disabled?: boolean;
  isStreaming?: boolean;
  onSendMessage: (message: string, useDocs: boolean) => void;
  onAttachFiles: (files: FileList) => void;
  useDocs: boolean;
  onToggleUseDocs: (value: boolean) => void;
  useDocsEnabled?: boolean;
  isUploadingAttachments?: boolean;
};

export default function Composer({
  disabled,
  isStreaming,
  onSendMessage,
  onAttachFiles,
  useDocs,
  onToggleUseDocs,
  useDocsEnabled = true,
  isUploadingAttachments = false
}: ComposerProps) {
  const [value, setValue] = React.useState("");
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const handleSend = () => {
    if (!value.trim()) return;
    onSendMessage(value, useDocs);
    setValue("");
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  const handleFilesSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      onAttachFiles(event.target.files);
      event.target.value = "";
    }
  };

  return (
    <div className="shrink-0 border-t border-border bg-panel/90 px-5 py-4">
      <div className="flex min-w-0 flex-wrap items-end gap-3 md:flex-nowrap">
        <button
          type="button"
          className="flex h-11 w-11 items-center justify-center rounded-2xl border border-border bg-card/90 text-ink shadow-glow transition hover:bg-accent/40"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || isUploadingAttachments}
          aria-label="Attach files"
        >
          <Paperclip className="h-5 w-5" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleFilesSelected}
        />
        <div className="min-w-0 flex-1">
          <Textarea
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything. Shift + Enter for a new line."
            className="min-h-[88px] resize-none"
            disabled={disabled}
          />
        </div>
        <div className="flex w-fit flex-col items-end gap-2">
          <div className="flex w-full justify-center">
            <button
              type="button"
              aria-pressed={useDocs}
              onClick={() => {
                if (!useDocsEnabled) return;
                onToggleUseDocs(!useDocs);
              }}
              className={cn(
                "relative h-6 w-12 overflow-hidden rounded-full border px-1 transition",
                useDocs
                  ? "border-accent-strong bg-ink/70 text-ink shadow-glow"
                  : "border-border bg-card/90 hover:border-accent",
                !useDocsEnabled ? "cursor-not-allowed opacity-50" : ""
              )}
              aria-label="Toggle use documents"
              role="switch"
              aria-checked={useDocs}
              aria-disabled={!useDocsEnabled}
            >
              <span
                className={cn(
                  "absolute left-1 top-1/2 h-4 w-4 -translate-y-1/2 rounded-full bg-card shadow transition-transform",
                  useDocs ? "translate-x-6" : "translate-x-0"
                )}
                aria-hidden
              />
            </button>
          </div>
          <div className="flex w-fit flex-col items-end gap-1 self-end">
            <Button
              type="button"
              onClick={handleSend}
              disabled={disabled || isStreaming || !value.trim()}
              className="h-11 rounded-2xl px-5"
            >
              <SendHorizontal className="h-4 w-4" />
              Send
            </Button>
            <span className="self-start text-left text-xs text-muted">
              {useDocs ? "Use documents" : "General answer"}
            </span>
          </div>
        </div>
      </div>
      <div className="mt-2 text-xs text-muted">
        Enter to send, Shift + Enter for newline.
      </div>
      {isUploadingAttachments ? (
        <div className="mt-2 flex items-center gap-2 text-xs text-muted">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Uploading / indexing attachments...
        </div>
      ) : null}
    </div>
  );
}
