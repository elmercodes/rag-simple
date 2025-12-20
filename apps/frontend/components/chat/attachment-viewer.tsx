"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { ArrowLeft, ChevronDown } from "lucide-react";
import * as mammoth from "mammoth/mammoth.browser";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Attachment } from "@/components/chat/chat-app";
import { cn } from "@/lib/utils";
import { attachmentContentUrl, getArrayBuffer, getText } from "@/lib/api";

type AttachmentViewerProps = {
  attachment: Attachment;
  attachments: Attachment[];
  onClose: () => void;
  onSelectAttachment: (attachment: Attachment) => void;
  variant: "sidebar" | "overlay";
  className?: string;
};

export default function AttachmentViewer({
  attachment,
  attachments,
  onClose,
  onSelectAttachment,
  variant,
  className
}: AttachmentViewerProps) {
  const [textContent, setTextContent] = React.useState<string>("");
  const [isLoadingText, setIsLoadingText] = React.useState(false);
  const [docxHtml, setDocxHtml] = React.useState("");
  const [docxError, setDocxError] = React.useState(false);
  const [isLoadingDocx, setIsLoadingDocx] = React.useState(false);
  const [isMenuOpen, setIsMenuOpen] = React.useState(false);
  const buttonRef = React.useRef<HTMLButtonElement>(null);
  const menuRef = React.useRef<HTMLDivElement>(null);
  const [menuPosition, setMenuPosition] = React.useState({
    top: 0,
    left: 0
  });
  const isPdf = attachment.type === "pdf";
  const isTxt = attachment.type === "txt";
  const isDocx = attachment.type === "docx";
  const hasMultipleAttachments = attachments.length > 1;
  const isOverlay = variant === "overlay";

  React.useEffect(() => {
    if (!isTxt) {
      setTextContent("");
      setIsLoadingText(false);
      return;
    }

    if (!attachment.id) {
      setTextContent("Preview unavailable.");
      setIsLoadingText(false);
      return;
    }

    let isActive = true;
    setIsLoadingText(true);
    getText(attachmentContentUrl(attachment.id))
      .then((text) => {
        if (isActive) {
          setTextContent(text);
        }
      })
      .catch(() => {
        if (isActive) {
          setTextContent("Unable to load text preview.");
        }
      })
      .finally(() => {
        if (isActive) {
          setIsLoadingText(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, [attachment.id, attachment.type, isTxt]);

  React.useEffect(() => {
    if (!isDocx) {
      setDocxHtml("");
      setDocxError(false);
      setIsLoadingDocx(false);
      return;
    }

    if (!attachment.id) {
      setDocxHtml("");
      setDocxError(true);
      setIsLoadingDocx(false);
      return;
    }

    let isActive = true;
    setIsLoadingDocx(true);
    setDocxError(false);
    setDocxHtml("");
    getArrayBuffer(attachmentContentUrl(attachment.id))
      .then((buffer) => mammoth.convertToHtml({ arrayBuffer: buffer }))
      .then((result) => {
        if (isActive) {
          setDocxHtml(result.value || "");
        }
      })
      .catch(() => {
        if (isActive) {
          setDocxError(true);
        }
      })
      .finally(() => {
        if (isActive) {
          setIsLoadingDocx(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, [attachment.id, attachment.type, isDocx]);

  React.useEffect(() => {
    if (!isMenuOpen) return;

    const updatePosition = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (!rect) return;
      const menuWidth = 256;
      const left = Math.max(16, rect.right - menuWidth);
      const top = rect.bottom + 8;
      setMenuPosition({ top, left });
    };

    updatePosition();

    const handleClickOutside = (event: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(event.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setIsMenuOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [isMenuOpen]);

  return (
    <aside
      className={cn(
        isOverlay
          ? "fixed inset-0 z-50 flex h-full w-full flex-col overflow-hidden bg-panel/95 shadow-2xl"
          : "flex h-full min-h-0 w-[min(100vw,clamp(320px,30vw,520px))] shrink-0 flex-col border-l border-border bg-panel/80",
        className
      )}
    >
      <div className="flex items-center gap-3 border-b border-border px-4 py-3">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Back to chats"
          onClick={onClose}
          className="h-9 w-9 rounded-xl border border-border bg-card/80 text-ink shadow-glow hover:bg-accent/50"
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className="flex min-w-0 flex-col">
            <span className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted">
              Attachment
            </span>
            <span className="truncate text-sm font-semibold text-ink">
              {attachment.name}
            </span>
          </div>
          {hasMultipleAttachments ? (
            <div className="relative">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Switch attachment"
                aria-expanded={isMenuOpen}
                onClick={() => setIsMenuOpen((prev) => !prev)}
                ref={buttonRef}
                className="h-8 w-8 rounded-xl border border-border bg-card/80 text-ink shadow-glow hover:bg-accent/50"
              >
                <ChevronDown className="h-4 w-4" />
              </Button>
              {isMenuOpen && typeof document !== "undefined"
                ? createPortal(
                    <div
                      ref={menuRef}
                      className="fixed z-[70] w-64 rounded-2xl border border-border bg-card p-2 shadow-soft"
                      style={{
                        top: menuPosition.top,
                        left: menuPosition.left
                      }}
                    >
                      <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-muted">
                        Attachments
                      </div>
                      <div className="mt-1 space-y-1">
                        {attachments.map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => {
                              onSelectAttachment(item);
                              setIsMenuOpen(false);
                            }}
                            className={cn(
                              "flex w-full items-center justify-between rounded-xl border px-3 py-2 text-left text-sm transition",
                              item.id === attachment.id
                                ? "border-accent-strong bg-accent/40 text-ink shadow-glow"
                                : "border-border bg-panel/60 text-muted hover:bg-accent/30 hover:text-ink"
                            )}
                          >
                            <span className="truncate">{item.name}</span>
                          </button>
                        ))}
                      </div>
                    </div>,
                    document.body
                  )
                : null}
            </div>
          ) : null}
        </div>
      </div>
      <ScrollArea className="flex-1">
        <div className="space-y-4 p-4">
          {isPdf ? (
            attachment.id ? (
              <div className="h-[70vh] w-full overflow-hidden rounded-2xl border border-border bg-card">
                <iframe
                  title={attachment.name}
                  src={attachmentContentUrl(attachment.id)}
                  className="h-full w-full"
                />
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-border bg-panel/60 p-6 text-sm text-muted">
                Preview unavailable.
              </div>
            )
          ) : null}
          {isTxt ? (
            <div className="rounded-2xl border border-border bg-card p-4">
              <pre className="whitespace-pre-wrap text-sm text-ink">
                {isLoadingText ? "Loading text preview..." : textContent}
              </pre>
            </div>
          ) : null}
          {isDocx ? (
            <div className="rounded-2xl border border-border bg-card p-4">
              {isLoadingDocx ? (
                <div className="text-sm text-muted">
                  Loading docx preview...
                </div>
              ) : docxError ? (
                <div className="text-sm text-muted">
                  Couldn't preview this docx.
                </div>
              ) : docxHtml ? (
                <div
                  className="prose prose-sm max-w-none text-ink leading-relaxed"
                  dangerouslySetInnerHTML={{ __html: docxHtml }}
                />
              ) : (
                <div className="text-sm text-muted">Preview unavailable.</div>
              )}
            </div>
          ) : null}
          {!isPdf && !isTxt && !isDocx ? (
            <div className="rounded-2xl border border-dashed border-border bg-panel/60 p-6 text-sm text-muted">
              <div className="font-semibold text-ink">{attachment.name}</div>
              <div className="mt-2">Preview not supported yet.</div>
            </div>
          ) : null}
        </div>
      </ScrollArea>
    </aside>
  );
}
