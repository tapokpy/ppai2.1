import { Navigate, Route, Routes } from "react-router-dom";
import { getToken } from "./api";
import Login from "./pages/Login";
import MessagesList from "./pages/MessagesList";
import TraceDetail from "./pages/TraceDetail";
import DocumentsList from "./pages/DocumentsList";
import DocumentDetail from "./pages/DocumentDetail";

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <MessagesList />
          </RequireAuth>
        }
      />
      <Route
        path="/trace/:messageId"
        element={
          <RequireAuth>
            <TraceDetail />
          </RequireAuth>
        }
      />
      <Route
        path="/documents"
        element={
          <RequireAuth>
            <DocumentsList />
          </RequireAuth>
        }
      />
      <Route
        path="/documents/:documentId"
        element={
          <RequireAuth>
            <DocumentDetail />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
