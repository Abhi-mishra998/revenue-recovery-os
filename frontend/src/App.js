import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { Toaster } from "sonner";
import "@/App.css";

import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import AuthCallback from "@/pages/AuthCallback";
import Dashboard from "@/pages/Dashboard";
import Proposals from "@/pages/Proposals";
import ProposalDetail from "@/pages/ProposalDetail";
import Invoices from "@/pages/Invoices";
import Clients from "@/pages/Clients";
import ClientDetail from "@/pages/ClientDetail";
import Admin from "@/pages/Admin";
import Settings from "@/pages/Settings";
import Welcome from "@/pages/Welcome";
import RevenueHealth from "@/pages/RevenueHealth";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center" data-testid="auth-loading">
        <div className="flex flex-col items-center gap-3 text-zinc-500">
          <div className="revora-spinner" />
          <div className="text-[12px] uppercase tracking-[0.16em]">Loading workspace</div>
        </div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function PublicOnly({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user) return <Navigate to="/" replace />;
  return children;
}

// Gate every protected app route on has_data — first-time tenants land on /welcome.
// One /onboarding/state call per session; cached in module scope so re-mounts
// don't re-hit the API.
let _cachedHasData = null;
function OnboardingGuard({ children }) {
  const [checked, setChecked] = useState(_cachedHasData !== null);
  useEffect(() => {
    if (_cachedHasData !== null) return;
    api
      .get("/onboarding/state")
      .then((r) => {
        _cachedHasData = !!r.data.has_data;
      })
      .catch(() => {
        _cachedHasData = true; // be permissive on error — don't trap them on /welcome
      })
      .finally(() => setChecked(true));
  }, []);
  if (!checked) return null;
  if (_cachedHasData === false) return <Navigate to="/welcome" replace />;
  return children;
}

function AppRouter() {
  const location = useLocation();
  // Detect Emergent Google OAuth callback synchronously during render to avoid race conditions.
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  if (location.hash && location.hash.includes("session_id=")) {
    return <AuthCallback />;
  }

  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />

      {/* /welcome runs full-bleed (no Layout chrome) so onboarding doesn't show empty sidebar links */}
      <Route path="/welcome" element={<Protected><Welcome /></Protected>} />

      <Route element={<Protected><OnboardingGuard><Layout /></OnboardingGuard></Protected>}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/health" element={<RevenueHealth />} />
        <Route path="/proposals" element={<Proposals />} />
        <Route path="/proposals/:id" element={<ProposalDetail />} />
        <Route path="/invoices" element={<Invoices />} />
        <Route path="/clients" element={<Clients />} />
        <Route path="/clients/:id" element={<ClientDetail />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/settings" element={<Settings />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

// Reset onboarding cache on logout so a fresh login re-checks /onboarding/state.
export function resetOnboardingCache() {
  _cachedHasData = null;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster richColors position="top-right" />
        <AppRouter />
      </BrowserRouter>
    </AuthProvider>
  );
}
