import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AuditLogSummary, listAuditLog } from "../api";

function statusBadgeClass(status: string): string {
  return status === "error" ? "badge error" : "badge rag";
}

export default function AuditLogList() {
  const [entries, setEntries] = useState<AuditLogSummary[] | null>(null);
  const [error, setError] = useState<string>("");
  const [moduleFilter, setModuleFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  useEffect(() => {
    listAuditLog({ module: moduleFilter || undefined, statusFilter: statusFilter || undefined })
      .then((res) => setEntries(res.items))
      .catch(() => setError("Не удалось загрузить журнал действий."));
  }, [moduleFilter, statusFilter]);

  return (
    <div className="page">
      <Link className="back-link" to="/">
        ← к сообщениям
      </Link>
      <div className="header">
        <h1>Журнал действий Локи</h1>
        <div>
          <select value={moduleFilter} onChange={(e) => setModuleFilter(e.target.value)}>
            <option value="">Все модули</option>
            <option value="cascade_router">cascade_router</option>
            <option value="warehouse">warehouse</option>
            <option value="projects">projects</option>
          </select>{" "}
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">Любой статус</option>
            <option value="success">success</option>
            <option value="error">error</option>
          </select>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {!error && entries === null && <p className="muted">Загрузка...</p>}
      {entries !== null && entries.length === 0 && <p className="muted">Записей пока нет.</p>}

      {entries !== null && entries.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Время</th>
              <th>Модуль</th>
              <th>Решение</th>
              <th>Статус</th>
              <th>Команда</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <td className="muted">{new Date(e.created_at).toLocaleString("ru-RU")}</td>
                <td>{e.module}</td>
                <td>{e.decision}</td>
                <td>
                  <span className={statusBadgeClass(e.status)}>{e.status}</span>
                </td>
                <td className="muted">{e.command_text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
