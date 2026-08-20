import { Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider, useAuth } from "@/context/AuthContext";
import { InstitutionProvider } from "@/context/InstitutionContext";
import { ApplicationDetail } from "@/pages/ApplicationDetail";
import { Apply } from "@/pages/Apply";
import { Dashboard } from "@/pages/Dashboard";
import { DemoSplit } from "@/pages/DemoSplit";
import { Login } from "@/pages/Login";
import { NetworkPage } from "@/pages/NetworkPage";

function Protected({ children }: { children: JSX.Element }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <InstitutionProvider>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/apply" element={<Apply />} />
        <Route
          path="/demo"
          element={
            <Protected>
              <DemoSplit />
            </Protected>
          }
        />
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
        <Route
          path="/network"
          element={
            <Protected>
              <NetworkPage />
            </Protected>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </InstitutionProvider>
      <Toaster theme="dark" position="bottom-right" richColors />
    </AuthProvider>
  );
}
