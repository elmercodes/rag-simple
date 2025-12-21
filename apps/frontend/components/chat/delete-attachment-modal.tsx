"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";

type DeleteAttachmentModalProps = {
  open: boolean;
  attachmentName: string;
  isDeleting?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export default function DeleteAttachmentModal({
  open,
  attachmentName,
  isDeleting = false,
  onConfirm,
  onCancel
}: DeleteAttachmentModalProps) {
  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-3xl border border-border bg-panel/95 p-6 shadow-2xl">
        <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted">
          Delete document
        </div>
        <div className="mt-2 text-lg font-semibold text-ink">
          Delete this document?
        </div>
        <div className="mt-1 text-sm text-muted">
          This removes it from the conversation and frees an attachment slot.
        </div>
        {attachmentName ? (
          <div className="mt-2 text-xs text-muted">{attachmentName}</div>
        ) : null}
        <div className="mt-6 flex items-center justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="outline"
            className="border-red-500 text-red-500 hover:bg-red-500/10"
            onClick={onConfirm}
            disabled={isDeleting}
          >
            {isDeleting ? "Deleting..." : "Delete"}
          </Button>
        </div>
      </div>
    </div>,
    document.body
  );
}
