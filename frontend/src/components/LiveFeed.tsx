import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { BandBadge } from "@/components/BandBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import type { ApplicationSummary } from "@/lib/types";
import { formatMoney, formatTime } from "@/lib/utils";

const POLL_MS = 3500;

export function LiveFeed({
  onData,
  pollMs = POLL_MS,
}: {
  onData?: (total: number) => void;
  pollMs?: number;
}) {
  const [rows, setRows] = useState<ApplicationSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newIds, setNewIds] = useState<Set<string>>(new Set());
  const knownIds = useRef<Set<string> | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const data = await api.listApplications({ limit: 14 });
        if (cancelled) return;
        setError(null);
        onData?.(data.total);

        // Highlight rows that were not present on the previous poll — this is
        // the "live" moment: a freshly scored application fades in.
        if (knownIds.current) {
          const fresh = new Set(
            data.items.filter((r) => !knownIds.current!.has(r.id)).map((r) => r.id)
          );
          if (fresh.size > 0) setNewIds(fresh);
        }
        knownIds.current = new Set(data.items.map((r) => r.id));
        setRows(data.items);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    }

    poll();
    const timer = setInterval(poll, pollMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [onData, pollMs]);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Live application feed</CardTitle>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
          <span className="font-semibold tracking-wider text-emerald-400">LIVE</span>
          <span>· every {pollMs / 1000}s</span>
        </span>
      </CardHeader>
      <CardContent className="p-0">
        {error && (
          <p className="px-5 py-6 text-sm text-red-400">
            Could not load the application feed — {error}
          </p>
        )}
        {!error && rows === null && (
          <div className="space-y-2 px-5 pb-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        )}
        {!error && rows !== null && (
          <div className="feed-scroll max-h-[430px] overflow-x-auto overflow-y-auto">
            <Table className="min-w-[640px]">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Received</TableHead>
                  <TableHead>Applicant</TableHead>
                  <TableHead>Requested</TableHead>
                  <TableHead>Purpose</TableHead>
                  <TableHead className="text-right">Risk</TableHead>
                  <TableHead>Decision</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow
                    key={row.id}
                    onClick={() => navigate(`/applications/${row.id}`)}
                    className={`cursor-pointer odd:bg-secondary/20 ${
                      newIds.has(row.id) ? "animate-feed-in" : ""
                    }`}
                  >
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {formatTime(row.created_at)}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      {row.applicant_age}y · {formatMoney(row.annual_income)} ·{" "}
                      {row.employment_type.replace("_", " ")}
                    </TableCell>
                    <TableCell>{formatMoney(row.requested_amount)}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {row.loan_purpose.replace("_", " ")}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.calibrated_risk_score !== null
                        ? row.calibrated_risk_score.toFixed(3)
                        : "—"}
                    </TableCell>
                    <TableCell>
                      <BandBadge band={row.decision_band} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
