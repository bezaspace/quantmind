const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export function streamChat(
  sessionId: string,
  message: string,
  onEvent: (event: any) => void,
  onError?: (err: any) => void
) {
  const url = `${API_BASE}/chat/stream?session_id=${encodeURIComponent(
    sessionId
  )}&message=${encodeURIComponent(message)}`;
  const source = new EventSource(url);

  source.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent(data);
    } catch (err) {
      console.error("Failed to parse SSE data", err);
    }
  };

  source.onerror = (err) => {
    source.close();
    onError?.(err as any);
  };

  return source;
}

export async function submitApproval(
  requestId: string,
  approved: boolean
): Promise<void> {
  const res = await fetch(`${API_BASE}/approval/${requestId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved }),
  });
  if (!res.ok) {
    throw new Error(`Approval failed: ${res.statusText}`);
  }
}

export async function chat(
  sessionId: string,
  message: string
): Promise<{ session_id: string; events: any[] }> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  if (!res.ok) {
    throw new Error(`Chat failed: ${res.statusText}`);
  }
  return res.json();
}
