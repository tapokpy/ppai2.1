import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DocumentDetail as DocumentDetailData, getDocumentDetail } from "../api";

export default function DocumentDetail() {
  const { documentId } = useParams();
  const [detail, setDetail] = useState<DocumentDetailData | null>(null);
  const [error, setError] = useState<string>("");
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    if (!documentId) return;
    getDocumentDetail(Number(documentId))
      .then(setDetail)
      .catch(() => setError("Не удалось загрузить документ."));
  }, [documentId]);

  return (
    <div className="page">
      <Link className="back-link" to="/documents">
        ← к документам
      </Link>
      <div className="header">
        <h1>{detail?.document.filename ?? `Документ #${documentId}`}</h1>
      </div>

      {error && <p className="error">{error}</p>}
      {!error && !detail && <p className="muted">Загрузка...</p>}

      {detail && (
        <>
          <div className="card">
            <p className="muted">
              источник: {detail.document.source} · эмбеддинг: {detail.embedding_model} · коллекция:{" "}
              {detail.collection} · чанков: {detail.chunks.length}
            </p>
          </div>

          {detail.chunks.map((chunk) => (
            <div
              className="card clickable"
              key={chunk.chunk_id}
              onClick={() => setExpanded(expanded === chunk.chunk_id ? null : chunk.chunk_id)}
            >
              <p className="muted">{chunk.chunk_id}</p>
              <p style={{ margin: 0 }}>
                {expanded === chunk.chunk_id ? chunk.text : `${chunk.text.slice(0, 160)}${chunk.text.length > 160 ? "…" : ""}`}
              </p>
              {expanded === chunk.chunk_id && (
                <pre>{JSON.stringify(chunk.metadata, null, 2)}</pre>
              )}
            </div>
          ))}
        </>
      )}
    </div>
  );
}
