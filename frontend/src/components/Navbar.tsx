import { Building2, ChevronDown, LayoutDashboard, LogOut, MonitorPlay, Share2, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ArchitectureDialog } from "@/components/ArchitectureDialog";
import { useAuth } from "@/context/AuthContext";
import { useInstitution } from "@/context/InstitutionContext";

function initials(name: string | null): string {
  if (!name) return "??";
  const parts = name.trim().split(/[\s_.-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/demo", label: "Live Demo", icon: MonitorPlay },
  { to: "/network", label: "Network", icon: Share2 },
];

export function Navbar() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { code, displayName, options, setCode } = useInstitution();
  const [instOpen, setInstOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-4 sm:px-6">
        {/* Brand mark */}
        <Link to="/dashboard" className="flex min-w-0 shrink-0 items-center gap-2.5">
          <span className="icon-chip icon-chip-brand">
            <ShieldCheck className="h-4 w-4" strokeWidth={2} />
          </span>
          <span className="flex flex-col leading-none">
            <span className="text-base font-bold tracking-tight text-foreground">AEGIS</span>
            <span className="mt-0.5 hidden text-[10px] font-semibold uppercase tracking-[0.14em] text-subtle sm:inline">
              Trust Intelligence
            </span>
          </span>
        </Link>

        {/* Primary navigation with a brand-blue active state */}
        <nav className="flex min-w-0 flex-1 items-center gap-1">
          {NAV.map(({ to, label, icon: Icon }) => {
            const active = pathname === to || pathname.startsWith(`${to}/`);
            return (
              <Link
                key={to}
                to={to}
                aria-current={active ? "page" : undefined}
                className={`inline-flex h-9 items-center gap-2 rounded-lg px-3 text-sm font-medium transition-colors ${
                  active
                    ? "bg-brand/10 text-brand"
                    : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
                }`}
              >
                <Icon className="h-4 w-4" strokeWidth={2} />
                <span className="hidden sm:inline">{label}</span>
              </Link>
            );
          })}
          <ArchitectureDialog />
        </nav>

        {/* Investigator */}
        {/* Institution switcher — re-scopes the whole investigator surface. */}
        <div className="relative shrink-0">
          <button
            onClick={() => setInstOpen((v) => !v)}
            className="flex items-center gap-2 rounded-lg border border-border bg-card px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-border-emphasis"
            aria-haspopup="menu"
            aria-expanded={instOpen}
          >
            <Building2 className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={2} />
            <span className="hidden sm:inline">{displayName}</span>
            <ChevronDown
              className={`h-3 w-3 text-muted-foreground transition-transform ${
                instOpen ? "rotate-180" : ""
              }`}
            />
          </button>
          {instOpen && (
            <div role="menu" className="aegis-surface absolute right-0 z-50 mt-1.5 w-56 p-1">
              <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-subtle">
                Viewing as institution
              </p>
              {options.map((option) => (
                <button
                  key={option.code}
                  onClick={() => {
                    setCode(option.code);
                    setInstOpen(false);
                  }}
                  className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-secondary/70 ${
                    option.code === code ? "text-brand" : "text-foreground"
                  }`}
                >
                  {option.display_name}
                  {option.code === code && <span className="text-xs">active</span>}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="relative shrink-0" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2 rounded-lg py-1 pl-1 pr-1.5 transition-colors hover:bg-secondary/60"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand/15 text-[11px] font-bold text-brand">
              {initials(username)}
            </span>
            <span className="hidden text-sm font-medium text-foreground md:inline">{username}</span>
            <ChevronDown
              className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${
                menuOpen ? "rotate-180" : ""
              }`}
            />
          </button>

          {menuOpen && (
            <div
              role="menu"
              className="aegis-surface absolute right-0 z-50 mt-1.5 w-52 overflow-hidden p-1"
            >
              <div className="border-b border-border px-3 py-2">
                <p className="text-sm font-semibold text-foreground">{username}</p>
                <p className="text-xs text-subtle">Fraud investigator</p>
              </div>
              <button
                onClick={() => {
                  setMenuOpen(false);
                  logout();
                  navigate("/");
                }}
                className="mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm font-medium text-foreground transition-colors hover:bg-secondary/70"
              >
                <LogOut className="h-4 w-4 text-muted-foreground" /> Log out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
