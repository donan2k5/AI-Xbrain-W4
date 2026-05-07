export type Level = "L1" | "L2" | "L3";

export type Question = {
  id: string;
  text: string;
};

export type QuestionGroup = {
  level: Level;
  title: string;
  questions: Question[];
};

export type Citation = {
  document: string;
  uri?: string | null;
  excerpt?: string | null;
};

export type ChatResponse = {
  answer: string;
  citations: Citation[];
  trace_id: string;
  reasoning?: string | null;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  level?: Level;
  questionId?: string;
  traceId?: string;
  citations?: Citation[];
  reasoning?: string | null;
  error?: boolean;
};

export type RetrievedChunk = {
  document: string;
  text: string;
  score?: number | null;
  uri?: string | null;
  location?: Record<string, unknown> | null;
  metadata?: Record<string, unknown>;
};

export type RetrievalTrace = {
  knowledge_base_id: string;
  top_k: number;
  chunks: RetrievedChunk[];
};

export type TraceRecord = {
  trace_id: string;
  request_id: string;
  session_id?: string | null;
  level: Level;
  question_id?: string | null;
  question: string;
  answer?: string | null;
  citations: Citation[];
  retrieval?: RetrievalTrace | null;
  logs: Array<Record<string, unknown>>;
  error?: string | null;
};
