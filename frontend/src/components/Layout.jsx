import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { LayoutDashboard, FileText, Receipt, Users, LogOut, Menu, X } from "lucide-react";

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const onLogout = () => {
    logout();
    navigate("/login");
  };

  const closeMobile = () => setMobileOpen(false);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Mobile header */}
      <header className="md:hidden sticky top-0 z-40 bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            className="p-2 -ml-2 rounded-md hover:bg-slate-100"
            onClick={() => setMobileOpen(true)}
            data-testid="mobile-nav-open"
            aria-label="Open menu"
          >
            <Menu className="w-5 h-5" />
          </button>
          <Brand small />
        </div>
        <button onClick={onLogout} className="p-2 rounded-md hover:bg-slate-100" data-testid="logout-btn-mobile" aria-label="Sign out">
          <LogOut className="w-4 h-4 text-slate-600" />
        </button>
      </header>

      {/* Mobile drawer */}
      {mobileOpen && (
        <>
          <div className="mobile-nav-overlay md:hidden" onClick={() => setMobileOpen(false)} />
          <aside className="mobile-nav-panel md:hidden flex flex-col" data-testid="mobile-nav-panel">
            <div className="px-5 py-5 border-b border-slate-200 flex items-center justify-between">
              <Brand />
              <button className="p-1 rounded-md hover:bg-slate-100" onClick={() => setMobileOpen(false)} data-testid="mobile-nav-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <nav className="px-3 py-4 space-y-1 flex-1">
              <NavItems onClick={closeMobile} />
            </nav>
            <UserFooter user={user} onLogout={onLogout} />
          </aside>
        </>
      )}

      <div className="md:flex">
        {/* Desktop sidebar */}
        <aside className="hidden md:flex md:flex-col md:w-64 md:shrink-0 md:min-h-screen border-r border-slate-200 bg-white">
          <div className="px-5 py-6 border-b border-slate-200">
            <Brand />
          </div>
          <nav className="px-3 py-4 flex-1 space-y-1">
            <NavItems />
          </nav>
          <UserFooter user={user} onLogout={onLogout} />
        </aside>

        {/* Main */}
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function NavItems({ onClick }) {
  return (
    <>
      <SideLink to="/" icon={LayoutDashboard} label="Dashboard" testId="nav-dashboard" end onClick={onClick} />
      <SideLink to="/proposals" icon={FileText} label="Proposals" testId="nav-proposals" onClick={onClick} />
      <SideLink to="/clients" icon={Users} label="Clients" testId="nav-clients" onClick={onClick} />
      <SideLink to="/invoices" icon={Receipt} label="Invoices" testId="nav-invoices" onClick={onClick} />
    </>
  );
}

function Brand({ small }) {
  return (
    <div className="flex items-center gap-2.5" data-testid="brand-logo">
      <div className={`${small ? "w-7 h-7 text-base" : "w-8 h-8 text-lg"} rounded-md bg-indigo-700 text-white grid place-items-center font-bold`}>
        R
      </div>
      <div>
        <div className={`${small ? "text-base" : "text-lg"} font-semibold text-slate-900 leading-none`}>Revora</div>
        <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500 mt-1">Revenue Recovery OS</div>
      </div>
    </div>
  );
}

function UserFooter({ user, onLogout }) {
  return (
    <div className="px-3 pb-4 border-t border-slate-100 pt-3 mt-2">
      <div className="px-2">
        <div className="text-xs font-medium text-slate-800 truncate" data-testid="current-user-name">{user?.name}</div>
        <div className="text-[11px] text-slate-500 truncate">{user?.email}</div>
        {user?.auth_provider === "google" && (
          <div className="text-[10px] mt-1 inline-flex items-center gap-1 text-slate-500">
            <span className="dot" style={{ background: "#0D9488" }} /> Signed in with Google
          </div>
        )}
      </div>
      <button className="revora-sidebar-link w-full mt-3" onClick={onLogout} data-testid="logout-btn">
        <LogOut className="w-4 h-4" /> Sign out
      </button>
    </div>
  );
}

function SideLink({ to, icon: Icon, label, testId, end, onClick }) {
  return (
    <NavLink
      to={to}
      end={end}
      data-testid={testId}
      onClick={onClick}
      className={({ isActive }) => `revora-sidebar-link ${isActive ? "active" : ""}`}
    >
      <Icon className="w-4 h-4" />
      <span>{label}</span>
    </NavLink>
  );
}
