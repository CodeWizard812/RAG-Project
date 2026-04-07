// frontend/app/chat/page.tsx
"use client";

import {
  useState, useEffect, useRef, useCallback,
} from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import {
  getToken, clearToken, clearSession, streamChat,
  parseContextsToSources, fetchSessionHistory,
  loadStoredSessions, saveStoredSessions,
} from "@/lib/api";
import type { Message, Session, SourceDoc, ModelType } from "@/lib/types";
import PDFIngestModal from "@/components/PDFIngestModal";

const TOOL_LABELS: Record<string, string> = {
  financial_database_query:    "Querying PostgreSQL",
  regulatory_knowledge_search: "Searching regulations",
};

const TOOL_COLORS: Record<string, string> = {
  financial_database_query:    "bg-amber-50 text-amber-800 border-amber-200",
  regulatory_knowledge_search: "bg-teal-50  text-teal-800  border-teal-200",
};

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

// ── Tool badge ─────────────────────────────────────────────────────────────

function ToolBadge({ tool, active }: { tool: string; active?: boolean }) {
  const label  = TOOL_LABELS[tool]  ?? tool;
  const colors = TOOL_COLORS[tool]  ?? "bg-gray-50 text-gray-700 border-gray-200";
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border ${colors} ${active ? "animate-pulse" : ""}`}>
      {active && <span className="w-1.5 h-1.5 rounded-full bg-current opacity-75" />}
      <span className="hidden sm:inline">{label}</span>
      <span className="sm:hidden">{active ? "…" : "✓"}</span>
      {!active && <span className="hidden sm:inline"> ✓</span>}
      {active  && <span className="hidden sm:inline">…</span>}
    </span>
  );
}

// ── Source card ────────────────────────────────────────────────────────────

function SourceCard({ src }: { src: SourceDoc }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-gray-100 rounded-lg overflow-hidden text-xs">
      <button
        onClick={() => setOpen(p => !p)}
        className="w-full flex items-start justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 transition-colors text-left gap-2"
      >
        <div className="min-w-0">
          <span className="font-medium text-gray-800 block truncate">{src.source}</span>
          <span className="text-gray-400">{src.category}</span>
          {src.docType && (
            <span className="ml-2 bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded">{src.docType}</span>
          )}
        </div>
        <div className="flex items-center gap-1 text-gray-400 shrink-0">
          <span className="hidden sm:inline">{src.relevance.toFixed(1)}%</span>
          <span>{open ? "▲" : "▼"}</span>
        </div>
      </button>
      {open && (
        <div className="px-3 py-2 text-gray-600 bg-white leading-relaxed border-t border-gray-100 wrap-break-word">
          {src.snippet}…
        </div>
      )}
    </div>
  );
}

// ── Message bubble ─────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: Message }) {
  if (msg.role === "human") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] sm:max-w-[75%] bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed wrap-break-word">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[92%] sm:max-w-[85%] flex flex-col gap-2">
        {((msg.activeTools?.length ?? 0) > 0 || (msg.toolCalls?.length ?? 0) > 0) && (
          <div className="flex flex-wrap gap-1.5">
            {msg.activeTools?.map(t => <ToolBadge key={t} tool={t} active />)}
            {msg.toolCalls?.map((tc, i) => <ToolBadge key={i} tool={tc.tool} />)}
          </div>
        )}
        <div className="bg-white border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed text-gray-800 wrap-break-word">
          {msg.isStreaming && !msg.content ? (
            <div className="flex gap-1 items-center py-1">
              {[0, 150, 300].map(d => (
                <span key={d} className="w-2 h-2 bg-gray-300 rounded-full animate-bounce"
                  style={{ animationDelay: `${d}ms` }} />
              ))}
            </div>
          ) : (
            <ReactMarkdown
              components={{
                p:      ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                ul:     ({ children }) => <ul className="list-disc pl-4 mb-2">{children}</ul>,
                ol:     ({ children }) => <ol className="list-decimal pl-4 mb-2">{children}</ol>,
                li:     ({ children }) => <li className="mb-1">{children}</li>,
                code:   ({ children }) => (
                  <code className="bg-gray-100 text-gray-800 px-1.5 py-0.5 rounded text-xs font-mono">
                    {children}
                  </code>
                ),
              }}
            >
              {msg.content}
            </ReactMarkdown>
          )}
          {msg.isStreaming && msg.content && (
            <span className="inline-block w-0.5 h-4 bg-blue-500 ml-0.5 animate-pulse align-middle" />
          )}
        </div>
        {(msg.sources?.length ?? 0) > 0 && (
          <div className="flex flex-col gap-1.5">
            <p className="text-xs text-gray-400 px-1">
              {msg.sources!.length} source{msg.sources!.length > 1 ? "s" : ""} retrieved
            </p>
            {msg.sources!.map((src, i) => <SourceCard key={i} src={src} />)}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Session row ────────────────────────────────────────────────────────────

function SessionRow({
  session, active, onSelect, onRename, onDelete,
}: {
  session:  Session; active: boolean;
  onSelect: () => void;
  onRename: (label: string) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft,   setDraft]   = useState(session.label);
  const [confirm, setConfirm] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function startEdit(e: React.MouseEvent) {
    e.stopPropagation();
    setDraft(session.label);
    setEditing(true);
    setTimeout(() => { inputRef.current?.focus(); inputRef.current?.select(); }, 0);
  }

  function commit() {
    const t = draft.trim();
    if (t && t !== session.label) onRename(t);
    setEditing(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter")  { e.preventDefault(); commit(); }
    if (e.key === "Escape") { setEditing(false); setDraft(session.label); }
  }

  function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    if (confirm) { onDelete(); }
    else {
      setConfirm(true);
      setTimeout(() => setConfirm(false), 3000);
    }
  }

  return (
    <div
      onClick={onSelect}
      className={`group flex items-center gap-1 px-2 py-2 rounded-lg cursor-pointer transition-colors ${
        active ? "bg-blue-50 text-blue-700" : "text-gray-600 hover:bg-gray-50"
      }`}
    >
      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={onKeyDown}
          onClick={e => e.stopPropagation()}
          className="flex-1 text-sm bg-white border border-blue-300 rounded px-1.5 py-0.5 focus:outline-none text-gray-900 min-w-0"
        />
      ) : (
        <span className="text-sm truncate flex-1 min-w-0">{session.label}</span>
      )}
      {!editing && (
        <div className={`flex gap-0.5 shrink-0 transition-opacity ${active ? "opacity-60" : "opacity-0 group-hover:opacity-60"}`}>
          <button onClick={startEdit} title="Rename"
            className="p-0.5 rounded hover:opacity-100 hover:text-gray-700 text-gray-400">
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M11.5 2.5l2 2-9 9H2.5v-2L11.5 2.5z"/>
            </svg>
          </button>
          <button onClick={handleDelete}
            title={confirm ? "Click again to confirm" : "Delete"}
            className={`p-0.5 rounded hover:opacity-100 transition-colors ${
              confirm ? "text-red-500 opacity-100" : "text-gray-400 hover:text-red-500"
            }`}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 4h12M5 4V2h6v2M6 7v5M10 7v5M3 4l1 10h8L13 4"/>
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────

function historyToMessages(
  records: Array<{ role: "human" | "ai"; content: string }>,
): Message[] {
  return records.map(r => ({ id: uid(), role: r.role, content: r.content }));
}

function labelFromFirstMessage(
  records: Array<{ role: "human" | "ai"; content: string }>,
  fallback: string,
): string {
  const first = records.find(r => r.role === "human");
  if (!first) return fallback;
  return first.content.length > 36 ? first.content.slice(0, 36) + "…" : first.content;
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function ChatPage() {
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) router.replace("/");
  }, [router]);

  const [sessions,        setSessions]        = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [messages,        setMessages]        = useState<Message[]>([]);
  const [historyLoading,  setHistoryLoading]  = useState(false);
  const [input,           setInput]           = useState("");
  const [model,           setModel]           = useState<ModelType>("gemini-2.5-flash");
  const [isStreaming,     setIsStreaming]      = useState(false);
  const [showIngest,      setShowIngest]       = useState(false);
  const [sidebarOpen,     setSidebarOpen]     = useState(false);

  const bottomRef  = useRef<HTMLDivElement>(null);
  const inputRef   = useRef<HTMLTextAreaElement>(null);

  // ── Boot ──────────────────────────────────────────────────────────────────

  useEffect(() => {
    const stored = loadStoredSessions();
    if (stored.length > 0) {
      setSessions(stored);
      setActiveSessionId(stored[0].id);
      loadHistory(stored[0].id);
    } else {
      const id      = uid();
      const initial = [{ id, label: "Chat 1" }];
      setSessions(initial);
      saveStoredSessions(initial);
      setActiveSessionId(id);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Close sidebar on outside click (mobile)
  useEffect(() => {
    if (!sidebarOpen) return;
    function handleClick(e: MouseEvent) {
      const sidebar = document.getElementById("sidebar");
      if (sidebar && !sidebar.contains(e.target as Node)) {
        setSidebarOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [sidebarOpen]);

  // ── History ───────────────────────────────────────────────────────────────

  async function loadHistory(sessionId: string) {
    if (!sessionId) return;
    setHistoryLoading(true);
    try {
      const records = await fetchSessionHistory(sessionId);
      if (records.length > 0) {
        setMessages(historyToMessages(records));
        setSessions(prev => {
          const session   = prev.find(s => s.id === sessionId);
          if (!session) return prev;
          if (!/^Chat \d+$/.test(session.label)) return prev;
          const updated = prev.map(s =>
            s.id === sessionId
              ? { ...s, label: labelFromFirstMessage(records, s.label) }
              : s
          );
          saveStoredSessions(updated);
          return updated;
        });
      } else {
        setMessages([]);
      }
    } catch {
      setMessages([]);
    } finally {
      setHistoryLoading(false);
    }
  }

  // ── Session management ────────────────────────────────────────────────────

  function newSession() {
    const id      = uid();
    const label   = `Chat ${sessions.length + 1}`;
    const updated = [...sessions, { id, label }];
    setSessions(updated);
    saveStoredSessions(updated);
    setActiveSessionId(id);
    setMessages([]);
    setSidebarOpen(false);
  }

  async function switchSession(id: string) {
    if (id === activeSessionId) { setSidebarOpen(false); return; }
    setActiveSessionId(id);
    setMessages([]);
    setSidebarOpen(false);
    await loadHistory(id);
  }

  function renameSession(id: string, newLabel: string) {
    const updated = sessions.map(s => s.id === id ? { ...s, label: newLabel } : s);
    setSessions(updated);
    saveStoredSessions(updated);
  }

  async function deleteSession(id: string) {
    await clearSession(id).catch(() => {});
    const updated = sessions.filter(s => s.id !== id);
    setSessions(updated);
    saveStoredSessions(updated);
    if (id === activeSessionId) {
      if (updated.length > 0) {
        setActiveSessionId(updated[0].id);
        await loadHistory(updated[0].id);
      } else {
        const newId  = uid();
        const fresh  = [{ id: newId, label: "New Chat" }];
        setSessions(fresh);
        saveStoredSessions(fresh);
        setActiveSessionId(newId);
        setMessages([]);
      }
    }
  }

  function handleLogout() {
    clearToken();
    router.replace("/");
  }

  // ── Streaming ─────────────────────────────────────────────────────────────

  const sendMessage = useCallback(async (question: string) => {
    if (!question.trim() || isStreaming) return;
    setIsStreaming(true);

    const humanId = uid();
    setMessages(prev => [...prev, { id: humanId, role: "human", content: question }]);

    const aiId = uid();
    setMessages(prev => [
      ...prev,
      { id: aiId, role: "ai", content: "", isStreaming: true, activeTools: [], toolCalls: [] },
    ]);

    setSessions(prev => {
      const session = prev.find(s => s.id === activeSessionId);
      if (!session || !/^Chat \d+$/.test(session.label)) return prev;
      const label   = question.length > 36 ? question.slice(0, 36) + "…" : question;
      const updated = prev.map(s => s.id === activeSessionId ? { ...s, label } : s);
      saveStoredSessions(updated);
      return updated;
    });

    try {
      const stream = streamChat(question, activeSessionId, model);
      for await (const event of stream) {
        const type = event.event as string;
        if (type === "tool_start") {
          setMessages(prev => prev.map(m =>
            m.id !== aiId ? m : { ...m, activeTools: [...(m.activeTools ?? []), event.tool as string] }
          ));
        } else if (type === "tool_end") {
          setMessages(prev => prev.map(m => {
            if (m.id !== aiId) return m;
            const active = m.activeTools ?? [];
            return {
              ...m,
              activeTools: active.slice(0, -1),
              toolCalls:   [...(m.toolCalls ?? []), { tool: active[active.length - 1] ?? "unknown", input: {} }],
            };
          }));
        } else if (type === "done") {
          const answer    = event.answer as string;
          const sources   = parseContextsToSources((event.contexts as string[]) ?? []);
          const toolCalls = (event.tool_calls as Array<{ tool: string; input: Record<string, unknown> }>) ?? [];
          const words     = answer.split(" ");
          for (let i = 0; i < words.length; i++) {
            await new Promise(r => setTimeout(r, 18));
            setMessages(prev => prev.map(m =>
              m.id !== aiId ? m : { ...m, content: words.slice(0, i + 1).join(" ") }
            ));
          }
          setMessages(prev => prev.map(m =>
            m.id !== aiId ? m : {
              ...m, content: answer, isStreaming: false,
              activeTools: [], toolCalls, sources,
            }
          ));
        } else if (type === "error") {
          setMessages(prev => prev.map(m =>
            m.id !== aiId ? m : {
              ...m, content: `Error: ${event.message as string}`,
              isStreaming: false, activeTools: [],
            }
          ));
        }
      }
    } catch (err) {
      setMessages(prev => prev.map(m =>
        m.id !== aiId ? m : {
          ...m, content: `Connection error: ${(err as Error).message}`,
          isStreaming: false, activeTools: [],
        }
      ));
    } finally {
      setIsStreaming(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [activeSessionId, model, isStreaming]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
      setInput("");
    }
  }

  const activeSession = sessions.find(s => s.id === activeSessionId);

  // ── Sidebar content (shared between mobile drawer and desktop) ────────────

  const SidebarContent = () => (
    <>
      <div className="px-4 py-4 border-b border-gray-100">
        <h1 className="text-sm font-semibold text-gray-900 leading-tight">Financial Intelligence</h1>
        <p className="text-xs text-gray-400 mt-0.5">Regulatory Agent</p>
      </div>
      <div className="flex-1 overflow-y-auto py-2 px-2 flex flex-col gap-0.5">
        {sessions.map(s => (
          <SessionRow
            key={s.id}
            session={s}
            active={s.id === activeSessionId}
            onSelect={() => switchSession(s.id)}
            onRename={label => renameSession(s.id, label)}
            onDelete={() => deleteSession(s.id)}
          />
        ))}
      </div>
      <div className="px-3 pb-4 flex flex-col gap-0.5 border-t border-gray-100 pt-3">
        <button onClick={newSession}
          className="w-full text-left px-3 py-1.5 text-sm text-blue-600 hover:bg-blue-50 rounded-lg transition-colors">
          + New chat
        </button>
        <button onClick={() => { setShowIngest(true); setSidebarOpen(false); }}
          className="w-full text-left px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 rounded-lg transition-colors flex items-center gap-2">
          <span>Upload PDF</span>
          <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium">new</span>
        </button>
        <button onClick={handleLogout}
          className="w-full text-left px-3 py-1.5 text-sm text-gray-400 hover:bg-gray-50 rounded-lg transition-colors">
          Sign out
        </button>
      </div>
    </>
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      <div className="flex h-screen bg-gray-50 overflow-hidden">

        {/* Mobile sidebar overlay */}
        {sidebarOpen && (
          <div className="fixed inset-0 bg-black/20 z-20 md:hidden" />
        )}

        {/* Sidebar — hidden on mobile unless open */}
        <aside
          id="sidebar"
          className={`
            fixed md:relative z-30 md:z-auto
            top-0 left-0 h-full
            w-64 md:w-56
            bg-white border-r border-gray-100
            flex flex-col
            transition-transform duration-200 ease-in-out
            ${sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
          `}
        >
          <SidebarContent />
        </aside>

        {/* Main */}
        <main className="flex-1 flex flex-col overflow-hidden min-w-0">

          {/* Header */}
          <header className="bg-white border-b border-gray-100 px-3 sm:px-6 py-3 flex items-center gap-3">

            {/* Hamburger — mobile only */}
            <button
              onClick={() => setSidebarOpen(p => !p)}
              className="md:hidden p-2 rounded-lg hover:bg-gray-100 transition-colors shrink-0"
              aria-label="Toggle sidebar"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 6h18M3 12h18M3 18h18"/>
              </svg>
            </button>

            {/* Session label */}
            <div className="flex-1 min-w-0">
              {historyLoading
                ? <span className="text-xs text-gray-400 italic">Loading history…</span>
                : <span className="text-sm font-medium text-gray-800 truncate block">
                    {activeSession?.label ?? "Chat"}
                  </span>
              }
            </div>

            {/* Model switcher */}
            <div className="flex items-center gap-1 bg-gray-50 rounded-lg p-1 border border-gray-200 shrink-0">
              {(["gemini-2.5-flash", "gemini-2.5-pro"] as ModelType[]).map(m => (
                <button
                  key={m}
                  onClick={() => setModel(m)}
                  className={`px-2 sm:px-3 py-1 text-xs rounded-md transition-colors font-medium whitespace-nowrap ${
                    model === m
                      ? "bg-white text-blue-700 border border-blue-200"
                      : "text-gray-500 hover:text-gray-700"
                  }`}
                >
                  {m === "gemini-2.5-flash" ? "Flash" : "Pro"}
                </button>
              ))}
            </div>
          </header>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-3 sm:px-6 py-4 sm:py-6">
            {historyLoading ? (
              <div className="flex items-center justify-center h-full text-sm text-gray-400">
                Loading conversation…
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center px-2">
                <p className="text-gray-400 text-sm mb-4">
                  Ask about financials, SEBI rules, or compare companies.
                </p>
                <div className="flex flex-col gap-2 w-full max-w-lg">
                  {[
                    "Is GreenHorizon eligible for SEBI institutional investment?",
                    "Compare Aether Technologies and NovaMed by net income.",
                    "What did ATHR say about their AI strategy?",
                  ].map(q => (
                    <button
                      key={q}
                      onClick={() => { sendMessage(q); setInput(""); }}
                      className="text-left px-4 py-2.5 text-sm text-gray-600 bg-white border border-gray-200 rounded-xl hover:border-blue-300 hover:text-blue-700 transition-colors"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-4 max-w-3xl mx-auto w-full">
                {messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div className="bg-white border-t border-gray-100 px-3 sm:px-6 py-3 sm:py-4">
            <div className="max-w-3xl mx-auto flex gap-2 sm:gap-3 items-end">
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question…"
                disabled={isStreaming || historyLoading}
                className="flex-1 resize-none border border-gray-200 rounded-xl px-3 sm:px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50 disabled:opacity-50 max-h-32 leading-relaxed min-w-0"
                style={{ height: "42px" }}
                onInput={e => {
                  const t = e.currentTarget;
                  t.style.height = "42px";
                  t.style.height = Math.min(t.scrollHeight, 128) + "px";
                }}
              />
              <button
                onClick={() => { sendMessage(input); setInput(""); }}
                disabled={isStreaming || !input.trim() || historyLoading}
                className="px-3 sm:px-4 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 disabled:opacity-40 transition-colors shrink-0"
              >
                {isStreaming ? "…" : "Send"}
              </button>
            </div>
            <p className="text-xs text-gray-400 text-center mt-2 hidden sm:block">
              Using <span className="font-medium">{model}</span>
              {" · "}
              <button onClick={() => setShowIngest(true)} className="hover:text-gray-600">
                upload PDF
              </button>
            </p>
          </div>
        </main>
      </div>

      {showIngest && <PDFIngestModal onClose={() => setShowIngest(false)} />}
    </>
  );
}