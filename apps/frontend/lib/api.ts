import { apiBaseUrl } from "@/lib/config";

const API_BASE_URL = apiBaseUrl.replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  details?: unknown;

  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

type Json = Record<string, unknown>;

const buildUrl = (path: string) =>
  API_BASE_URL ? `${API_BASE_URL}${path}` : path;

const withDefaults = (init?: RequestInit): RequestInit => ({
  credentials: "include",
  ...init
});

const parseError = async (response: Response) => {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      const data = await response.json();
      const message =
        typeof data?.detail === "string"
          ? data.detail
          : typeof data?.message === "string"
            ? data.message
            : response.statusText;
      return { message, details: data };
    } catch {
      return { message: response.statusText, details: null };
    }
  }
  try {
    const text = await response.text();
    return { message: text || response.statusText, details: text };
  } catch {
    return { message: response.statusText, details: null };
  }
};

const requestJson = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(buildUrl(path), withDefaults(init));
  if (!response.ok) {
    const { message, details } = await parseError(response);
    throw new ApiError(message, response.status, details);
  }
  if (response.status === 204) {
    return null as T;
  }
  return response.json() as Promise<T>;
};

export const getJson = <T>(path: string, init?: RequestInit) =>
  requestJson<T>(path, { ...init, method: "GET" });

export const postJson = <T>(path: string, body?: Json, init?: RequestInit) =>
  requestJson<T>(path, {
    ...init,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    body: body ? JSON.stringify(body) : undefined
  });

export const patchJson = <T>(path: string, body?: Json, init?: RequestInit) =>
  requestJson<T>(path, {
    ...init,
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    body: body ? JSON.stringify(body) : undefined
  });

export const putJson = <T>(path: string, body?: Json, init?: RequestInit) =>
  requestJson<T>(path, {
    ...init,
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    body: body ? JSON.stringify(body) : undefined
  });

export const deleteJson = <T>(path: string, init?: RequestInit) =>
  requestJson<T>(path, { ...init, method: "DELETE" });

export const uploadFile = async <T>(
  path: string,
  file: File,
  init?: RequestInit
) => {
  const formData = new FormData();
  formData.append("file", file);
  return requestJson<T>(path, {
    ...init,
    method: "POST",
    body: formData
  });
};

export const getText = async (path: string, init?: RequestInit) => {
  const response = await fetch(buildUrl(path), withDefaults(init));
  if (!response.ok) {
    const { message, details } = await parseError(response);
    throw new ApiError(message, response.status, details);
  }
  return response.text();
};

export const getArrayBuffer = async (path: string, init?: RequestInit) => {
  const response = await fetch(buildUrl(path), withDefaults(init));
  if (!response.ok) {
    const { message, details } = await parseError(response);
    throw new ApiError(message, response.status, details);
  }
  return response.arrayBuffer();
};

export type SSEvent<T = unknown> = {
  event: string;
  data: T;
};

export async function* streamSSE<T>(
  path: string,
  body?: Json,
  init?: RequestInit
): AsyncGenerator<SSEvent<T>> {
  const response = await fetch(
    buildUrl(path),
    withDefaults({
      ...init,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {})
      },
      body: body ? JSON.stringify(body) : undefined
    })
  );

  if (!response.ok) {
    const { message, details } = await parseError(response);
    throw new ApiError(message, response.status, details);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new ApiError("Streaming response not supported.", 500);
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      const lines = chunk.split("\n");
      let eventName = "message";
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        }
      }
      const dataString = dataLines.join("\n");
      let payload: T | string = dataString;
      if (dataString) {
        try {
          payload = JSON.parse(dataString) as T;
        } catch {
          payload = dataString;
        }
      }
      yield { event: eventName, data: payload as T };
    }
  }
}

export const attachmentContentUrl = (id: string | number) =>
  buildUrl(`/attachments/${id}/content`);
