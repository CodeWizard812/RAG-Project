// frontend/app/chat/page.tsx
"use client";

import {
  useState, useEffect, useRef, useCallback,
} from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import {
  getToken, clearToken, clearSession, streamChat,
  parseContextsToSources,
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

// ── Sub-components ─────────────────────────────────────────────────────────

function ToolBadge({ tool, active }: { tool: string; active?: boolean }) {
  const label  = TOOL_LABELS[tool]  ?? tool;
  const colors = TOOL_COLORS[tool]  ?? "bg-gray-50 text-gray-700 border-gray-200";
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${colors} ${
        active ? "animate-pulse" : ""
      }`}
    >
      {active && (
        <span className="w-1.5 h-1.5 rounded-full bg-current opacity-75" />
      )}
      {label}
      {active ? "…" : " ✓"}
    </span>
  );
}

function SourceCard({ src }: { src: SourceDoc }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-gray-100 rounded-lg overflow-hidden text-xs">
      <button
        onClick={() => setOpen(p => !p)}
        className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        <div>
          <span className="font-medium text-gray-800">{src.source}</span>
          <span className="ml-2 text-gray-400">{src.category}</span>
          {src.docType && (
            <span className="ml-2 bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded text-xs">
              {src.docType}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-gray-400">
          <span>{src.relevance.toFixed(1)}% match</span>
          <span>{open ? "▲" : "▼"}</span>
        </div>
      </button>
      {open && (
        <div className="px-3 py-2 text-gray-600 bg-white leading-relaxed border-t border-gray-100">
          {src.snippet}…
        </div>
      )}
    </div>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  if (msg.role === "human") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] flex flex-col gap-2">
        {((msg.activeTools?.length ?? 0) > 0 || (msg.toolCalls?.length ?? 0) > 0) && (
          <div className="flex flex-wrap gap-1.5">
            {msg.activeTools?.map(t => (
              <ToolBadge key={t} tool={t} active />
            ))}
            {msg.toolCalls?.map((tc, i) => (
              <ToolBadge key={i} tool={tc.tool} active={false} />
            ))}
          </div>
        )}

        <div className="bg-white border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed text-gray-800">
          {msg.isStreaming && !msg.content ? (
            <div className="flex gap-1 items-center py-1">
              {[0, 150, 300].map(d => (
                <span
                  key={d}
                  className="w-2 h-2 bg-gray-300 rounded-full animate-bounce"
                  style={{ animationDelay: `${d}ms` }}
                />
              ))}
            </div>
          ) : (
            <ReactMarkdown
              components={{
                p:      ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                ul:     ({ children }) => <ul className="list-disc pl-4 mb-2">{children}</ul>,
                li:     ({ children }) => <li className="mb-1">{children}</li>,
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
            {msg.sources!.map((src, i) => (
              <SourceCard key={i} src={src} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Session row with inline rename ─────────────────────────────────────────

function SessionRow({
  session,
  active,
  onSelect,
  onRename,
}: {
  session:  Session;
  active:   boolean;
  onSelect: () => void;
  onRename: (newLabel: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft,   setDraft]   = useState(session.label);
  const inputRef = useRef<HTMLInputElement>(null);

  function startEdit(e: React.MouseEvent) {
    e.stopPropagation();
    setDraft(session.label);
    setEditing(true);
    setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 0);
  }

  function commitEdit() {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== session.label) onRename(trimmed);
    setEditing(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter")  { e.preventDefault(); commitEdit(); }
    if (e.key === "Escape") { setEditing(false); setDraft(session.label); }
  }

  return (
    <div
      onClick={onSelect}
      className={`group flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors ${
        active
          ? "bg-blue-50 text-blue-700"
          : "text-gray-600 hover:bg-gray-50"
      }`}
    >
      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commitEdit}
          onKeyDown={onKeyDown}
          onClick={e => e.stopPropagation()}
          className="flex-1 text-sm bg-white border border-blue-300 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-400 text-gray-900"
        />
      ) : (
        <>
          <span className="text-sm truncate flex-1">{session.label}</span>
          {/* Rename pencil — visible on hover or when active */}
          <button
            onClick={startEdit}
            title="Rename session"
            className={`text-xs px-1 py-0.5 rounded transition-opacity ${
              active ? "opacity-60 hover:opacity-100" : "opacity-0 group-hover:opacity-60 hover:opacity-100!"
            } text-gray-400 hover:text-gray-600`}
          >
            ✎
          </button>
        </>
      )}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function ChatPage() {
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) router.replace("/");
  }, [router]);

  const [sessions,        setSessions]        = useState<Session[]>([
    { id: "default", label: "New session" },
  ]);
  const [activeSessionId, setActiveSessionId] = useState("default");
  const [messages,        setMessages]        = useState<Message[]>([]);
  const [input,           setInput]           = useState("");
  const [model,           setModel]           = useState<ModelType>("gemini-2.5-flash");
  const [isStreaming,     setIsStreaming]      = useState(false);
  const [showIngest,      setShowIngest]       = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Session management ───────────────────────────────────────────────────

  function newSession() {
    const id    = uid();
    const label = `Session ${sessions.length + 1}`;
    setSessions(p => [...p, { id, label }]);
    setActiveSessionId(id);
    setMessages([]);
  }

  function switchSession(id: string) {
    setActiveSessionId(id);
    setMessages([]);
  }

  function renameSession(id: string, newLabel: string) {
    setSessions(prev =>
      prev.map(s => s.id === id ? { ...s, label: newLabel } : s)
    );
  }

  async function handleClearSession() {
    await clearSession(activeSessionId);
    setMessages([]);
  }

  function handleLogout() {
    clearToken();
    router.replace("/");
  }

  // ── Streaming ────────────────────────────────────────────────────────────

  const sendMessage = useCallback(async (question: string) => {
    if (!question.trim() || isStreaming) return;

    setIsStreaming(true);

    const humanId = uid();
    setMessages(prev => [
      ...prev,
      { id: humanId, role: "human", content: question },
    ]);

    const aiId = uid();
    setMessages(prev => [
      ...prev,
      {
        id:          aiId,
        role:        "ai",
        content:     "",
        isStreaming: true,
        activeTools: [],
        toolCalls:   [],
      },
    ]);

    try {
      const stream = streamChat(question, activeSessionId, model);

      for await (const event of stream) {
        const type = event.event as string;

        if (type === "tool_start") {
          setMessages(prev => prev.map(m =>
            m.id !== aiId ? m : {
              ...m,
              activeTools: [...(m.activeTools ?? []), event.tool as string],
            }
          ));
        } else if (type === "tool_end") {
          setMessages(prev => prev.map(m => {
            if (m.id !== aiId) return m;
            const active = m.activeTools ?? [];
            return {
              ...m,
              activeTools: active.slice(0, -1),
              toolCalls: [
                ...(m.toolCalls ?? []),
                { tool: active[active.length - 1] ?? "unknown", input: {} },
              ],
            };
          }));
        } else if (type === "done") {
          const answer    = event.answer as string;
          const sources   = parseContextsToSources((event.contexts as string[]) ?? []);
          const toolCalls = (event.tool_calls as Array<{ tool: string; input: Record<string, unknown> }>) ?? [];

          const words = answer.split(" ");
          for (let i = 0; i < words.length; i++) {
            await new Promise(r => setTimeout(r, 18));
            setMessages(prev => prev.map(m =>
              m.id !== aiId ? m : { ...m, content: words.slice(0, i + 1).join(" ") }
            ));
          }

          setMessages(prev => prev.map(m =>
            m.id !== aiId ? m : {
              ...m,
              content:     answer,
              isStreaming: false,
              activeTools: [],
              toolCalls,
              sources,
            }
          ));
        } else if (type === "error") {
          setMessages(prev => prev.map(m =>
            m.id !== aiId ? m : {
              ...m,
              content:     `Error: ${event.message as string}`,
              isStreaming: false,
              activeTools: [],
            }
          ));
        }
      }
    } catch (err) {
      setMessages(prev => prev.map(m =>
        m.id !== aiId ? m : {
          ...m,
          content:     `Connection error: ${(err as Error).message}`,
          isStreaming: false,
          activeTools: [],
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

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <>
      <div className="flex h-screen bg-gray-50 overflow-hidden">

        {/* Sidebar */}
        <aside className="w-56 bg-white border-r border-gray-100 flex flex-col">
          <div className="px-4 py-4 border-b border-gray-100">
            <h1 className="text-sm font-semibold text-gray-900 leading-tight">
              Financial Intelligence
            </h1>
            <p className="text-xs text-gray-400 mt-0.5">Regulatory Agent</p>
          </div>

          {/* Sessions list */}
          <div className="flex-1 overflow-y-auto py-2 px-2 scrollbar-thin flex flex-col gap-0.5">
            {sessions.map(s => (
              <SessionRow
                key={s.id}
                session={s}
                active={s.id === activeSessionId}
                onSelect={() => switchSession(s.id)}
                onRename={label => renameSession(s.id, label)}
              />
            ))}
          </div>

          {/* Sidebar actions */}
          <div className="px-3 pb-4 flex flex-col gap-0.5 border-t border-gray-100 pt-3">
            <button
              onClick={newSession}
              className="w-full text-left px-3 py-1.5 text-sm text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
            >
              + New session
            </button>

            {/* PDF ingest button */}
            <button
              onClick={() => setShowIngest(true)}
              className="w-full text-left px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 rounded-lg transition-colors flex items-center gap-2"
            >
              <span>Upload PDF</span>
              <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium">
                new
              </span>
            </button>

            <button
              onClick={handleClearSession}
              className="w-full text-left px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 rounded-lg transition-colors"
            >
              Clear session
            </button>
            <button
              onClick={handleLogout}
              className="w-full text-left px-3 py-1.5 text-sm text-gray-400 hover:bg-gray-50 rounded-lg transition-colors"
            >
              Sign out
            </button>
          </div>
        </aside>

        {/* Main area */}
        <main className="flex-1 flex flex-col overflow-hidden">

          <header className="bg-white border-b border-gray-100 px-6 py-3 flex items-center justify-between">
            <div className="text-sm text-gray-500">
              Session:{" "}
              <span className="font-medium text-gray-800">
                {sessions.find(s => s.id === activeSessionId)?.label ?? activeSessionId}
              </span>
            </div>

            <div className="flex items-center gap-1.5 bg-gray-50 rounded-lg p-1 border border-gray-200">
              {(["gemini-2.5-flash", "gemini-2.5-pro"] as ModelType[]).map(m => (
                <button
                  key={m}
                  onClick={() => setModel(m)}
                  className={`px-3 py-1 text-xs rounded-md transition-colors font-medium ${
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

          <div className="flex-1 overflow-y-auto px-6 py-6 scrollbar-thin">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <p className="text-gray-400 text-sm mb-4">
                  Ask about financials, SEBI rules, or compare companies.
                </p>
                <div className="flex flex-col gap-2 w-full max-w-lg">
                  {[
                    "Is GreenHorizon eligible for SEBI institutional investment?",
                    "Compare Aether Technologies and NovaMed Pharma by net income.",
                    "What did ATHR management say about their AI strategy?",
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
            )}

            <div className="flex flex-col gap-4 max-w-3xl mx-auto">
              {messages.map(msg => (
                <MessageBubble key={msg.id} msg={msg} />
              ))}
            </div>
            <div ref={bottomRef} />
          </div>

          <div className="bg-white border-t border-gray-100 px-6 py-4">
            <div className="max-w-3xl mx-auto flex gap-3 items-end">
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question… (Enter to send, Shift+Enter for new line)"
                disabled={isStreaming}
                className="flex-1 resize-none border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50 disabled:opacity-50 max-h-32 leading-relaxed"
                style={{ height: "42px" }}
                onInput={e => {
                  const t = e.currentTarget;
                  t.style.height = "42px";
                  t.style.height = Math.min(t.scrollHeight, 128) + "px";
                }}
              />
              <button
                onClick={() => { sendMessage(input); setInput(""); }}
                disabled={isStreaming || !input.trim()}
                className="px-4 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 disabled:opacity-40 transition-colors"
              >
                {isStreaming ? "…" : "Send"}
              </button>
            </div>
            <p className="text-xs text-gray-400 text-center mt-2">
              Using <span className="font-medium">{model}</span>
              {" · "}
              <button onClick={handleClearSession} className="hover:text-gray-600">
                clear session
              </button>
              {" · "}
              <button
                onClick={() => setShowIngest(true)}
                className="hover:text-gray-600"
              >
                upload PDF
              </button>
            </p>
          </div>
        </main>
      </div>

      {/* PDF ingest modal — rendered outside the layout so it overlays everything */}
      {showIngest && (
        <PDFIngestModal onClose={() => setShowIngest(false)} />
      )}
    </>
  );
}