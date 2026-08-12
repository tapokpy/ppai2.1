import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { clearToken, listMessages, MessageSummary } from "../api";

function sourceBadgeClass(source: string): string {
  if (source === "rag") return "badge rag";
  if (source === "local") return "badge local";
  if (source === "cloud") return "badge cloud";
  return "badge";
}

export default function MessagesList() {
  const [messages, setMessages] = useState<MessageSummary[] | null>(null);
  const [error, setError] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const navigate = useNavigate();

  useEffect(() => {
    listMessages({ source: sourceFilter || undefined, limit: 100 })
      .then((res) => setMessages(res.items))
      .catch(() => setError("Не удалось загрузить сообщения. Возможно, сессия истекла."));
  }, [sourceFilter]);

  return (
    <div className="page">
      <div className="header">
        <h1>Сообщения</h1>
        <div>
          <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
            <option value="">Все источники</option>
            <option value="rag">rag</option>
            <option value="local">local</option>
            <option value="cloud">cloud</option>
          </select>{" "}
          <Link to="/documents">Документы</Link>{" "}
          <button
            className="secondary"
            onClick={() => {
              clearToken();
              navigate("/login");
            }}
          >
            Выйти
          </button>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {!error && messages === null && <p className="muted">Загрузка...</p>}
      {messages !== null && messages.length === 0 && <p className="muted">Пока нет сообщений.</p>}

      {messages !== null && messages.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Время</th>
              <th>Источник</th>
              <th>Вопрос</th>
              <th>Контекст</th>
            </tr>
          </thead>
          <tbody>
            {messages.map((m) => (
              <tr key={m.id} className="clickable" onClick={() => navigate(`/trace/${m.id}`)}>
                <td className="muted">{new Date(m.created_at).toLocaleString("ru-RU")}</td>
                <td>
                  <span className={sourceBadgeClass(m.source)}>{m.source}</span>
                </td>
                <td>{m.prompt}</td>
                <td className="muted">{m.context_used ? "да" : "нет"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
