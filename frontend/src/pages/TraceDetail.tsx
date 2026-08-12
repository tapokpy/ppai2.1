import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRagTrace, RagTrace } from "../api";

const EVENT_LABELS: Record<string, string> = {
  retrieval_started: "Поиск начат",
  query_embedded: "Запрос эмбеддирован",
  retrieval_results: "Результаты поиска",
  chunks_selected: "Чанки выбраны",
  context_built: "Контекст собран",
  llm_called: "Вызов модели",
  answer_generated: "Ответ сгенерирован",
};

function RetrievedChunks({ retrieved }: { retrieved: any[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Score</th>
          <th>Файл</th>
          <th>Фрагмент</th>
        </tr>
      </thead>
      <tbody>
        {retrieved.map((r, i) => (
          <tr key={i}>
            <td>{typeof r.score === "number" ? r.score.toFixed(2) : "?"}</td>
            <td className="muted">{r.metadata?.filename ?? "—"}</td>
            <td className="muted">{r.snippet}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function TraceDetail() {
  const { messageId } = useParams();
  const [trace, setTrace] = useState<RagTrace | null>(null);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    if (!messageId) return;
    getRagTrace(Number(messageId))
      .then(setTrace)
      .catch(() => setError("Не удалось загрузить трейс."));
  }, [messageId]);

  return (
    <div className="page">
      <Link className="back-link" to="/">
        ← к списку сообщений
      </Link>
      <div className="header">
        <h1>Трейс #{messageId}</h1>
      </div>

      {error && <p className="error">{error}</p>}
      {!error && !trace && <p className="muted">Загрузка...</p>}

      {trace && (
        <>
          <div className="card">
            <p>
              <strong>Вопрос:</strong> {trace.prompt}
            </p>
            <p className="muted">
              source: {trace.source}
              {trace.timing &&
                " · " +
                  Object.entries(trace.timing)
                    .map(([k, v]) => `${k.replace("_seconds", "")} ${v}с`)
                    .join(" + ")}
            </p>
            {trace.rag_trace_id && <p className="muted">trace_id: {trace.rag_trace_id}</p>}
          </div>

          <div className="timeline">
            {trace.events.map((event) => (
              <div className="timeline-event" key={event.seq}>
                <div className="name">
                  {event.seq}. {EVENT_LABELS[event.event_name] ?? event.event_name}
                </div>
                {event.event_name === "retrieval_results" && Array.isArray((event.payload as any).retrieved) ? (
                  <RetrievedChunks retrieved={(event.payload as any).retrieved} />
                ) : (
                  <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
