/**
 * Cross-institution network hit callout.
 *
 * Cyan, deliberately: every other alert colour on this page means "Aegis
 * detected this itself". Cyan means "a partner institution detected this, and
 * all we received was a hash".
 */

import { Share2 } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import type { NetworkHit } from "@/lib/types";
import { formatTime } from "@/lib/utils";

const CYAN = "#22D3EE";

const SIGNAL_LABEL: Record<string, string> = {
  DEVICE_HASH: "device fingerprint",
  IP_HASH: "network address",
  ID_DOCUMENT_HASH: "identity document",
};

export function NetworkHitCallout({ hits }: { hits: NetworkHit[] | null | undefined }) {
  if (!hits || hits.length === 0) return null;

  return (
    <Card
      style={{
        borderColor: "rgba(34,211,238,0.45)",
        background:
          "linear-gradient(90deg, rgba(34,211,238,0.10) 0%, rgba(34,211,238,0.02) 60%, transparent 100%)",
      }}
    >
      <CardContent className="flex gap-3.5 p-5">
        <span
          className="icon-chip mt-0.5 shrink-0"
          style={{ background: "rgba(34,211,238,0.14)", color: CYAN }}
        >
          <Share2 className="h-4 w-4" strokeWidth={2} />
        </span>
        <div className="min-w-0 space-y-2">
          <p
            className="text-[11px] font-bold uppercase tracking-[0.14em]"
            style={{ color: CYAN }}
          >
            NETWORK SIGNAL
          </p>
          {hits.map((hit) => (
            <p
              key={`${hit.signal_type}-${hit.matched_hash_prefix}`}
              className="text-sm leading-relaxed text-foreground"
            >
              This applicant&rsquo;s{" "}
              {SIGNAL_LABEL[hit.signal_type] ?? hit.signal_type.toLowerCase()} matches a fraud
              signal published by{" "}
              <span className="font-semibold" style={{ color: CYAN }}>
                {hit.reported_by}
              </span>{" "}
              on {formatTime(hit.fraud_confirmed_at)}. No identity data was shared; only a
              cryptographic match was detected.
            </p>
          ))}
          <p className="font-mono text-xs text-subtle">
            {hits.map((h) => `${h.signal_type} ${h.matched_hash_prefix}…`).join("   ")}
          </p>
          <p className="text-xs text-muted-foreground">
            Each match added +0.30 to the risk score at the rules layer, above the model output.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
