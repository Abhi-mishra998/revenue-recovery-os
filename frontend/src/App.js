import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { lazy, Suspense, useEffect, useState } from "react";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import "@/App.css";

// Eager-load the first-paint critical surface — auth, onboarding, layout chrome.
// Lazy-loading Login moved framer-motion out of main.js but inflated LCP (chunk
// download added latency) and caused CLS (splash → Login swap). Lighthouse
// regression confirmed: 79 → 54. Keeping the entry routes eager — the framer
// cost is paid by Login itself only.
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Welcome from "@/pages/Welcome";

// Lazy-load everything else. Each page becomes its own chunk that Vercel/CDN
// caches separately, and the user only downloads what they navigate to.
//
// We name each loader (the `() => import(...)` arrow) so we can reuse it for
// hover-prefetch — see `preload` below. Clicking a sidebar link with the chunk
// already in cache feels instant (no network round-trip on nav).
const loadAuthCallback = () => import("@/pages/AuthCallback");
const loadDashboard = () => import("@/pages/Dashboard");
const loadProposals = () => import("@/pages/Proposals");
const loadProposalDetail = () => import("@/pages/ProposalDetail");
const loadInvoices = () => import("@/pages/Invoices");
const loadClients = () => import("@/pages/Clients");
const loadClientDetail = () => import("@/pages/ClientDetail");
const loadAdmin = () => import("@/pages/Admin");
const loadSettings = () => import("@/pages/Settings");
const loadRevenueHealth = () => import("@/pages/RevenueHealth");
const loadToaster = () => import("sonner").then((m) => ({ default: m.Toaster }));

const AuthCallback = lazy(loadAuthCallback);
const Dashboard = lazy(loadDashboard);
const Proposals = lazy(loadProposals);
const ProposalDetail = lazy(loadProposalDetail);
const Invoices = lazy(loadInvoices);
const Clients = lazy(loadClients);
const ClientDetail = lazy(loadClientDetail);
const Admin = lazy(loadAdmin);
const Settings = lazy(loadSettings);
const RevenueHealth = lazy(loadRevenueHealth);
const LazyToaster = lazy(loadToaster);

// Sidebar hover-prefetch: Layout.jsx calls preload[key]?.() on mouseEnter so the
// route chunk is downloaded before the user clicks. Idempotent — webpack dedupes
// repeat imports of the same module.
export const preload = {
  dashboard: loadDashboard,
  health: loadRevenueHealth,
  proposals: loadProposals,
  clients: loadClients,
  invoices: loadInvoices,
  settings: loadSettings,
  admin: loadAdmin,
};

// Skeleton that mirrors the real Layout footprint (sidebar + main) so when the
// page chunk lands and Layout swaps in, there's zero layout shift. CLS was 0.329
// before this — almost all of it came from centered-spinner → sidebar-layout swap.
function LayoutSkeleton({ testId = "route-loading" }) {
  return (
    <div className="min-h-screen md:flex" style={{ background: "var(--bg)" }} data-testid={testId}>
      <aside className="hidden md:block md:w-[256px] md:shrink-0 md:min-h-screen" style={{ background: "var(--surface)", borderRight: "1px solid var(--border)" }} />
      <main className="flex-1 min-w-0 grid place-items-center">
        <div className="flex flex-col items-center gap-3 text-zinc-500">
          <div className="revora-spinner" />
          <div className="text-[12px] uppercase tracking-[0.16em]">Loading</div>
        </div>
      </main>
    </div>
  );
}

function PageFallback() {
  return <LayoutSkeleton testId="route-loading" />;
}

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <LayoutSkeleton testId="auth-loading" />;
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
        {/* Toaster lazy-loaded so sonner (~10 KiB) doesn't pin in main.js. A
            null fallback is fine — no toast fires before user interaction, and
            the chunk is well in flight by the time anyone clicks anything. */}
        <Suspense fallback={null}>
          <LazyToaster richColors position="top-right" />
        </Suspense>
        <AppRouter />
      </BrowserRouter>
    </AuthProvider>
  );
}
