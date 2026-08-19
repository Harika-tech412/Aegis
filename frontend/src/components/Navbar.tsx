import { LogOut, ShieldCheck } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

export function Navbar() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
        <Link to="/dashboard" className="flex items-center gap-2.5">
          <ShieldCheck className="h-5 w-5 text-amber-400" />
          <span className="text-lg font-semibold tracking-tight">Aegis</span>
          <span className="mt-0.5 hidden text-xs uppercase tracking-widest text-muted-foreground sm:inline">
            Trust Intelligence
          </span>
        </Link>
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground">
            Investigator: <span className="text-foreground">{username}</span>
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              logout();
              navigate("/");
            }}
          >
            <LogOut className="h-4 w-4" /> Log out
          </Button>
        </div>
      </div>
    </header>
  );
}
