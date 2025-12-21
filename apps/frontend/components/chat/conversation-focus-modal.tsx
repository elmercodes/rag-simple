"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";

type ConversationFocusModalProps = {
  open: boolean;
  isSaving?: boolean;
  onSubmit: (focusType: 0 | 1 | 2) => void;
  onClose?: () => void;
};

export default function ConversationFocusModal({
  open,
  isSaving = false,
  onSubmit,
  onClose
}: ConversationFocusModalProps) {
  const [focusType, setFocusType] = React.useState<0 | 1 | 2 | "">("");

  React.useEffect(() => {
    if (open) {
      setFocusType("");
    }
  }, [open]);

  if (!open) return null;

  const handleSave = () => {
    if (focusType === "") return;
    onSubmit(focusType);
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-3xl border border-border bg-panel/95 p-6 shadow-2xl">
        <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted">
          Conversation focus
        </div>
        <div className="mt-2 text-lg font-semibold text-ink">
          What is the focus of this conversation?
        </div>
        <div className="mt-5 space-y-2">
          <label className="text-xs font-semibold uppercase tracking-[0.18em] text-muted">
            Select a focus
          </label>
          <select
            value={focusType}
            onChange={(event) => {
              const value = event.target.value;
              if (value === "") {
                setFocusType("");
              } else {
                setFocusType(Number(value) as 0 | 1 | 2);
              }
            }}
            className="w-full rounded-2xl border border-border bg-card/80 px-4 py-3 text-sm text-ink shadow-soft focus:outline-none focus:ring-2 focus:ring-accent-strong"
            aria-label="Conversation focus"
          >
            <option value="" disabled>
              Select focus
            </option>
            <option value="0">Research paper</option>
            <option value="1">Manual</option>
            <option value="2">Other</option>
          </select>
        </div>
        <div className="mt-6 flex items-center justify-end gap-2">
          {onClose ? (
            <Button type="button" variant="ghost" onClick={onClose}>
              Not now
            </Button>
          ) : null}
          <Button
            type="button"
            onClick={handleSave}
            disabled={focusType === "" || isSaving}
          >
            {isSaving ? "Saving..." : "Save"}
          </Button>
        </div>
      </div>
    </div>,
    document.body
  );
}
