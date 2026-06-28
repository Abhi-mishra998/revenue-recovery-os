import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { LayoutDashboard, FileText, Receipt, Users, LogOut, Menu, X, Command } from "lucide-react";

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
    <div className="min-h-screen" style={{ background: "var(--bg)" }}>
      {/* Mobile header */}
      <header className="md:hidden sticky top-0 z-40 px-4 py-3 flex items-center justify-between" style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
        <div className="flex items-center gap-2">
          <button
            className="p-2 -ml-2 rounded-md hover:bg-zinc-100"
            onClick={() => setMobileOpen(true)}
            data-testid="mobile-nav-open"
            aria-label="Open menu"
          >
            <Menu className="w-5 h-5" />
          </button>
          <Brand small />
        </div>
        <button onClick={onLogout} className="p-2 rounded-md hover:bg-zinc-100" data-testid="logout-btn-mobile" aria-label="Sign out">
          <LogOut className="w-4 h-4 text-zinc-600" />
        </button>
      </header>

      {/* Mobile drawer */}
      {mobileOpen && (
        <>
          <div className="mobile-nav-overlay md:hidden" onClick={closeMobile} />
          <aside className="mobile-nav-panel md:hidden flex flex-col" data-testid="mobile-nav-panel">
            <div className="px-5 py-5 flex items-center justify-between" style={{ borderBottom: "1px solid var(--border)" }}>
              <Brand />
              <button className="p-1 rounded-md hover:bg-zinc-100" onClick={closeMobile} data-testid="mobile-nav-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <nav className="px-3 py-4 space-y-0.5 flex-1">
              <NavItems onClick={closeMobile} />
            </nav>
            <UserFooter user={user} onLogout={onLogout} />
          </aside>
        </>
      )}

      <div className="md:flex">
        {/* Desktop sidebar */}
        <aside className="hidden md:flex md:flex-col md:w-[256px] md:shrink-0 md:min-h-screen" style={{ background: "var(--surface)", borderRight: "1px solid var(--border)" }}>
          <div className="px-5 py-5" style={{ borderBottom: "1px solid var(--border)" }}>
            <Brand />
          </div>
          <nav className="px-3 py-4 flex-1 space-y-0.5">
            <NavItems />
          </nav>
          <UserFooter user={user} onLogout={onLogout} />
        </aside>

        {/* Main */}
        <main className="flex-1 min-w-0" data-page-enter>
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
      <div
        className={`${small ? "w-7 h-7" : "w-8 h-8"} rounded-md grid place-items-center text-white brand-mark-anim`}
        style={{ background: "var(--primary)", boxShadow: "var(--shadow-xs)" }}
      >
        <Command className={small ? "w-3.5 h-3.5" : "w-4 h-4"} strokeWidth={2.4} />
      </div>
      <div className="leading-tight">
        <div className={`${small ? "text-[15px]" : "text-[16px]"} font-semibold text-zinc-900`}>Revora</div>
        <div className="text-[10px] uppercase tracking-[0.08em] text-zinc-500 mt-0.5">Revenue OS</div>
      </div>
    </div>
  );
}

function UserFooter({ user, onLogout }) {
  return (
    <div className="px-3 pb-4 pt-3" style={{ borderTop: "1px solid var(--border)" }}>
      <div className="px-2.5 py-2 rounded-md flex items-center gap-2.5" style={{ background: "var(--surface-2)" }}>
        <div className="w-7 h-7 rounded-full grid place-items-center text-[11px] font-medium text-zinc-700" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          {(user?.name || user?.email || "U").slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[12.5px] font-medium text-zinc-900 truncate" data-testid="current-user-name">{user?.name || "User"}</div>
          <div className="text-[11px] text-zinc-500 truncate">{user?.email}</div>
        </div>
      </div>
      {user?.auth_provider === "google" && (
        <div className="px-2.5 mt-1.5 text-[10px] text-zinc-500 inline-flex items-center gap-1">
          <span className="dot" style={{ background: "var(--green)" }} /> Signed in with Google
        </div>
      )}
      <button className="revora-sidebar-link w-full mt-2" onClick={onLogout} data-testid="logout-btn">
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
      <Icon className="w-[15px] h-[15px]" strokeWidth={1.75} />
      <span>{label}</span>
    </NavLink>
  );
}
