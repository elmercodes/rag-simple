"use client";

import * as React from "react";
import Sidebar from "@/components/chat/sidebar";
import ChatThread from "@/components/chat/chat-thread";
import Composer from "@/components/chat/composer";
import TitleEditor from "@/components/chat/title-editor";
import AttachmentViewer from "@/components/chat/attachment-viewer";
import { Button } from "@/components/ui/button";
import { useTheme, type Theme } from "@/components/theme-provider";
import { Settings, Moon, Sun, PanelLeft, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  ApiError,
  attachmentContentUrl,
  deleteJson,
  getJson,
  patchJson,
  postJson,
  putJson,
  streamSSE,
  uploadFile
} from "@/lib/api";

export type Message = {
  id?: string;
  role: "user" | "assistant";
  content: string;
  createdAt?: string;
  isStreaming?: boolean;
  useDocs?: boolean;
  citations?: BackendMessage["citations"];
  evidence?: BackendMessage["evidence"];
  meta?: BackendMessage["meta"];
  warning?: string;
};

export type Attachment = {
  id: string;
  name: string;
  type: "pdf" | "txt" | "doc" | "docx";
  url: string;
  createdAt?: string;
};

export type AIModel = "gpt-5-nano" | "Qwen3";

export type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  attachments: Attachment[];
  createdAt: string;
  lastUpdatedAt: string;
  isPinned: boolean;
  pinnedAt: string | null;
  pinnedOrder: number | null;
};

type ConversationPayload = Omit<Conversation, "messages" | "attachments">;

type BackendConversation = Omit<ConversationPayload, "id"> & {
  id: number;
};

type BackendMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  useDocs?: boolean;
  citations?: Array<{ attachmentId: number | string; page?: number | null }>;
  evidence?: Array<{
    attachmentId: number | string;
    page?: number | null;
    excerpt?: string | null;
    filename?: string | null;
    rank?: number;
  }>;
  meta?: {
    answerMode?: "rag" | "direct" | string;
    verdict?: "SUPPORTED" | "PARTIAL" | "UNSUPPORTED" | string | null;
    confidence?: number | null;
    warning?: string | null;
  };
  warning?: string;
};

type BackendAttachment = {
  id: number;
  name: string;
  type: string | null;
  createdAt?: string;
};

const timestamp = (value?: string | null) =>
  value ? Date.parse(value) : 0;

const normalizeConversation = (
  payload: BackendConversation,
  current?: Conversation
): Conversation => ({
  id: String(payload.id),
  title: payload.title,
  createdAt: payload.createdAt,
  lastUpdatedAt: payload.lastUpdatedAt,
  isPinned: payload.isPinned,
  pinnedAt: payload.pinnedAt ?? null,
  pinnedOrder:
    typeof payload.pinnedOrder === "number" ? payload.pinnedOrder : null,
  messages: current?.messages ?? [],
  attachments: current?.attachments ?? []
});

const normalizeMessage = (payload: BackendMessage): Message => ({
  id: payload.id,
  role: payload.role,
  content: payload.content,
  createdAt: payload.createdAt,
  useDocs: payload.useDocs,
  citations: payload.citations ?? [],
  evidence: payload.evidence ?? [],
  meta: payload.meta ?? {},
  warning: payload.warning
});

const normalizeAttachment = (payload: BackendAttachment): Attachment => {
  const rawType = (payload.type || "").toLowerCase();
  const type =
    rawType === "pdf" ||
    rawType === "txt" ||
    rawType === "doc" ||
    rawType === "docx"
      ? rawType
      : "doc";
  return {
    id: String(payload.id),
    name: payload.name,
    type,
    url: attachmentContentUrl(payload.id),
    createdAt: payload.createdAt
  };
};

const sortPinnedConversations = (list: Conversation[]) =>
  [...list]
    .filter((conversation) => conversation.isPinned)
    .sort((a, b) => {
      const aOrder = a.pinnedOrder ?? Number.MAX_SAFE_INTEGER;
      const bOrder = b.pinnedOrder ?? Number.MAX_SAFE_INTEGER;
      if (aOrder !== bOrder) return aOrder - bOrder;
      return timestamp(b.pinnedAt) - timestamp(a.pinnedAt);
    });

const sortUnpinnedConversations = (list: Conversation[]) =>
  [...list]
    .filter((conversation) => !conversation.isPinned)
    .sort((a, b) => {
      const lastUpdated = timestamp(b.lastUpdatedAt) - timestamp(a.lastUpdatedAt);
      if (lastUpdated !== 0) return lastUpdated;
      return timestamp(b.createdAt) - timestamp(a.createdAt);
    });

export default function ChatApp() {
  const streamingEnabled =
    process.env.NEXT_PUBLIC_STREAMING_ENABLED !== "false";
  const { theme, setTheme } = useTheme();
  const [isSettingsOpen, setIsSettingsOpen] = React.useState(false);
  const settingsRef = React.useRef<HTMLDivElement>(null);
  const [isSidebarOpen, setIsSidebarOpen] = React.useState(false);
  const [selectedAttachment, setSelectedAttachment] =
    React.useState<Attachment | null>(null);
  const toastTimeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(
    null
  );
  const apiErrorTimeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(
    null
  );
  const [toastMessage, setToastMessage] = React.useState<string | null>(null);
  const [lastApiError, setLastApiError] = React.useState<string | null>(null);
  const [initialLoadFailed, setInitialLoadFailed] = React.useState(false);
  const [isWideLayout, setIsWideLayout] = React.useState(true);
  const [mounted, setMounted] = React.useState(false);
  const [selectedModel, setSelectedModel] =
    React.useState<AIModel>("gpt-5-nano");
  const [useDocsDefaults, setUseDocsDefaults] = React.useState(true);

  const [conversations, setConversations] = React.useState<Conversation[]>([]);
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const [useDocsByConversation, setUseDocsByConversation] = React.useState<
    Record<string, boolean>
  >({});
  const [streamingByConversation, setStreamingByConversation] = React.useState<
    Record<string, { content: string }>
  >({});
  const [uploadingByConversation, setUploadingByConversation] = React.useState<
    Record<string, boolean>
  >({});
  const attachmentCountRef = React.useRef<Record<string, number>>({});
  const abortControllersRef = React.useRef<Record<string, AbortController>>({});
  const abortRequestedRef = React.useRef<Record<string, boolean>>({});

  const activeConversation = conversations.find(
    (conversation) => conversation.id === activeId
  );
  const pinnedConversations = React.useMemo(
    () => sortPinnedConversations(conversations),
    [conversations]
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

  const reportApiError = React.useCallback((context: string, error: unknown) => {
    if (process.env.NODE_ENV === "production") return;
    const setApiError = (message: string) => {
      setLastApiError(message);
      if (apiErrorTimeoutRef.current) {
        clearTimeout(apiErrorTimeoutRef.current);
      }
      apiErrorTimeoutRef.current = setTimeout(() => {
        setLastApiError(null);
      }, 8000);
    };

    if (error instanceof ApiError) {
      const detail =
        typeof error.details === "string"
          ? error.details
          : JSON.stringify(error.details ?? {});
      console.error(`[API] ${context}`, {
        status: error.status,
        message: error.message,
        detail
      });
      setApiError(
        `${context}: ${error.status} ${error.message}${detail ? ` — ${detail}` : ""}`
      );
      return;
    }
    console.error(`[API] ${context}`, error);
    setApiError(`${context}: ${String(error)}`);
  }, []);

  const syncConversations = React.useCallback(
    (payload: BackendConversation[]) => {
      setConversations((prev) => {
        const prevMap = new Map(prev.map((conv) => [conv.id, conv]));
        return payload.map((item) =>
          normalizeConversation(item, prevMap.get(String(item.id)))
        );
      });
      if (!activeId && payload.length > 0) {
        setActiveId(String(payload[0].id));
      }
    },
    [activeId]
  );

  const refreshConversations = React.useCallback(async () => {
    try {
      const data = await getJson<BackendConversation[]>("/conversations");
      syncConversations(data);
      return data;
    } catch (error) {
      reportApiError("GET /conversations", error);
      throw error;
    }
  }, [reportApiError, syncConversations]);

  const loadMessages = React.useCallback(async (conversationId: string) => {
    try {
      const data = await getJson<BackendMessage[]>(
        `/conversations/${conversationId}/messages`
      );
      updateConversation(conversationId, (conversation) => ({
        ...conversation,
        messages: data.map(normalizeMessage)
      }));
      return data;
    } catch (error) {
      reportApiError(
        `GET /conversations/${conversationId}/messages`,
        error
      );
      throw error;
    }
  }, [reportApiError, updateConversation]);

  const loadAttachments = React.useCallback(async (conversationId: string) => {
    try {
      const data = await getJson<BackendAttachment[]>(
        `/conversations/${conversationId}/attachments`
      );
      updateConversation(conversationId, (conversation) => ({
        ...conversation,
        attachments: data.map(normalizeAttachment)
      }));
      return data;
    } catch (error) {
      reportApiError(
        `GET /conversations/${conversationId}/attachments`,
        error
      );
      throw error;
    }
  }, [reportApiError, updateConversation]);

  const handleNewChat = React.useCallback(async () => {
    try {
      const data = await postJson<BackendConversation>("/conversations");
      const newConversation = normalizeConversation(data);
      setConversations((prev) => [newConversation, ...prev]);
      setActiveId(newConversation.id);
      await Promise.all([
        loadMessages(newConversation.id),
        loadAttachments(newConversation.id)
      ]);
      setIsSidebarOpen(false);
    } catch (error) {
      reportApiError("POST /conversations", error);
      showToast("Unable to create a new conversation.");
      console.error(error);
    }
  }, [loadAttachments, loadMessages, reportApiError, showToast]);

  const handleRetryLoad = React.useCallback(async () => {
    setInitialLoadFailed(false);
    try {
      const data = await refreshConversations();
      if (data.length === 0) {
        await handleNewChat();
      }
    } catch (error) {
      setInitialLoadFailed(true);
      showToast("Backend unreachable. Check NEXT_PUBLIC_API_BASE_URL.");
      console.error(error);
    }
  }, [handleNewChat, refreshConversations, showToast]);

  const handleRenameConversation = async (id: string, title: string) => {
    const nextTitle = title.trim();
    if (!nextTitle) return;
    const previous = conversations.find((item) => item.id === id);
    if (!previous) return;

    updateConversation(id, (conversation) => ({
      ...conversation,
      title: nextTitle
    }));

    try {
      const data = await patchJson<BackendConversation>(`/conversations/${id}`,
        { title: nextTitle }
      );
      updateConversation(id, (conversation) =>
        normalizeConversation(data, conversation)
      );
    } catch (error) {
      updateConversation(id, () => previous);
      showToast("Failed to rename conversation.");
      console.error(error);
    }
  };

  const handleAttachFiles = async (files: FileList) => {
    if (!activeConversation || files.length === 0) return;
    const conversationId = activeConversation.id;
    setUploadingByConversation((prev) => ({
      ...prev,
      [conversationId]: true
    }));

    const uploads = Array.from(files).map(async (file) => {
      try {
        const data = await uploadFile<BackendAttachment>(
          `/conversations/${conversationId}/attachments`,
          file
        );
        const attachment = normalizeAttachment(data);
        updateConversation(conversationId, (conversation) => {
          const exists = conversation.attachments.some(
            (item) => item.id === attachment.id
          );
          const attachments = exists
            ? conversation.attachments
            : [attachment, ...conversation.attachments];
          return {
            ...conversation,
            attachments,
            lastUpdatedAt: new Date().toISOString()
          };
        });
      } catch (error) {
        if (error instanceof ApiError && error.status === 400) {
          showToast(error.message || "Attachment limit reached.");
        } else {
          showToast("Unable to upload attachment.");
        }
        console.error(error);
      }
    });

    try {
      await Promise.all(uploads);
    } finally {
      setUploadingByConversation((prev) => ({
        ...prev,
        [conversationId]: false
      }));
    }
  };

  const handleSendMessageNonStreaming = React.useCallback(
    async (conversationId: string, content: string, shouldUseDocs: boolean) => {
      try {
        const response = await postJson<{
          messages: BackendMessage[];
          warning?: string;
        }>(`/conversations/${conversationId}/messages`, {
          content,
          useDocs: shouldUseDocs
        });

        if (response.warning) {
          showToast(response.warning);
        }
        return response.messages.map(normalizeMessage);
      } catch (error) {
        reportApiError(
          `POST /conversations/${conversationId}/messages`,
          error
        );
        throw error;
      }
    },
    [reportApiError, showToast]
  );

  const handleSendMessage = async (content: string, shouldUseDocs: boolean) => {
    if (!activeConversation) return;
    const trimmed = content.trim();
    if (!trimmed) return;

    const conversationId = activeConversation.id;
    const previousMessageCount = activeConversation.messages.length;
    const optimisticUserMessage: Message = {
      id: `tmp-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`}`,
      role: "user",
      content: trimmed,
      createdAt: new Date().toISOString()
    };

    updateConversation(conversationId, (conversation) => ({
      ...conversation,
      messages: [...conversation.messages, optimisticUserMessage],
      lastUpdatedAt: new Date().toISOString()
    }));

    setStreamingByConversation((prev) => ({
      ...prev,
      [conversationId]: { content: "" }
    }));

    if (!streamingEnabled) {
      try {
        await handleSendMessageNonStreaming(
          conversationId,
          trimmed,
          shouldUseDocs
        );
        await loadMessages(conversationId);
      } catch (error) {
        showToast("Unable to send message.");
        console.error(error);
      } finally {
        setStreamingByConversation((prev) => {
          const next = { ...prev };
          delete next[conversationId];
          return next;
        });
      }
      return;
    }

    abortRequestedRef.current[conversationId] = false;
    const controller = new AbortController();
    abortControllersRef.current[conversationId] = controller;

    const stream = streamSSE<
      { delta?: string; message?: string; status?: string } | BackendMessage
    >(
      `/conversations/${conversationId}/messages:stream`,
      {
        content: trimmed,
        useDocs: shouldUseDocs
      },
      { signal: controller.signal }
    );

    let hadStreamError = false;
    let finalReceived = false;
    let wasAborted = false;

    try {
      for await (const event of stream) {
        if (abortRequestedRef.current[conversationId]) {
          wasAborted = true;
          break;
        }
        if (event.event === "message.status") {
          setStreamingByConversation((prev) => {
            const current = prev[conversationId];
            if (current && current.content.length > 0) {
              return prev;
            }
            return {
              ...prev,
              [conversationId]: { content: "" }
            };
          });
        }
        if (event.event === "message.delta" && "delta" in event.data) {
          const delta = event.data.delta ?? "";
          setStreamingByConversation((prev) => {
            const current = prev[conversationId] ?? { content: "" };
            return {
              ...prev,
              [conversationId]: { content: `${current.content}${delta}` }
            };
          });
        }
        if (event.event === "message.final") {
          const finalPayload = event.data as BackendMessage & { warning?: string };
          const finalMessage = normalizeMessage(finalPayload);
          updateConversation(conversationId, (conversation) => ({
            ...conversation,
            messages: [...conversation.messages, finalMessage]
          }));
          if (finalPayload.warning) {
            showToast(finalPayload.warning);
          }
          setStreamingByConversation((prev) => {
            const next = { ...prev };
            delete next[conversationId];
            return next;
          });
          finalReceived = true;
        }
        if (event.event === "error") {
          hadStreamError = true;
          const message =
            typeof (event.data as { message?: string })?.message === "string"
              ? (event.data as { message: string }).message
              : "Streaming error.";
          throw new Error(message);
        }
      }
    } catch (error) {
      const isAbort =
        error instanceof DOMException && error.name === "AbortError";
      wasAborted = isAbort;
      hadStreamError = !isAbort;
      setStreamingByConversation((prev) => {
        const next = { ...prev };
        delete next[conversationId];
        return next;
      });
      if (!isAbort) {
        showToast("Streaming failed.");
        console.error(error);
      }
    }

    if (!finalReceived) {
      setStreamingByConversation((prev) => {
        const next = { ...prev };
        delete next[conversationId];
        return next;
      });
    }

    delete abortControllersRef.current[conversationId];
    delete abortRequestedRef.current[conversationId];

    if (wasAborted) {
      return;
    }

    if (hadStreamError) {
      try {
        const latest = await getJson<BackendMessage[]>(
          `/conversations/${conversationId}/messages`
        );
        updateConversation(conversationId, (conversation) => ({
          ...conversation,
          messages: latest.map(normalizeMessage)
        }));
        if (latest.length <= previousMessageCount) {
          await handleSendMessageNonStreaming(
            conversationId,
            trimmed,
            shouldUseDocs
          );
          await loadMessages(conversationId);
        }
      } catch (error) {
        showToast("Unable to send message.");
        console.error(error);
      }
    } else {
      await loadMessages(conversationId);
    }
  };

  const handleStopStreaming = React.useCallback(() => {
    if (!activeConversation) return;
    const conversationId = activeConversation.id;
    abortRequestedRef.current[conversationId] = true;

    const partial = streamingByConversation[conversationId]?.content ?? "";
    if (partial.trim()) {
      updateConversation(conversationId, (conversation) => ({
        ...conversation,
        messages: [
          ...conversation.messages,
          {
            id: `tmp-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`}`,
            role: "assistant",
            content: partial,
            createdAt: new Date().toISOString()
          }
        ]
      }));
    }

    const controller = abortControllersRef.current[conversationId];
    if (controller) {
      controller.abort();
      delete abortControllersRef.current[conversationId];
    }

    setStreamingByConversation((prev) => {
      const next = { ...prev };
      delete next[conversationId];
      return next;
    });
  }, [activeConversation, streamingByConversation, updateConversation]);

  const handleSelectConversation = (id: string) => {
    setActiveId(id);
    setSelectedAttachment(null);
    setIsSidebarOpen(false);
  };

  const handleTogglePin = async (id: string) => {
    const conversation = conversations.find((item) => item.id === id);
    if (!conversation) return;
    const nextPinned = !conversation.isPinned;
    const previous = conversation;

    updateConversation(id, (current) => ({
      ...current,
      isPinned: nextPinned,
      pinnedAt: nextPinned ? new Date().toISOString() : null
    }));

    try {
      const data = await patchJson<BackendConversation>(`/conversations/${id}`,
        { isPinned: nextPinned }
      );
      updateConversation(id, (current) =>
        normalizeConversation(data, current)
      );
    } catch (error) {
      updateConversation(id, () => previous);
      if (error instanceof ApiError && error.status === 400) {
        showToast("Max 5 pinned conversations");
      } else {
        showToast("Unable to update pin.");
      }
      console.error(error);
    }
  };

  const handleReorderPinned = async (ids: string[]) => {
    const previous = conversations;
    setConversations((prev) =>
      prev.map((conversation) => {
        const index = ids.indexOf(conversation.id);
        if (index === -1) {
          return conversation.isPinned
            ? { ...conversation, pinnedOrder: null }
            : conversation;
        }
        return {
          ...conversation,
          isPinned: true,
          pinnedOrder: index + 1
        };
      })
    );

    try {
      await putJson<{ status: string }>("/conversations/pinned-order", {
        ids
      });
    } catch (error) {
      setConversations(previous);
      showToast("Unable to reorder pinned conversations.");
      console.error(error);
    }
  };

  const handleDeleteConversation = async (id: string) => {
    try {
      await deleteJson<{ status: string }>(`/conversations/${id}`);
    } catch (error) {
      showToast("Unable to delete conversation.");
      console.error(error);
      return;
    }

    setConversations((prev) => prev.filter((conversation) => conversation.id !== id));

    if (activeId === id) {
      const remaining = conversations.filter((conversation) => conversation.id !== id);
      if (remaining.length === 0) {
        await handleNewChat();
        return;
      }
      const nextSorted = [
        ...sortPinnedConversations(remaining),
        ...sortUnpinnedConversations(remaining)
      ];
      setActiveId(nextSorted[0].id);
    }
  };

  const handleOpenAttachment = (attachment: Attachment) => {
    setSelectedAttachment(attachment);
    setIsSidebarOpen(false);
  };

  const handleCloseAttachment = () => {
    setSelectedAttachment(null);
    setIsSidebarOpen(false);
  };

  const useDocsEnabled = (activeConversation?.attachments.length ?? 0) > 0;
  const resolvedUseDocs = activeConversation
    ? useDocsByConversation[activeConversation.id] ??
      (useDocsEnabled ? useDocsDefaults : false)
    : false;

  const isStreaming = Boolean(
    activeConversation && streamingByConversation[activeConversation.id]
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
    const mediaQuery = window.matchMedia("(min-width: 900px)");
    const updateLayout = () => setIsWideLayout(mediaQuery.matches);
    updateLayout();
    mediaQuery.addEventListener("change", updateLayout);
    return () => {
      mediaQuery.removeEventListener("change", updateLayout);
    };
  }, [mounted]);

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
      if (apiErrorTimeoutRef.current) {
        clearTimeout(apiErrorTimeoutRef.current);
      }
    };
  }, []);

  React.useEffect(() => {
    if (!mounted) return;
    window.localStorage.setItem("preferredModel", selectedModel);
  }, [selectedModel, mounted]);

  React.useEffect(() => {
    if (!activeId) return;
    let isActive = true;
    const load = async () => {
      try {
        await Promise.all([loadMessages(activeId), loadAttachments(activeId)]);
      } catch (error) {
        if (isActive) {
          showToast("Unable to load conversation details.");
        }
        console.error(error);
      }
    };

    load();

    return () => {
      isActive = false;
    };
  }, [activeId, loadAttachments, loadMessages, showToast]);

  React.useEffect(() => {
    if (!activeConversation) return;
    const id = activeConversation.id;
    const count = activeConversation.attachments.length;
    const previous = attachmentCountRef.current[id];
    attachmentCountRef.current[id] = count;

    setUseDocsByConversation((prev) => {
      const current = prev[id];
      if (count === 0) {
        if (current === false) return prev;
        return { ...prev, [id]: false };
      }
      if (previous === undefined) {
        if (current !== undefined) return prev;
        return { ...prev, [id]: useDocsDefaults };
      }
      if (previous === 0 && count > 0) {
        if (current === true) return prev;
        return { ...prev, [id]: true };
      }
      return prev;
    });
  }, [activeConversation, useDocsDefaults]);

  React.useEffect(() => {
    if (!mounted) return;
    let isActive = true;
    const load = async () => {
      try {
        const settings = await getJson<{ theme: Theme | null; useDocs: boolean }>(
          "/settings"
        );
        if (!isActive) return;
        if (settings.theme === "light" || settings.theme === "dark") {
          setTheme(settings.theme);
        }
        setUseDocsDefaults(Boolean(settings.useDocs));
      } catch (error) {
        console.error(error);
      }

      try {
        const data = await refreshConversations();
        if (!isActive) return;
        if (data.length === 0) {
          await handleNewChat();
        }
        setInitialLoadFailed(false);
      } catch (error) {
        showToast("Backend unreachable. Check NEXT_PUBLIC_API_BASE_URL.");
        setInitialLoadFailed(true);
        console.error(error);
      }
    };

    load();

    return () => {
      isActive = false;
    };
  }, [handleNewChat, mounted, refreshConversations, setTheme, showToast]);

  const handleThemeSelect = async (value: Theme) => {
    setTheme(value);
    setIsSettingsOpen(false);
    try {
      await patchJson<{ theme: Theme | null; useDocs: boolean }>("/settings", {
        theme: value
      });
    } catch (error) {
      console.error(error);
    }
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
      {process.env.NODE_ENV !== "production" && lastApiError ? (
        <div className="fixed left-4 top-4 z-[98] max-w-lg rounded-2xl border border-border bg-card/90 px-4 py-3 pr-10 text-xs text-ink shadow-soft">
          <div className="flex items-start justify-between gap-4">
            <span>API: {lastApiError}</span>
            <button
              type="button"
              className="flex h-6 w-6 items-center justify-center rounded-full border border-border text-muted transition hover:bg-accent/40 hover:text-ink"
              aria-label="Dismiss API error"
              onClick={() => {
                setLastApiError(null);
                if (apiErrorTimeoutRef.current) {
                  clearTimeout(apiErrorTimeoutRef.current);
                }
              }}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      ) : null}
      {!isViewerOpen ? (
        <div className="hidden md:flex">
          <Sidebar
            pinnedConversations={pinnedConversations}
            conversations={unpinnedConversations}
            activeId={activeId ?? ""}
            attachments={activeConversation?.attachments ?? []}
            isUploadingAttachments={
              activeConversation
                ? Boolean(uploadingByConversation[activeConversation.id])
                : false
            }
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
              activeId={activeId ?? ""}
              attachments={activeConversation?.attachments ?? []}
              isUploadingAttachments={
                activeConversation
                  ? Boolean(uploadingByConversation[activeConversation.id])
                  : false
              }
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
        <ChatThread
          messages={activeConversation?.messages ?? []}
          streamingMessage={
            activeConversation && streamingByConversation[activeConversation.id]
              ? {
                  role: "assistant",
                  content: streamingByConversation[activeConversation.id].content,
                  isStreaming: true
                }
              : null
          }
        />
        {initialLoadFailed && !activeConversation ? (
          <div className="mx-6 mb-4 rounded-2xl border border-border bg-card/80 p-4 text-sm text-ink shadow-soft">
            <div className="font-semibold">
              Backend unreachable. Check NEXT_PUBLIC_API_BASE_URL.
            </div>
            <div className="mt-2 text-xs text-muted">
              You can retry once the backend is running.
            </div>
            <div className="mt-3">
              <Button type="button" onClick={handleRetryLoad}>
                Retry connection
              </Button>
            </div>
          </div>
        ) : null}
        <Composer
          disabled={!activeConversation}
          isStreaming={isStreaming}
          onStop={handleStopStreaming}
          isUploadingAttachments={
            activeConversation
              ? Boolean(uploadingByConversation[activeConversation.id])
              : false
          }
          onAttachFiles={handleAttachFiles}
          onSendMessage={handleSendMessage}
          useDocs={resolvedUseDocs}
          onToggleUseDocs={(value) => {
            if (!activeConversation || !useDocsEnabled) return;
            setUseDocsByConversation((prev) => ({
              ...prev,
              [activeConversation.id]: value
            }));
          }}
          useDocsEnabled={useDocsEnabled}
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
