import { AlertTriangle, BadgeCheck, Copy, ScanFace } from "lucide-react";
import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TitleIcon } from "@/components/ui/title-icon";
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
        .catch(() => setImageMissing(true));
    }
    return () => {
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [idDocumentFilename]);

  if (!identityCheck && !idDocumentFilename) return null;

  const mismatch = identityCheck?.mismatch ?? false;
  const reused = identityCheck?.reused_across_names ?? false;
  const priorNames = identityCheck?.prior_names ?? [];
  const verified =
    identityCheck?.id_document_name && identityCheck.applicant_name && !mismatch && !reused;

  const rows: { label: string; form: string | null | undefined; doc: string | null | undefined; alert?: boolean }[] = [
    {
      label: "Name",
      form: identityCheck?.applicant_name,
      doc: identityCheck?.id_document_name,
      alert: mismatch,
    },
    { label: "Date of birth", form: identityCheck?.form_dob, doc: identityCheck?.ocr_dob },
    { label: "ID number", form: "—", doc: identityCheck?.ocr_id_number },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <TitleIcon icon={ScanFace} tone="brand" />
          Identity verification
        </CardTitle>
        <p className="aegis-section-desc mt-1">Document OCR compared against the declared applicant</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {mismatch && (
          <div className="flex items-start gap-2.5 rounded-md border border-danger/50 bg-danger/10 p-3.5 text-sm font-medium text-danger">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
            <span>
              IDENTITY MISMATCH DETECTED — OCR-extracted name on the document does not match the
              applicant's declared name.
            </span>
          </div>
        )}
        {reused && (
          <div className="flex items-start gap-2.5 rounded-md border border-danger/50 bg-danger/10 p-3.5 text-sm font-medium text-danger">
            <Copy className="mt-0.5 h-5 w-5 shrink-0" />
            <span>
              ID IMAGE REUSED — this same document image has been submitted with{" "}
              {priorNames.length} other name{priorNames.length === 1 ? "" : "s"}:{" "}
              <span className="font-semibold">{priorNames.join(", ") || "unknown"}</span>{" "}
              (perceptual-hash match across {identityCheck?.prior_uses ?? 0} prior upload
              {(identityCheck?.prior_uses ?? 0) === 1 ? "" : "s"}).
            </span>
          </div>
        )}
        {verified && (
          <div className="flex items-center gap-2 rounded-md border border-success/40 bg-success/10 px-3 py-2 text-sm text-success">
            <BadgeCheck className="h-4 w-4" /> Identity verified — document name matches the
            applicant.
          </div>
        )}

        <div className="flex flex-wrap items-start gap-5">
          {imageUrl && (
            <img
              src={imageUrl}
              alt="Submitted ID document (synthetic)"
              className="w-72 max-w-full rounded-md border border-border"
            />
          )}
          {imageMissing && (
            <p className="w-64 rounded-md border border-border bg-secondary/30 p-3 text-xs text-muted-foreground">
              Document image not available for this application.
            </p>
          )}

          {identityCheck && (
            <div className="min-w-[260px] flex-1 overflow-hidden rounded-md border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-secondary/40 text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-3 py-2 font-medium">Field</th>
                    <th className="px-3 py-2 font-medium">Form said</th>
                    <th className="px-3 py-2 font-medium">ID document said</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.label} className="border-b border-border/60 last:border-0">
                      <td className="px-3 py-2 text-muted-foreground">{r.label}</td>
                      <td className="px-3 py-2">{r.form || "—"}</td>
                      <td className={`px-3 py-2 ${r.alert ? "font-semibold text-danger" : ""}`}>
                        {r.doc || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
