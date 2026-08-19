import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { SimilarCasesResponse } from "@/lib/types";

export function SimilarCasesPanel({
  data,
  loading,
  error,
}: {
  data: SimilarCasesResponse | null;
  loading: boolean;
  error: string | null;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Similar past cases</CardTitle>
      </CardHeader>
      <CardContent>
        {loading && (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        )}
        {error && (
          <p className="text-sm text-red-400">Similar-case search unavailable — {error}</p>
        )}
        {!loading && !error && data && (
          <>
            <p className="mb-4 rounded-md border border-border bg-secondary/40 p-3 text-sm leading-relaxed">
              {data.summary}
              <span className="ml-2 text-xs text-muted-foreground">
                ({data.summary_source === "groq" ? "AI summary" : "generated summary"})
              </span>
            </p>
            <div className="space-y-2">
              {data.matches.map((m) => (
                <button
                  key={m.case_id}
                  onClick={() => setExpanded(expanded === m.case_id ? null : m.case_id)}
                  className="w-full rounded-md border border-border bg-background/40 p-3 text-left transition-colors hover:bg-secondary/40"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                      <span className="font-mono text-sm">{m.case_id}</span>
                      <Badge
                        variant={m.fraud_type === "false_alarm" ? "approve" : "flag"}
                      >
                        {m.fraud_type.replace(/_/g, " ")}
                      </Badge>
                    </div>
                    <span className="flex items-center gap-2 text-xs tabular-nums text-muted-foreground">
                      {(m.similarity_score * 100).toFixed(0)}% match
                      <ChevronDown
                        className={`h-4 w-4 transition-transform ${
                          expanded === m.case_id ? "rotate-180" : ""
                        }`}
                      />
                    </span>
                  </div>
                  {expanded === m.case_id && (
                    <p className="mt-2.5 border-t border-border pt-2.5 text-sm leading-relaxed text-muted-foreground">
                      {m.narrative_text}
                    </p>
                  )}
                </button>
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
