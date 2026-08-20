/**
 * Selected institution — session-scoped React state (never localStorage).
 *
 * Switching institution re-scopes the whole investigator surface: the live
 * feed, the stat counts, everything. Partner Bank A is a real member with its
 * own book of business, not a mocked view.
 */

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

export interface InstitutionOption {
  code: string;
  display_name: string;
}

export const DEFAULT_INSTITUTIONS: InstitutionOption[] = [
  { code: "SYNC_DEMO", display_name: "Synchrony (Demo)" },
  { code: "PARTNER_A", display_name: "Partner Bank A" },
];

interface InstitutionState {
  code: string;
  displayName: string;
  options: InstitutionOption[];
  setCode: (code: string) => void;
}

const InstitutionContext = createContext<InstitutionState | null>(null);

export function InstitutionProvider({ children }: { children: ReactNode }) {
  const [code, setCodeState] = useState("SYNC_DEMO");
  const setCode = useCallback((next: string) => setCodeState(next), []);
  const displayName =
    DEFAULT_INSTITUTIONS.find((i) => i.code === code)?.display_name ?? code;

  return (
    <InstitutionContext.Provider
      value={{ code, displayName, options: DEFAULT_INSTITUTIONS, setCode }}
    >
      {children}
    </InstitutionContext.Provider>
  );
}

export function useInstitution(): InstitutionState {
  const ctx = useContext(InstitutionContext);
  if (!ctx) throw new Error("useInstitution must be used within InstitutionProvider");
  return ctx;
}
