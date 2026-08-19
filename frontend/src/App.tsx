import { Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider, useAuth } from "@/context/AuthContext";
import { ApplicationDetail } from "@/pages/ApplicationDetail";
import { Dashboard } from "@/pages/Dashboard";
import { Login } from "@/pages/Login";

function Protected({ children }: { children: JSX.Element }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route
          path="/dashboard"
          element={
            <Protected>
              <Dashboard />
            </Protected>
          }
        />
        <Route
          path="/applications/:id"
          element={
            <Protected>
              <ApplicationDetail />
            </Protected>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <Toaster theme="dark" position="bottom-right" richColors />
    </AuthProvider>
  );
}
