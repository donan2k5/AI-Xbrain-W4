import { KeyboardEvent, useEffect, useRef, useMemo, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { fetchTrace, sendChat } from "./api";
import { QUESTION_GROUPS } from "./data/questions";
import type { ChatMessage, Citation, Level, Question, ToolCallRecord, TraceRecord } from "./types";

function buildCiteMap(content: string, citations: Citation[]): Record<number, string> {
  const allNums = [...content.matchAll(/\[(\d+)\]/g)].map(m => parseInt(m[1]));
  const unique = [...new Set(allNums)].sort((a, b) => a - b);
  const map: Record<number, string> = {};
  unique.forEach((n, i) => { if (citations[i]) map[n] = citations[i].document; });
  return map;
}

function InlineText({ text, citeMap }: { text: string; citeMap: Record<number, string> }): ReactNode {
  return text.split(/(\[\d+\])/).map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (m) {
      const doc = citeMap[parseInt(m[1])];
      return <span key={i} className="cite-ref" data-doc={doc ?? part}>{part}</span>;
    }
    return part;
  });
}

function renderWithCitations(content: string, citations: Citation[]): ReactNode {
  const citeMap = buildCiteMap(content, citations);
  // Replace [n] placeholders temporarily so react-markdown doesn't mangle them
  const placeholder = (n: string) => `⟦${n}⟧`;
  const withPlaceholders = content.replace(/\[(\d+)\]/g, (_, n) => placeholder(n));

  return (
    <ReactMarkdown
      components={{
        p: ({ children }) => (
          <span className="md-para">
            {processChildren(children, citeMap)}
          </span>
        ),
        strong: ({ children }) => <strong>{children}</strong>,
        em: ({ children }) => <em>{children}</em>,
        // Flatten lists into inline prose (we forbid lists in prompt but just in case)
        li: ({ children }) => <span>{children} </span>,
        ul: ({ children }) => <span>{children}</span>,
        ol: ({ children }) => <span>{children}</span>,
      }}
    >
      {withPlaceholders}
    </ReactMarkdown>
  );
}

function processChildren(children: ReactNode, citeMap: Record<number, string>): ReactNode {
  if (typeof children === "string") {
    // Restore placeholders to cite-ref spans
    return children.split(/(⟦\d+⟧)/).map((part, i) => {
      const m = part.match(/^⟦(\d+)⟧$/);
      if (m) {
        const doc = citeMap[parseInt(m[1])];
        return <span key={i} className="cite-ref" data-doc={doc ?? `[${m[1]}]`}>[{m[1]}]</span>;
      }
      return part;
    });
  }
  if (Array.isArray(children)) {
    return children.map((child, i) =>
      typeof child === "string"
        ? <span key={i}>{processChildren(child, citeMap)}</span>
        : child
    );
  }
  return children;
}

const newId = () => crypto.randomUUID();

function inferLevel(questionId?: string, fallback?: Level): Level {
  if (fallback) return fallback;
  return questionId?.startsWith("L2") ? "L2" : "L1";
}

function App() {
  const [input, setInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedLevel, setSelectedLevel] = useState<string | null>(null);
  const [pendingQuestion, setPendingQuestion] = useState<{ id: string; level: Level } | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const sendStartRef = useRef<number>(0);

  useEffect(() => {
    if (!isSending) { setElapsedSeconds(0); return; }
    sendStartRef.current = Date.now();
    const id = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - sendStartRef.current) / 1000));
    }, 200);
    return () => clearInterval(id);
  }, [isSending]);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [traceCache, setTraceCache] = useState<Record<string, TraceRecord>>({});
  const [traceError, setTraceError] = useState<string | null>(null);
  const selectedTrace = selectedTraceId ? traceCache[selectedTraceId] : null;

  const activeQuestionLabel = useMemo(() => {
    if (!pendingQuestion) return "Custom question";
    return `${pendingQuestion.level} ${pendingQuestion.id}`;
  }, [pendingQuestion]);

  const filteredQuestionGroups = useMemo(() => {
    let groups = QUESTION_GROUPS;

    // Filter by level
    if (selectedLevel) {
      groups = groups.filter((group) => group.level === selectedLevel);
    }

    // Filter by search
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      groups = groups.map((group) => ({
        ...group,
        questions: group.questions.filter(
          (q) =>
            q.id.toLowerCase().includes(query) ||
            q.text.toLowerCase().includes(query)
        ),
      })).filter((group) => group.questions.length > 0);
    }

    return groups;
  }, [searchQuery, selectedLevel]);

  const activeTraceSummary = selectedTrace?.citations.map((citation) => citation.document).join(", ") ?? "";

  const chooseQuestion = (question: Question, level: Level) => {
    setInput(question.text);
    setPendingQuestion({ id: question.id, level });
  };

  const openTrace = async (traceId: string) => {
    setSelectedTraceId(traceId);
    setTraceError(null);
    if (traceCache[traceId]) return;
    try {
      const trace = await fetchTrace(traceId);
      setTraceCache((current) => ({ ...current, [traceId]: trace }));
    } catch (error) {
      setTraceError(error instanceof Error ? error.message : "Unable to load trace");
    }
  };

  const submit = async () => {
    const text = input.trim();
    if (!text || isSending) return;

    const level = inferLevel(pendingQuestion?.id, pendingQuestion?.level);
    const questionId = pendingQuestion?.id;
    const userMessage: ChatMessage = {
      id: newId(),
      role: "user",
      content: text,
      level,
      questionId,
    };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setPendingQuestion(null);
    setIsSending(true);

    try {
      const response = await sendChat({
        message: text,
        level,
        question_id: questionId,
      });
      const assistantMessage: ChatMessage = {
        id: newId(),
        role: "assistant",
        content: response.answer,
        level,
        questionId,
        traceId: response.trace_id,
        citations: response.citations,
        reasoning: response.reasoning,
      };
      setMessages((current) => [...current, assistantMessage]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: newId(),
          role: "assistant",
          content: error instanceof Error ? error.message : "Request failed",
          level,
          questionId,
          error: true,
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const onInputKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  return (
    <main className="app-shell">
      <aside className="question-rail" aria-label="Question bank">
        <div className="rail-header">
          <p className="eyebrow">AI-XBrain</p>
          <h1>AI-XBrain</h1>
        </div>
        <div className="level-filter">
          {["L1", "L2", "L3"].map((level) => (
            <button
              key={level}
              className={`level-button ${selectedLevel === level ? "active" : ""}`}
              onClick={() => setSelectedLevel(selectedLevel === level ? null : level)}
              type="button"
              title={`Filter by ${level}`}
            >
              {level.charAt(1)}
            </button>
          ))}
        </div>
        <input
          className="search-input"
          type="text"
          placeholder="Search questions..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          aria-label="Search questions"
        />
        <div className="question-groups">
          {filteredQuestionGroups.map((group) => (
            <section className="question-group" key={group.level}>
              <h2>{group.title}</h2>
              <div className="question-list">
                {group.questions.map((question) => (
                  <button
                    className="question-button"
                    key={question.id}
                    onClick={() => chooseQuestion(question, group.level)}
                    type="button"
                  >
                    <span>{question.id}</span>
                    {question.text}
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
      </aside>

      <section className="chat-pane" aria-label="Chat">
        <header className="chat-header">
          <div>
            <p className="eyebrow">{activeQuestionLabel}</p>
            <h2>GeekBrain Knowledge Chat</h2>
          </div>
          <div className={`status-pill ${isSending ? "thinking" : ""}`}>
            {isSending ? <><span className="pill-spinner" />{elapsedSeconds}s</> : "Ready"}
          </div>
        </header>

        <div className="message-list">
          {messages.length === 0 ? (
            <div className="empty-state">
              <h2>Select a prompt from the left rail.</h2>
              <p>Click a question to fill the input, then press Enter to send.</p>
            </div>
          ) : (
            <>
              {messages.map((message) => (
                <article className={`message ${message.role} ${message.error ? "error" : ""}`} key={message.id}>
                  <div className="message-meta">
                    <span>{message.role === "user" ? "You" : "Assistant"}</span>
                    {message.questionId ? <span>{message.questionId}</span> : null}
                  </div>
                  {message.reasoning ? (
                    <details className="reasoning-block">
                      <summary>Reasoning</summary>
                      <pre className="reasoning-content">{message.reasoning}</pre>
                    </details>
                  ) : null}
                  <div className="message-body">{renderWithCitations(message.content, message.citations ?? [])}</div>
                  {message.role === "assistant" && message.traceId ? (
                    <div className="message-actions">
                      <button className="trace-button" onClick={() => void openTrace(message.traceId!)} type="button">
                        Trace
                      </button>
                    </div>
                  ) : null}
                </article>
              ))}
              {isSending && <ThinkingMessage elapsed={elapsedSeconds} />}
            </>
          )}
        </div>

        <footer className="composer">
          <textarea
            aria-label="Question input"
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onInputKeyDown}
            placeholder="Ask a GeekBrain question..."
            rows={3}
            value={input}
          />
          <button disabled={!input.trim() || isSending} onClick={() => void submit()} type="button">
            Send
          </button>
        </footer>
      </section>

      <aside className={`trace-panel ${selectedTraceId ? "open" : ""}`} aria-label="Trace panel">
        <div className="trace-header">
          <div>
            <p className="eyebrow">Trace</p>
            <h2>{selectedTrace ? selectedTrace.question_id ?? selectedTrace.level : "No response selected"}</h2>
            {activeTraceSummary ? <p className="trace-summary">{activeTraceSummary}</p> : null}
          </div>
          {selectedTraceId ? (
            <button className="close-button" onClick={() => setSelectedTraceId(null)} type="button">
              Close
            </button>
          ) : null}
        </div>

        {selectedTraceId && !selectedTrace && !traceError ? <p className="trace-loading">Loading trace...</p> : null}
        {traceError ? <p className="trace-error">{traceError}</p> : null}
        {selectedTrace ? (
          <>
            <TraceContent trace={selectedTrace} />
          </>
        ) : null}
      </aside>
    </main>
  );
}

function ThinkingMessage({ elapsed }: { elapsed: number }) {
  return (
    <article className="message assistant">
      <div className="message-meta"><span>Assistant</span></div>
      <div className="thinking-bubble">
        <span className="thinking-spinner" />
        <span className="thinking-label">Thinking</span>
        <span className="thinking-dots"><span /><span /><span /></span>
        <span className="thinking-elapsed">{elapsed}s</span>
      </div>
    </article>
  );
}

function stripFrontmatter(text: string): string {
  const s = text.trim();
  if (!s.startsWith("---")) return s;
  const end = s.indexOf("\n---", 3);
  return end !== -1 ? s.slice(end + 4).trimStart() : s;
}

const TOOL_ICONS: Record<string, string> = {
  search_knowledge_base: "📚",
  fetch_service_metrics: "📡",
  fetch_all_services_metrics: "📡",
  get_service_costs: "💰",
  get_all_costs: "💰",
  get_q1_costs_summary: "💰",
  get_service_incidents: "🚨",
  get_sla_targets: "🎯",
  get_daily_metrics: "📈",
  get_service_comparison: "⚖️",
};

function ToolCallRow({ call }: { call: ToolCallRecord }) {
  const icon = TOOL_ICONS[call.tool_name] ?? "🔧";
  return (
    <div className="tool-call-row">
      <div className="tool-call-header">
        <span className="tool-icon">{icon}</span>
        <span className="tool-name">{call.tool_name}</span>
      </div>
      {call.params && <p className="tool-params">{call.params}</p>}
      <p className="tool-result">{call.result_hint}</p>
    </div>
  );
}

function TraceContent({ trace }: { trace: TraceRecord }) {
  const toolCalls = trace.tool_calls ?? [];
  const kbCalls = toolCalls.filter(t => t.tool_name === "search_knowledge_base");
  const dataCalls = toolCalls.filter(t => t.tool_name !== "search_knowledge_base");
  const citedDocs = trace.citations;

  return (
    <div className="trace-content">

      {/* ── Tool calls (data tools) ── */}
      {dataCalls.length > 0 && (
        <section className="trace-section">
          <h3>Tools called ({dataCalls.length})</h3>
          {dataCalls.map((call, i) => <ToolCallRow key={i} call={call} />)}
        </section>
      )}

      {/* ── KB searches ── */}
      {kbCalls.length > 0 && (
        <section className="trace-section">
          <h3>KB searches ({kbCalls.length})</h3>
          {kbCalls.map((call, i) => <ToolCallRow key={i} call={call} />)}
        </section>
      )}

      {/* ── Cited sources (document names only) ── */}
      <section className="trace-section">
        <h3>Sources cited</h3>
        {citedDocs.length === 0
          ? <p className="trace-empty">No KB sources — answer from live tools.</p>
          : citedDocs.map((c, i) => (
            <div className="source-row" key={`${c.document}-${i}`}>
              <span className="source-index">[{i + 1}]</span>
              <strong>{c.document}</strong>
            </div>
          ))}
      </section>

    </div>
  );
}

export default App;
