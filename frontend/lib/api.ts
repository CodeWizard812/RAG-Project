// frontend/lib/api.ts

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

// ── Token management ──────────────────────────────────────────────────────────

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("rag_access_token");
}

export function setToken(token: string): void {
  localStorage.setItem("rag_access_token", token);
}

export function clearToken(): void {
  localStorage.removeItem("rag_access_token");
}

// ── Username persistence ──────────────────────────────────────────────────────
// Stored on login so we can namespace session storage per user.
// Never used for auth — the JWT token is the sole auth credential.

export function setStoredUsername(username: string): void {
  localStorage.setItem("rag_username", username);
}

export function getStoredUsername(): string {
  return localStorage.getItem("rag_username") ?? "default";
}

export function clearStoredUsername(): void {
  localStorage.removeItem("rag_username");
}

// ── Session storage — namespaced per user ─────────────────────────────────────
// Key format: rag_sessions:{username}
// This prevents User B from seeing User A's sessions when sharing a browser.

function sessionStoreKey(): string {
  return `rag_sessions:${getStoredUsername()}`;
}

export function loadStoredSessions(): Array<{ id: string; label: string }> {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(sessionStoreKey());
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveStoredSessions(
  sessions: Array<{ id: string; label: string }>,
): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(sessionStoreKey(), JSON.stringify(sessions));
  } catch {
    // localStorage quota exceeded — fail silently
  }
}

export function clearStoredSessions(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(sessionStoreKey());
  } catch {
    // ignore
  }
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(
  username: string,
  password: string,
): Promise<{ access: string; refresh: string }> {
  const res = await fetch(`${BASE}/api/auth/token/`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error("Invalid credentials");
  const data = await res.json();
  // Persist username immediately so session namespace is set before
  // any session storage calls happen in the chat page
  setStoredUsername(username);
  return data;
}

export async function register(
  username: string,
  password: string,
  email:    string,
): Promise<void> {
  const res = await fetch(`${BASE}/api/auth/register/`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ username, password, email }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
}

// ── Health ────────────────────────────────────────────────────────────────────

export async function fetchHealth(): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/api/health/`);
  return res.json();
}

// ── Session management ────────────────────────────────────────────────────────

export async function clearSession(sessionId: string): Promise<void> {
  const token = getToken();
  await fetch(`${BASE}/api/chat/clear/`, {
    method:  "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization:  `Bearer ${token}`,
    },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function fetchSessionHistory(
  sessionId: string,
): Promise<Array<{ role: "human" | "ai"; content: string }>> {
  const token = getToken();
  const res   = await fetch(
    `${BASE}/api/chat/history/?session_id=${encodeURIComponent(sessionId)}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!res.ok) return [];
  const data = await res.json();
  return data.messages ?? [];
}

// ── Streaming chat ────────────────────────────────────────────────────────────

export async function* streamChat(
  question:  string,
  sessionId: string,
  modelType: string,
): AsyncGenerator<Record<string, unknown>> {
  const token = getToken();

  const res = await fetch(`${BASE}/api/chat/stream/`, {
    method:  "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization:  `Bearer ${token}`,
    },
    body: JSON.stringify({
      question,
      session_id: sessionId,
      model_type: modelType,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `HTTP ${res.status}`);
  }

  const reader  = res.body!.getReader();
  const decoder = new TextDecoder();
  let   buffer  = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const json = line.slice(5).trim();
      if (!json) continue;
      try { yield JSON.parse(json); } catch { /* skip malformed chunk */ }
    }
  }
}

// ── Source parsing ────────────────────────────────────────────────────────────

import type { SourceDoc } from "./types";

export function parseContextsToSources(contexts: string[]): SourceDoc[] {
  return contexts
    .map((ctx): SourceDoc | null => {
      const hm = ctx.match(/\[Source \d+ \| ([^|]+) \| ([^|]+) \| Relevance: ([\d.]+)%\]/);
      const sm = ctx.match(/Source: (.+)/);
      if (!hm && !sm) return null;
      const snippetStart = ctx.indexOf("\n\n");
      const snippet = snippetStart > -1
        ? ctx.slice(snippetStart + 2).slice(0, 300)
        : ctx.slice(0, 300);
      return {
        category:  hm?.[1]?.trim() ?? "Unknown",
        docType:   hm?.[2]?.trim() ?? "",
        relevance: parseFloat(hm?.[3] ?? "0"),
        source:    sm?.[1]?.trim() ?? "Unknown source",
        snippet,
      };
    })
    .filter((s): s is SourceDoc => s !== null);
}

// ── PDF ingestion ─────────────────────────────────────────────────────────────

export async function ingestPDF(
  file:         File,
  sourceName:   string,
  category:     string,
  documentType: string,
  extraMeta:    Record<string, string> = {},
): Promise<{ doc_uuid: string; chunk_count: number; char_count: number; message: string }> {
  const token    = getToken();
  const formData = new FormData();
  formData.append("file",          file);
  formData.append("source_name",   sourceName);
  formData.append("category",      category);
  formData.append("document_type", documentType);
  if (Object.keys(extraMeta).length > 0) {
    formData.append("extra_metadata", JSON.stringify(extraMeta));
  }
  const res = await fetch(`${BASE}/api/ingest/`, {
    method:  "POST",
    headers: { Authorization: `Bearer ${token}` },
    body:    formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || err.file?.[0] || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function listDocuments(): Promise<{
  count: number;
  documents: Array<{
    doc_uuid: string | null; source_name: string; category: string;
    document_type: string; file_name: string; chunk_count: number;
  }>;
}> {
  const token = getToken();
  const res   = await fetch(`${BASE}/api/documents/`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function deleteDocument(docUuid: string): Promise<void> {
  const token = getToken();
  const res   = await fetch(`${BASE}/api/documents/${docUuid}/`, {
    method:  "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}