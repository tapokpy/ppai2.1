import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { DocumentSummary, listDocuments } from "../api";

export default function DocumentsList() {
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [error, setError] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const navigate = useNavigate();

  useEffect(() => {
    listDocuments({ source: sourceFilter || undefined })
      .then((res) => setDocuments(res.items))
      .catch(() => setError("Не удалось загрузить документы."));
  }, [sourceFilter]);

  return (
    <div className="page">
      <Link className="back-link" to="/">
        ← к сообщениям
      </Link>
      <div className="header">
        <h1>Документы в базе знаний</h1>
        <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
          <option value="">Все источники</option>
          <option value="project_docs">project_docs</option>
          <option value="pdf_upload">pdf_upload</option>
          <option value="harvested">harvested</option>
        </select>
      </div>

      {error && <p className="error">{error}</p>}
      {!error && documents === null && <p className="muted">Загрузка...</p>}
      {documents !== null && documents.length === 0 && <p className="muted">Документов пока нет.</p>}

      {documents !== null && documents.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Источник</th>
              <th>Файл</th>
              <th>Чанков</th>
              <th>Добавлен</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((d) => (
              <tr key={d.id} className="clickable" onClick={() => navigate(`/documents/${d.id}`)}>
                <td>
                  <span className="badge">{d.source}</span>
                </td>
                <td>{d.filename ?? "—"}</td>
                <td className="muted">{d.chunk_count}</td>
                <td className="muted">{new Date(d.created_at).toLocaleString("ru-RU")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
