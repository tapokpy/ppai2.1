import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { exchangeOtt, setToken } from "../api";

export default function Login() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<"exchanging" | "error" | "idle">("idle");
  const [error, setError] = useState<string>("");

  const ott = searchParams.get("ott");

  useEffect(() => {
    if (!ott) {
      return;
    }
    setStatus("exchanging");
    exchangeOtt(ott)
      .then((token) => {
        setToken(token);
        navigate("/", { replace: true });
      })
      .catch(() => {
        setStatus("error");
        setError("Ссылка недействительна или истекла. Запросите новую командой /dashboard в Telegram.");
      });
  }, [ott, navigate]);

  return (
    <div className="login-box">
      <h1>ppai — RAG панель</h1>
      {!ott && (
        <p className="muted">
          Откройте эту страницу по ссылке из команды <code>/dashboard</code> в Telegram-боте.
        </p>
      )}
      {status === "exchanging" && <p className="muted">Вход...</p>}
      {status === "error" && <p className="error">{error}</p>}
    </div>
  );
}
