import { AlertTriangle, BadgeCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { IdentityCheck } from "@/lib/types";

export function IdentityPanel({
  identityCheck,
  idDocumentFilename,
}: {
  identityCheck: IdentityCheck | null;
  idDocumentFilename: string | null;
}) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageMissing, setImageMissing] = useState(false);

  useEffect(() => {
    let revoked: string | null = null;
    if (idDocumentFilename) {
      api
        .getIdImageUrl(idDocumentFilename)
        .then((url) => {
          revoked = url;
          setImageUrl(url);
        })
        // Custom uploads are previewed client-side at scoring time and not
        // retained server-side; only sample documents are re-servable here.
        .catch(() => setImageMissing(true));
    }
    return () => {
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [idDocumentFilename]);

  if (!identityCheck && !idDocumentFilename) return null;

  const mismatch = identityCheck?.mismatch ?? false;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Identity verification</CardTitle>
      </CardHeader>
      <CardContent>
        {identityCheck && identityCheck.id_document_name && (
          <div
            className={`mb-4 flex items-start gap-2.5 rounded-md border p-3 text-sm ${
              mismatch
                ? "border-red-800 bg-red-950/50 text-red-300"
                : "border-emerald-900 bg-emerald-950/40 text-emerald-300"
            }`}
          >
            {mismatch ? (
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            ) : (
              <BadgeCheck className="mt-0.5 h-4 w-4 shrink-0" />
            )}
            <span>
              {mismatch
                ? "The name on the submitted ID does NOT match the declared applicant — rule-based identity signal applied (+0.30 risk)."
                : "The name on the submitted ID matches the declared applicant."}
            </span>
          </div>
        )}

        <div className="flex flex-wrap items-start gap-5">
          {imageUrl && (
            <img
              src={imageUrl}
              alt="Submitted synthetic ID document"
              className="w-64 max-w-full rounded-md border border-border"
            />
          )}
          {imageMissing && (
            <p className="w-64 rounded-md border border-border bg-secondary/30 p-3 text-xs text-muted-foreground">
              Document image not retained — custom uploads are previewed at scoring time only;
              sample documents remain viewable.
            </p>
          )}

          {identityCheck && (
            <div className="grid min-w-[220px] flex-1 grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground">
                  Form name
                </p>
                <p className="mt-1 font-medium">{identityCheck.applicant_name ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground">
                  ID name
                </p>
                <p className={`mt-1 font-medium ${mismatch ? "text-red-300" : ""}`}>
                  {identityCheck.id_document_name ?? "—"}
                </p>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
