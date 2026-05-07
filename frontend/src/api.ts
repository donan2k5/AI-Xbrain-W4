import type { ChatResponse, Level, TraceRecord } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8001";

export async function sendChat(payload: {
  message: string;
  level?: Level;
  question_id?: string;
}): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    let detail: string | undefined;
    try {
      const payload = JSON.parse(text) as { detail?: string };
      detail = payload.detail;
    } catch {
      detail = text;
    }
    throw new Error(detail || `Chat request failed with ${response.status}`);
  }

  return response.json();
}

export async function fetchTrace(traceId: string): Promise<TraceRecord> {
  const response = await fetch(`${API_BASE_URL}/api/traces/${traceId}`);
  if (!response.ok) {
    const text = await response.text();
    let detail: string | undefined;
    try {
      const payload = JSON.parse(text) as { detail?: string };
      detail = payload.detail;
    } catch {
      detail = text;
    }
    throw new Error(detail || `Trace request failed with ${response.status}`);
  }
  return response.json();
}
