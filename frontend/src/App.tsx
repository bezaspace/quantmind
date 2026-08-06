import { useCallback, useEffect, useRef, useState } from "react";
import { streamChat, submitApproval } from "./api";
import ApprovalCard from "./components/ApprovalCard";
import EventRenderer from "./components/EventRenderer";
import "./App.css";

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  text?: string;
  event?: any;
}

function generateId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function App() {
  const [sessionId] = useState(() => `web-${generateId()}`);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [pendingApprovals, setPendingApprovals] = useState<Record<string, any>>({});
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pendingApprovals]);

  const handleEvent = useCallback((raw: any) => {
    const event = raw.data || raw;
    const id = generateId();
    if (event.type === "approval_requested") {
      setPendingApprovals((prev) => ({
        ...prev,
        [event.data.request_id]: event.data,
      }));
    } else if (event.type === "assistant_message") {
      setMessages((prev) => [
        ...prev,
        { id, role: "agent", text: event.data.content },
      ]);
    } else {
      setMessages((prev) => [...prev, { id, role: "agent", event }]);
    }
  }, []);

  const send = async () => {
    if (!input.trim()) return;
    const userText = input;
    setInput("");
    setLoading(true);
    setMessages((prev) => [
      ...prev,
      { id: generateId(), role: "user", text: userText },
    ]);

    try {
      const source = streamChat(sessionId, userText, handleEvent, () =>
        setLoading(false)
      );
      source.addEventListener("error", () => setLoading(false));
      source.addEventListener("open", () => setLoading(true));
    } catch (err) {
      console.error(err);
      setLoading(false);
    }
  };

  const handleApproval = async (requestId: string, approved: boolean) => {
    await submitApproval(requestId, approved);
    setPendingApprovals((prev) => {
      const next = { ...prev };
      delete next[requestId];
      return next;
    });
  };

  return (
    <div className="app">
      <header className="header">
        <h1>QuantMind</h1>
        <span className="subtitle">AI quant trading assistant</span>
      </header>

      <main className="chat">
        <div className="messages">
          {messages.map((m) => (
            <div
              key={m.id}
              className={`message ${m.role === "user" ? "user" : "agent"}`}
            >
              {m.text && <div className="bubble">{m.text}</div>}
              {m.event && <EventRenderer event={m.event} />}
            </div>
          ))}

          {Object.entries(pendingApprovals).map(([requestId, data]) => (
            <ApprovalCard
              key={requestId}
              requestId={requestId}
              toolName={data.tool_name}
              arguments={data.arguments}
              onApprove={() => handleApproval(requestId, true)}
              onReject={() => handleApproval(requestId, false)}
            />
          ))}

          {loading && (
            <div className="message agent">
              <div className="bubble loading">...</div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="input-bar">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Ask QuantMind..."
            disabled={loading}
          />
          <button onClick={send} disabled={loading || !input.trim()}>
            Send
          </button>
        </div>
      </main>
    </div>
  );
}

export default App;
