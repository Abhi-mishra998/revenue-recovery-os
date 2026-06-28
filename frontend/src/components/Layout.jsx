import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { LayoutDashboard, FileText, Receipt, Users, LogOut, Sparkles } from "lucide-react";

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen grain-bg">
      <div className="flex">
        {/* Sidebar */}
        <aside className="w-60 shrink-0 border-r border-stone-200 bg-white/60 backdrop-blur-sm min-h-screen flex flex-col">
          <div className="px-5 py-6 border-b border-stone-200">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-md bg-stone-900 text-amber-50 grid place-items-center font-serif-display text-lg">R</div>
              <div>
                <div className="font-serif-display text-xl leading-none">Revora</div>
                <div className="text-[10px] uppercase tracking-[0.22em] text-stone-500 mt-1">Revenue Recovery OS</div>
              </div>
            </div>
          </div>

          <nav className="px-3 py-4 flex-1 space-y-1">
            <SideLink to="/" icon={LayoutDashboard} label="Dashboard" testId="nav-dashboard" end />
            <SideLink to="/proposals" icon={FileText} label="Proposals" testId="nav-proposals" />
            <SideLink to="/invoices" icon={Receipt} label="Invoices" testId="nav-invoices" />
            <SideLink to="/clients" icon={Users} label="Clients" testId="nav-clients" />
          </nav>

          <div className="px-3 pb-4">
            <div className="px-3 py-3 rounded-md border border-stone-200 bg-amber-50/60">
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-amber-800">
                <Sparkles className="w-3.5 h-3.5" />
                AI Drafts on
              </div>
              <p className="text-xs text-stone-600 mt-1.5 leading-snug">
                Copy-to-send drafts powered by Claude Sonnet 4.5.
              </p>
            </div>
            <div className="mt-3 px-3">
              <div className="text-xs text-stone-700 font-medium" data-testid="current-user-name">{user?.name}</div>
              <div className="text-[11px] text-stone-500 truncate">{user?.email}</div>
            </div>
            <button
              className="revora-sidebar-link w-full mt-2"
              onClick={onLogout}
              data-testid="logout-btn"
            >
              <LogOut className="w-4 h-4" /> Sign out
            </button>
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function SideLink({ to, icon: Icon, label, testId, end }) {
  return (
    <NavLink
      to={to}
      end={end}
      data-testid={testId}
      className={({ isActive }) => `revora-sidebar-link ${isActive ? "active" : ""}`}
    >
      <Icon className="w-4 h-4" />
      <span>{label}</span>
    </NavLink>
  );
}
