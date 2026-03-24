import { useState, useRef, useEffect } from "react";
import { sendChat } from "../services/api";

// Bold all numbers (integers, decimals, currency amounts) in text
function boldNumbers(text) {
  if (!text) return text;
  const parts = text.split(/(\b\d[\d,]*\.?\d*\b)/g);
  return parts.map((part, i) =>
    /^\d[\d,]*\.?\d*$/.test(part) ? <strong key={i}>{part}</strong> : part
  );
}

export default function ChatPanel() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);

    try {
      const res = await sendChat(text);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: res.answer,
          sql: res.sql,
          results: res.results,
          error: res.error,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Failed to get a response. Check the backend.", error: "network" },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-header">AI Query Assistant</div>
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-hint">
            Ask questions in plain English, e.g.:<br />
            "What are the top 5 customers by total order value?"<br />
            "Show all sales orders that have been delivered but not billed"<br />
            "How many products are assigned to each plant?"
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`chat-msg chat-msg-${msg.role}`}>
            <div className="chat-msg-text">
              {msg.role === "assistant" ? boldNumbers(msg.text) : msg.text}
            </div>
            {msg.sql && (
              <details className="chat-sql">
                <summary>View SQL</summary>
                <pre>{msg.sql}</pre>
              </details>
            )}
            {msg.results && msg.results.length > 0 && (
              <details className="chat-results">
                <summary>{msg.results.length} row{msg.results.length !== 1 ? "s" : ""} returned</summary>
                <div className="chat-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        {Object.keys(msg.results[0]).map((col) => (
                          <th key={col}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {msg.results.slice(0, 20).map((row, ri) => (
                        <tr key={ri}>
                          {Object.values(row).map((val, ci) => (
                            <td key={ci}>{val == null ? "" : String(val)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {msg.results.length > 20 && (
                    <div className="chat-more">...and {msg.results.length - 20} more rows</div>
                  )}
                </div>
              </details>
            )}
          </div>
        ))}
        {loading && (
          <div className="chat-msg chat-msg-assistant">
            <div className="chat-msg-text chat-thinking">Thinking...</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <form className="chat-input" onSubmit={handleSend}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your O2C data..."
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
