import { ChevronDown, LogOut, MonitorPlay, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ArchitectureDialog } from "@/components/ArchitectureDialog";
import { useAuth } from "@/context/AuthContext";

function initials(name: string | null): string {
  if (!name) return "??";
  const parts = name.trim().split(/[\s_.-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

export function Navbar() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();
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
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
        <Link to="/dashboard" className="flex min-w-0 items-center gap-2.5">
          <ShieldCheck className="h-5 w-5 shrink-0 text-amber-400" />
          <span className="text-lg font-semibold tracking-tight">Aegis</span>
          <span className="mt-0.5 hidden text-[11px] uppercase tracking-[0.14em] text-muted-foreground lg:inline">
            Trust Intelligence
          </span>
        </Link>

        <div className="flex items-center gap-2 sm:gap-3">
          <Link
            to="/demo"
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-amber-500/50 bg-amber-500/10 px-2.5 text-sm font-semibold text-amber-300 transition-colors hover:bg-amber-500/20 sm:px-3"
          >
            <MonitorPlay className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Live Demo</span>
          </Link>

          <ArchitectureDialog />

          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="flex items-center gap-2 rounded-lg py-1 pl-1 pr-1.5 transition-colors hover:bg-secondary/60"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-[11px] font-semibold text-amber-300">
                {initials(username)}
              </span>
              <span className="hidden text-sm text-foreground md:inline">{username}</span>
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
                  <p className="text-sm font-medium text-foreground">{username}</p>
                  <p className="text-xs text-muted-foreground">Fraud investigator</p>
                </div>
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    logout();
                    navigate("/");
                  }}
                  className="mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-foreground transition-colors hover:bg-secondary/70"
                >
                  <LogOut className="h-4 w-4 text-muted-foreground" /> Log out
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
