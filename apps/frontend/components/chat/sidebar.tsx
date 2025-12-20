"use client";

import * as React from "react";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy
} from "@dnd-kit/sortable";
import { restrictToVerticalAxis } from "@dnd-kit/modifiers";
import {
  MoreHorizontal,
  Pin as PinIcon,
  PinOff,
  Plus,
  Check,
  ChevronDown,
  Stethoscope,
  Trash2,
  Loader2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { badgeVariants } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type {
  AIModel,
  Attachment,
  Conversation
} from "@/components/chat/chat-app";

type SidebarProps = {
  pinnedConversations: Conversation[];
  conversations: Conversation[];
  activeId: string;
  attachments: Attachment[];
  isUploadingAttachments?: boolean;
  selectedModel: AIModel;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onSelectAttachment: (attachment: Attachment) => void;
  onTogglePin: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onReorderPinned: (ids: string[]) => void;
  onSelectModel: (model: AIModel) => void;
};

export default function Sidebar({
  pinnedConversations,
  conversations,
  activeId,
  attachments,
  isUploadingAttachments = false,
  selectedModel,
  onNewChat,
  onSelectConversation,
  onSelectAttachment,
  onTogglePin,
  onDeleteConversation,
  onReorderPinned,
  onSelectModel
}: SidebarProps) {
  const modelOptions: AIModel[] = ["gpt-5-nano", "Qwen3"];
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 }
    })
  );

  const handleKeyPress = (event: React.KeyboardEvent, id: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelectConversation(id);
    }
  };

  const renderConversation = (
    conversation: Conversation,
    sortable?: ReturnType<typeof useSortable>
  ) => {
    const lastMessage =
      conversation.messages[conversation.messages.length - 1];
    const isActive = conversation.id === activeId;
    const draggableStyle =
      sortable && (sortable.transform || sortable.transition)
        ? {
            transform: sortable.transform
              ? `translate3d(${sortable.transform.x}px, ${sortable.transform.y}px, 0) scale(${sortable.transform.scaleX}, ${sortable.transform.scaleY})`
              : undefined,
            transition: sortable.transition
          }
        : undefined;
    const { onKeyDown: sortableKeyDown, ...sortableListeners } =
      sortable?.listeners ?? {};
    const draggableHandlers =
      sortable?.attributes || sortableListeners
        ? { ...(sortable?.attributes ?? {}), ...sortableListeners }
        : {};

    return (
      <div
        key={conversation.id}
        role="button"
        tabIndex={0}
        ref={sortable?.setNodeRef}
        className={cn(
          "group relative w-full rounded-2xl border px-4 py-3 text-left transition",
          isActive
            ? "border-active-border bg-active-bg text-active-text shadow-glow"
            : "border-chip/60 bg-chip/70 text-chip-text hover:bg-chip/80",
          sortable ? "cursor-grab active:cursor-grabbing" : ""
        )}
        onClick={() => onSelectConversation(conversation.id)}
        onKeyDown={(event) => {
          sortableKeyDown?.(event);
          if (!event.defaultPrevented) {
            handleKeyPress(event, conversation.id);
          }
        }}
        style={draggableStyle}
        {...draggableHandlers}
      >
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <div
              className={cn(
                "text-sm font-semibold",
                isActive ? "text-active-text" : "text-ink"
              )}
            >
              {conversation.title}
            </div>
            <div
              className={cn(
                "mt-1 text-xs",
                isActive ? "text-active-text/80" : "text-muted"
              )}
            >
              {lastMessage?.content ?? "No messages yet."}
            </div>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className={cn(
                  "rounded-full p-1 text-muted transition hover:bg-accent/50 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-strong/40",
                  "opacity-100 md:opacity-0 md:group-hover:opacity-100"
                )}
                aria-label="Conversation actions"
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
              >
                <MoreHorizontal className="h-4 w-4" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              side="right"
              align="end"
              sideOffset={8}
              onClick={(event) => event.stopPropagation()}
              className="z-50"
            >
              <DropdownMenuItem
                onSelect={(event) => {
                  event.preventDefault();
                  onTogglePin(conversation.id);
                }}
              >
                {conversation.isPinned ? (
                  <PinOff className="h-4 w-4" />
                ) : (
                  <PinIcon className="h-4 w-4" />
                )}
                <span>{conversation.isPinned ? "Unpin" : "Pin"}</span>
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-red-500 focus:text-red-500"
                onSelect={(event) => {
                  event.preventDefault();
                  onDeleteConversation(conversation.id);
                }}
              >
                <Trash2 className="h-4 w-4" />
                <span>Delete</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    );
  };

  const SortableConversation = ({ conversation }: { conversation: Conversation }) => {
    const sortable = useSortable({ id: conversation.id });
    return renderConversation(conversation, sortable);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const ids = pinnedConversations.map((conversation) => conversation.id);
    const oldIndex = ids.indexOf(String(active.id));
    const newIndex = ids.indexOf(String(over.id));
    if (oldIndex === -1 || newIndex === -1) return;
    onReorderPinned(arrayMove(ids, oldIndex, newIndex));
  };

  return (
    <aside className="flex h-full min-h-0 w-[clamp(220px,22vw,320px)] min-w-[220px] max-w-[320px] shrink-0 flex-col border-r border-border bg-panel/80">
      <div className="px-5 pb-4 pt-5">
        <div className="flex items-center gap-3 text-ink">
          <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-accent/70 text-ink">
            <Stethoscope className="h-5 w-5" />
          </span>
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.3em] text-muted">
              Studio
            </div>
            <div className="text-lg font-semibold">Doc. Chat</div>
          </div>
        </div>
        <Button
          className="mt-4 w-full justify-center bg-accent text-accent-contrast shadow-glow hover:bg-accent/90"
          onClick={onNewChat}
        >
          <Plus className="h-4 w-4" />
          New chat
        </Button>
      </div>

      <div className="px-5 pb-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted">
          Attachments
        </div>
        <div className="mt-3 flex max-w-full gap-2 overflow-x-auto pb-2">
          {attachments.length === 0 ? (
            <div className="text-xs text-muted">
              No files attached to this conversation.
            </div>
          ) : (
            attachments.map((attachment) => (
              <button
                key={attachment.id}
                type="button"
                onClick={() => onSelectAttachment(attachment)}
                className={cn(
                  badgeVariants(),
                  "shrink-0 cursor-pointer transition hover:border-accent hover:bg-accent/60 hover:text-ink"
                )}
              >
                {attachment.name}
              </button>
            ))
          )}
        </div>
        {isUploadingAttachments ? (
          <div className="mt-2 flex items-center gap-2 text-xs text-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Uploading / indexing...
          </div>
        ) : null}
      </div>

      <div className="px-5 pb-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted">
          AI Model
        </div>
        <div className="mt-3">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="flex w-full items-center justify-between rounded-2xl border border-border bg-card/80 px-3 py-2.5 text-sm text-ink shadow-glow transition hover:border-accent hover:bg-accent/40"
              >
                <span className="truncate">{selectedModel}</span>
                <ChevronDown className="h-4 w-4 text-muted" aria-hidden />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="start"
              sideOffset={8}
              className="w-[220px]"
            >
              {modelOptions.map((option) => (
                <DropdownMenuItem
                  key={option}
                  onSelect={(event) => {
                    event.preventDefault();
                    onSelectModel(option);
                  }}
                  className="flex items-center justify-between text-ink"
                >
                  <span>{option}</span>
                  {selectedModel === option ? (
                    <span className="flex items-center gap-1 rounded-full bg-accent/40 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-ink">
                      <Check className="h-3 w-3" />
                      Active
                    </span>
                  ) : null}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="flex items-center justify-between px-5 pb-3">
        <span className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted">
          Conversations
        </span>
      </div>

      <ScrollArea className="flex-1 px-3 pb-6">
        <div className="space-y-5">
          {pinnedConversations.length > 0 ? (
            <div className="space-y-2">
              <div className="px-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-muted">
                Pinned
              </div>
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handleDragEnd}
                modifiers={[restrictToVerticalAxis]}
              >
                <SortableContext
                  items={pinnedConversations.map((conversation) => conversation.id)}
                  strategy={verticalListSortingStrategy}
                >
                  <div className="space-y-2">
                    {pinnedConversations.map((conversation) => (
                      <SortableConversation
                        key={conversation.id}
                        conversation={conversation}
                      />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>
            </div>
          ) : null}
          <div className="space-y-2">
            <div className="px-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-muted">
              Recent
            </div>
            {conversations.length === 0 ? (
              <div className="px-2 text-xs text-muted">
                No recent conversations yet.
              </div>
            ) : (
              conversations.map((conversation) => renderConversation(conversation))
            )}
          </div>
        </div>
      </ScrollArea>
    </aside>
  );
}
