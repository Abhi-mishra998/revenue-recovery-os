import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { lazy, Suspense, useEffect, useState } from "react";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { Toaster } from "sonner";
import "@/App.css";

// Eager-load the first-paint critical surface — auth, onboarding, layout chrome.
// These are the pages a cold visitor lands on. Keeping them in main.js means
// they render without a network round-trip for a chunk.
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Welcome from "@/pages/Welcome";

// Lazy-load everything else. Each page becomes its own chunk that Vercel/CDN
// caches separately, and the user only downloads what they navigate to.
// Reduces main.js by ~225 KiB per the Lighthouse audit, which is what was
// dominating LCP at 6.1 s.
const AuthCallback = lazy(() => import("@/pages/AuthCallback"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Proposals = lazy(() => import("@/pages/Proposals"));
const ProposalDetail = lazy(() => import("@/pages/ProposalDetail"));
const Invoices = lazy(() => import("@/pages/Invoices"));
const Clients = lazy(() => import("@/pages/Clients"));
const ClientDetail = lazy(() => import("@/pages/ClientDetail"));
const Admin = lazy(() => import("@/pages/Admin"));
const Settings = lazy(() => import("@/pages/Settings"));
const RevenueHealth = lazy(() => import("@/pages/RevenueHealth"));

// Minimum-friction fallback — reserved space (no layout shift), brief spinner.
function PageFallback() {
  return (
    <div className="min-h-screen grid place-items-center" data-testid="route-loading">
      <div className="flex flex-col items-center gap-3 text-zinc-500">
        <div className="revora-spinner" />
        <div className="text-[12px] uppercase tracking-[0.16em]">Loading</div>
      </div>
    </div>
  );
}

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
    return (
      <Suspense fallback={<PageFallback />}>
        <AuthCallback />
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<PageFallback />}>
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
    </Suspense>
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
