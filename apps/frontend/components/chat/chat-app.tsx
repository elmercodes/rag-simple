"use client";

import * as React from "react";
import { mockStreamAssistantReply } from "@/lib/mockApi";
import Sidebar from "@/components/chat/sidebar";
import ChatThread from "@/components/chat/chat-thread";
import Composer from "@/components/chat/composer";
import TitleEditor from "@/components/chat/title-editor";
import AttachmentViewer from "@/components/chat/attachment-viewer";
import { Button } from "@/components/ui/button";
import { useTheme, type Theme } from "@/components/theme-provider";
import { Settings, Moon, Sun, PanelLeft, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  useDocs?: boolean;
};

export type Attachment = {
  id: string;
  name: string;
  type: "pdf" | "txt" | "doc" | "docx";
  url: string;
};

export type AIModel = "gpt-5-nano" | "Qwen3";

export type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  attachments: Attachment[];
  createdAt: number;
  lastUpdatedAt: number;
  isPinned: boolean;
  pinnedAt: number | null;
};

const seedTimestamp = 1_700_000_000_000;
const seedConversations: Conversation[] = [
  {
    id: "conv-aurora",
    title: "Aurora launch plan",
    attachments: [
      {
        id: "file-1",
        name: "product-brief.pdf",
        type: "pdf",
        url: "/demo.pdf"
      },
      {
        id: "file-2",
        name: "kickoff-notes.txt",
        type: "txt",
        url: "/demo.txt"
      },
      {
        id: "file-3",
        name: "demo.docx",
        type: "docx",
        url: "/demo.docx"
      }
    ],
    messages: [
      {
        id: "msg-1",
        role: "assistant",
        content:
          "Welcome back. Want me to draft a launch timeline, or start with a press-ready overview?"
      },
      {
        id: "msg-2",
        role: "user",
        content: "Start with a timeline and include key risks."
      }
    ],
    createdAt: seedTimestamp - 1000 * 60 * 60 * 2,
    lastUpdatedAt: seedTimestamp - 1000 * 60 * 45,
    isPinned: false,
    pinnedAt: null
  },
  {
    id: "conv-research",
    title: "Research recap",
    attachments: [],
    messages: [
      {
        id: "msg-3",
        role: "assistant",
        content:
          "I summarized the top findings and highlighted the gaps you can validate next week."
      }
    ],
    createdAt: seedTimestamp - 1000 * 60 * 60 * 6,
    lastUpdatedAt: seedTimestamp - 1000 * 60 * 60 * 3,
    isPinned: false,
    pinnedAt: null
  }
];

const createId = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);

const sortPinnedConversations = (
  list: Conversation[],
  order: string[]
) =>
  [...list]
    .filter((conversation) => conversation.isPinned)
    .sort((a, b) => {
      const aIndex = order.indexOf(a.id);
      const bIndex = order.indexOf(b.id);
      if (aIndex !== -1 && bIndex !== -1) return aIndex - bIndex;
      if (aIndex !== -1) return -1;
      if (bIndex !== -1) return 1;
      return (b.pinnedAt ?? 0) - (a.pinnedAt ?? 0);
    });

const sortUnpinnedConversations = (list: Conversation[]) =>
  [...list]
    .filter((conversation) => !conversation.isPinned)
    .sort((a, b) => {
      if (a.lastUpdatedAt !== b.lastUpdatedAt) {
        return b.lastUpdatedAt - a.lastUpdatedAt;
      }
      return b.createdAt - a.createdAt;
    });

export default function ChatApp() {
  const { theme, setTheme } = useTheme();
  const [isSettingsOpen, setIsSettingsOpen] = React.useState(false);
  const settingsRef = React.useRef<HTMLDivElement>(null);
  const [isSidebarOpen, setIsSidebarOpen] = React.useState(false);
  const [selectedAttachment, setSelectedAttachment] =
    React.useState<Attachment | null>(null);
  const toastTimeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(
    null
  );
  const [toastMessage, setToastMessage] = React.useState<string | null>(null);
  const [isWideLayout, setIsWideLayout] = React.useState(true);
  const [pinnedOrder, setPinnedOrder] = React.useState<string[]>([]);
  const [useDocs, setUseDocs] = React.useState<boolean>(true);
  const [mounted, setMounted] = React.useState(false);
  const [selectedModel, setSelectedModel] =
    React.useState<AIModel>("gpt-5-nano");

  const [conversations, setConversations] = React.useState<Conversation[]>(
    seedConversations
  );
  const [activeId, setActiveId] = React.useState(seedConversations[0].id);

  const createConversation = React.useCallback((): Conversation => {
    const now = Date.now();
    return {
      id: createId(),
      title: "New chat",
      attachments: [],
      messages: [
        {
          id: createId(),
          role: "assistant",
          content:
            "Tell me what you want to build, and I will help you map the next steps."
        }
      ],
      createdAt: now,
      lastUpdatedAt: now,
      isPinned: false,
      pinnedAt: null
    };
  }, []);

  const activeConversation = conversations.find(
    (conversation) => conversation.id === activeId
  );
  const pinnedConversations = React.useMemo(
    () => sortPinnedConversations(conversations, pinnedOrder),
    [conversations, pinnedOrder]
  );
  const unpinnedConversations = React.useMemo(
    () => sortUnpinnedConversations(conversations),
    [conversations]
  );

  const updateConversation = React.useCallback(
    (id: string, updater: (conversation: Conversation) => Conversation) => {
      setConversations((prev) =>
        prev.map((conversation) =>
          conversation.id === id ? updater(conversation) : conversation
        )
      );
    },
    []
  );

  const showToast = React.useCallback((message: string) => {
    setToastMessage(message);
    if (toastTimeoutRef.current) {
      clearTimeout(toastTimeoutRef.current);
    }
    toastTimeoutRef.current = setTimeout(() => {
      setToastMessage(null);
    }, 2200);
  }, []);

  const handleNewChat = () => {
    const newConversation = createConversation();

    setConversations((prev) => [newConversation, ...prev]);
    setActiveId(newConversation.id);
    setIsSidebarOpen(false);
  };

  const handleRenameConversation = (id: string, title: string) => {
    const nextTitle = title.trim();
    if (!nextTitle) return;
    updateConversation(id, (conversation) => ({
      ...conversation,
      title: nextTitle
    }));
  };

  const resolveAttachmentType = (name: string): Attachment["type"] => {
    const extension = name.split(".").pop()?.toLowerCase();
    switch (extension) {
      case "pdf":
        return "pdf";
      case "txt":
        return "txt";
      case "doc":
        return "doc";
      case "docx":
        return "docx";
      default:
        return "doc";
    }
  };

  const handleAttachFiles = (files: FileList) => {
    if (!activeConversation || files.length === 0) return;
    const newAttachments: Attachment[] = Array.from(files).map((file) => ({
      id: createId(),
      name: file.name,
      type: resolveAttachmentType(file.name),
      url: URL.createObjectURL(file)
    }));

    updateConversation(activeConversation.id, (conversation) => ({
      ...conversation,
      attachments: [...newAttachments, ...conversation.attachments]
    }));
  };

  const handleSendMessage = async (content: string, shouldUseDocs: boolean) => {
    if (!activeConversation) return;
    const trimmed = content.trim();
    if (!trimmed) return;
    const model = selectedModel;

    const conversationId = activeConversation.id;
    const now = Date.now();
    const userMessage: Message = {
      id: createId(),
      role: "user",
      content: trimmed,
      useDocs: shouldUseDocs
    };
    const assistantMessage: Message = {
      id: createId(),
      role: "assistant",
      content: "",
      isStreaming: true
    };

    updateConversation(conversationId, (conversation) => ({
      ...conversation,
      messages: [...conversation.messages, userMessage, assistantMessage],
      lastUpdatedAt: now
    }));

    for await (const chunk of mockStreamAssistantReply(trimmed, shouldUseDocs, model)) {
      updateConversation(conversationId, (conversation) => ({
        ...conversation,
        messages: conversation.messages.map((message) =>
          message.id === assistantMessage.id
            ? { ...message, content: `${message.content}${chunk}` }
            : message
        )
      }));
    }

    updateConversation(conversationId, (conversation) => ({
      ...conversation,
      messages: conversation.messages.map((message) =>
        message.id === assistantMessage.id
          ? { ...message, isStreaming: false }
          : message
      )
    }));
  };

  const handleSelectConversation = (id: string) => {
    setActiveId(id);
    setIsSidebarOpen(false);
  };

  const handleTogglePin = (id: string) => {
    const conversation = conversations.find((item) => item.id === id);
    if (!conversation) return;

    if (conversation.isPinned) {
      setPinnedOrder((prev) => prev.filter((item) => item !== id));
      updateConversation(id, (current) => ({
        ...current,
        isPinned: false,
        pinnedAt: null,
        lastUpdatedAt: Date.now()
      }));
      return;
    }

    const pinnedCount = conversations.filter((item) => item.isPinned).length;
    if (pinnedCount >= 5) {
      showToast("Max 5 pinned conversations");
      return;
    }

    const now = Date.now();
    setPinnedOrder((prev) => [id, ...prev.filter((item) => item !== id)]);
    updateConversation(id, (current) => ({
      ...current,
      isPinned: true,
      pinnedAt: now,
      lastUpdatedAt: now
    }));
  };

  const handleReorderPinned = (ids: string[]) => {
    setPinnedOrder(ids);
  };

  const handleDeleteConversation = (id: string) => {
    const nextPinnedOrder = pinnedOrder.filter((item) => item !== id);
    setPinnedOrder(nextPinnedOrder);
    setConversations((prev) => {
      const nextConversations = prev.filter(
        (conversation) => conversation.id !== id
      );
      if (activeId === id) {
        if (nextConversations.length === 0) {
          const freshConversation = createConversation();
          setActiveId(freshConversation.id);
          return [freshConversation];
        }

        const nextSorted = [
          ...sortPinnedConversations(nextConversations, nextPinnedOrder),
          ...sortUnpinnedConversations(nextConversations)
        ];
        setActiveId(nextSorted[0].id);
      }
      return nextConversations;
    });
  };

  const handleOpenAttachment = (attachment: Attachment) => {
    setSelectedAttachment(attachment);
    setIsSidebarOpen(false);
  };

  const handleCloseAttachment = () => {
    setSelectedAttachment(null);
    setIsSidebarOpen(false);
  };

  const isStreaming = Boolean(
    activeConversation?.messages.some((message) => message.isStreaming)
  );
  const isViewerOpen = Boolean(selectedAttachment);
  const viewerVariant = isWideLayout ? "sidebar" : "overlay";

  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        settingsRef.current &&
        !settingsRef.current.contains(event.target as Node)
      ) {
        setIsSettingsOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsSettingsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  React.useEffect(() => {
    if (!mounted) return;
    const stored = window.localStorage.getItem("pinnedOrder");
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          setPinnedOrder(parsed.filter((item) => typeof item === "string"));
        }
      } catch (error) {
        console.error("Failed to parse pinned order", error);
      }
    }
  }, [mounted]);

  React.useEffect(() => {
    if (!mounted) return;
    const stored = window.localStorage.getItem("useDocsPreference");
    if (stored === "true") {
      setUseDocs(true);
    } else if (stored === "false") {
      setUseDocs(false);
    }
  }, [mounted]);

  React.useEffect(() => {
    if (!mounted) return;
    const mediaQuery = window.matchMedia("(min-width: 900px)");
    const updateLayout = () => setIsWideLayout(mediaQuery.matches);
    updateLayout();
    mediaQuery.addEventListener("change", updateLayout);
    return () => {
      mediaQuery.removeEventListener("change", updateLayout);
    };
  }, []);

  React.useEffect(() => {
    if (!mounted) return;
    const stored = window.localStorage.getItem("preferredModel");
    if (stored === "gpt-5-nano" || stored === "Qwen3") {
      setSelectedModel(stored);
    }
  }, [mounted]);

  React.useEffect(() => {
    return () => {
      if (toastTimeoutRef.current) {
        clearTimeout(toastTimeoutRef.current);
      }
    };
  }, []);

  React.useEffect(() => {
    if (!mounted) return;
    window.localStorage.setItem("pinnedOrder", JSON.stringify(pinnedOrder));
  }, [pinnedOrder, mounted]);

  React.useEffect(() => {
    if (!mounted) return;
    window.localStorage.setItem("useDocsPreference", useDocs ? "true" : "false");
  }, [useDocs, mounted]);

  React.useEffect(() => {
    if (!mounted) return;
    window.localStorage.setItem("preferredModel", selectedModel);
  }, [selectedModel, mounted]);

  React.useEffect(() => {
    setPinnedOrder((prev) => {
      const pinnedIds = conversations
        .filter((conversation) => conversation.isPinned)
        .map((conversation) => conversation.id);
      const filtered = prev.filter((id) => pinnedIds.includes(id));
      const missing = pinnedIds.filter((id) => !filtered.includes(id));
      if (missing.length === 0 && filtered.length === prev.length) {
        return prev;
      }
      return [...filtered, ...missing];
    });
  }, [conversations]);

  const handleThemeSelect = (value: Theme) => {
    setTheme(value);
    setIsSettingsOpen(false);
  };

  return (
    <div className="relative flex h-full w-full min-w-0 overflow-hidden border border-border bg-panel/70 shadow-soft backdrop-blur">
      {toastMessage ? (
        <div className="pointer-events-none fixed left-1/2 top-4 z-[99] w-full max-w-md -translate-x-1/2 px-4">
          <div className="rounded-2xl border border-border bg-card/90 px-4 py-3 text-sm text-ink shadow-soft">
            {toastMessage}
          </div>
        </div>
      ) : null}
      {!isViewerOpen ? (
        <div className="hidden md:flex">
          <Sidebar
            pinnedConversations={pinnedConversations}
            conversations={unpinnedConversations}
            activeId={activeId}
            attachments={activeConversation?.attachments ?? []}
            selectedModel={selectedModel}
            onNewChat={handleNewChat}
            onSelectConversation={handleSelectConversation}
            onSelectAttachment={handleOpenAttachment}
            onTogglePin={handleTogglePin}
            onDeleteConversation={handleDeleteConversation}
            onReorderPinned={handleReorderPinned}
            onSelectModel={setSelectedModel}
          />
        </div>
      ) : null}
      {isSidebarOpen && !isViewerOpen ? (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-ink/40"
            aria-label="Close sidebar"
            onClick={() => setIsSidebarOpen(false)}
          />
          <div className="relative z-10 h-full">
            <Sidebar
              pinnedConversations={pinnedConversations}
              conversations={unpinnedConversations}
              activeId={activeId}
              attachments={activeConversation?.attachments ?? []}
              selectedModel={selectedModel}
              onNewChat={handleNewChat}
              onSelectConversation={handleSelectConversation}
              onSelectAttachment={handleOpenAttachment}
              onTogglePin={handleTogglePin}
              onDeleteConversation={handleDeleteConversation}
              onReorderPinned={handleReorderPinned}
              onSelectModel={setSelectedModel}
            />
          </div>
        </div>
      ) : null}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between gap-4 border-b border-border bg-panel/90 px-6 py-4">
          <div className="flex items-center gap-3">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Toggle sidebar"
              onClick={() => setIsSidebarOpen((prev) => !prev)}
              className="h-10 w-10 rounded-2xl border border-border bg-card/80 text-ink shadow-glow hover:bg-accent/50 md:hidden"
            >
              {isSidebarOpen ? (
                <X className="h-5 w-5" />
              ) : (
                <PanelLeft className="h-5 w-5" />
              )}
            </Button>
            {activeConversation ? (
              <TitleEditor
                title={activeConversation.title}
                onRename={(title) =>
                  handleRenameConversation(activeConversation.id, title)
                }
              />
            ) : (
              <div className="text-lg font-semibold">
                No conversation selected
              </div>
            )}
          </div>
          <div className="relative z-10" ref={settingsRef}>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Open settings"
              aria-expanded={isSettingsOpen}
              onClick={() => setIsSettingsOpen((prev) => !prev)}
              className="h-10 w-10 rounded-2xl border border-border bg-card/80 text-ink shadow-glow hover:bg-accent/50"
            >
              <Settings className="h-5 w-5" />
            </Button>
            {isSettingsOpen ? (
              <div className="absolute right-0 mt-2 w-56 rounded-2xl border border-border bg-card p-3 shadow-soft">
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted">
                  Theme
                </div>
                <div className="mt-2 space-y-2">
                  {["light", "dark"].map((option) => (
                    <button
                      key={option}
                      type="button"
                      onClick={() => handleThemeSelect(option as Theme)}
                      className={cn(
                        "flex w-full items-center justify-between rounded-xl border px-3 py-2 text-sm transition",
                        theme === option
                          ? "border-accent-strong bg-accent/40 text-ink shadow-glow"
                          : "border-border bg-panel/60 text-muted hover:bg-accent/30 hover:text-ink"
                      )}
                      aria-pressed={theme === option}
                    >
                      <span className="flex items-center gap-2 text-ink">
                        {option === "light" ? (
                          <Sun className="h-4 w-4" />
                        ) : (
                          <Moon className="h-4 w-4" />
                        )}
                        {option === "light" ? "Light" : "Dark"}
                      </span>
                      <span
                        className={cn(
                          "h-2 w-2 rounded-full",
                          theme === option
                            ? "bg-accent-strong"
                            : "bg-border"
                        )}
                        aria-hidden
                      />
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </header>
        <ChatThread messages={activeConversation?.messages ?? []} />
        <Composer
          disabled={!activeConversation}
          isStreaming={isStreaming}
          onAttachFiles={handleAttachFiles}
          onSendMessage={handleSendMessage}
          useDocs={useDocs}
          onToggleUseDocs={setUseDocs}
        />
      </div>
      {selectedAttachment ? (
        <AttachmentViewer
          attachment={selectedAttachment}
          attachments={activeConversation?.attachments ?? []}
          onClose={handleCloseAttachment}
          onSelectAttachment={handleOpenAttachment}
          variant={viewerVariant}
          className={isViewerOpen ? "" : "hidden"}
        />
      ) : null}
    </div>
  );
}
