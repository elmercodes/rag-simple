"use client";

import * as React from "react";
import { Pencil, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type TitleEditorProps = {
  title: string;
  onRename: (title: string) => void;
};

export default function TitleEditor({ title, onRename }: TitleEditorProps) {
  const [isEditing, setIsEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(title);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    setDraft(title);
  }, [title]);

  React.useEffect(() => {
    if (isEditing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [isEditing]);

  const handleSave = () => {
    const next = draft.trim();
    if (next) {
      onRename(next);
    }
    setIsEditing(false);
  };

  const handleCancel = () => {
    setDraft(title);
    setIsEditing(false);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleSave();
    }
    if (event.key === "Escape") {
      event.preventDefault();
      handleCancel();
    }
  };

  return (
    <div className="flex items-center gap-3">
      {isEditing ? (
        <Input
          ref={inputRef}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          className="h-10 min-w-[220px]"
          aria-label="Rename conversation"
        />
      ) : (
        <div className="text-lg font-semibold text-ink">{title}</div>
      )}
      {isEditing ? (
        <div className="flex items-center gap-2">
          <Button size="icon" variant="outline" onClick={handleSave}>
            <Check className="h-4 w-4" />
          </Button>
          <Button size="icon" variant="ghost" onClick={handleCancel}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      ) : (
        <Button size="icon" variant="outline" onClick={() => setIsEditing(true)}>
          <Pencil className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}
