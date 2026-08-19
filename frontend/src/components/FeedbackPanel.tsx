import { CheckCircle2, Gavel } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TitleIcon } from "@/components/ui/title-icon";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

const VERDICTS = [
  { value: "CONFIRMED_FRAUD", label: "Confirm fraud", variant: "destructive" as const },
  { value: "CONFIRMED_LEGITIMATE", label: "Confirm legitimate", variant: "default" as const },
  { value: "UNCERTAIN", label: "Mark uncertain", variant: "secondary" as const },
];

export function FeedbackPanel({ applicationId }: { applicationId: string }) {
  const [notes, setNotes] = useState("");
  const [recorded, setRecorded] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(verdict: string) {
    setBusy(true);
    try {
      const result = await api.submitFeedback(applicationId, verdict, notes);
      setRecorded(result.verdict);
      toast.success("Verdict recorded", {
        description: `${result.verdict.replace(/_/g, " ")} — this feedback feeds the retraining loop.`,
      });
    } catch (e) {
      toast.error("Could not record feedback", { description: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <TitleIcon icon={Gavel} tone="slate" />
          Investigator verdict
        </CardTitle>
      </CardHeader>
      <CardContent>
        {recorded ? (
          <div className="flex items-center gap-2.5 rounded-md border border-emerald-900 bg-emerald-950/40 p-3 text-sm">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            <span>
              Recorded: <span className="font-semibold">{recorded.replace(/_/g, " ")}</span>.
              This verdict is stored and will inform the next retraining cycle.
            </span>
          </div>
        ) : (
          <div className="space-y-3">
            <Input
              placeholder="Optional notes (e.g. verified employment by phone)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              maxLength={2000}
            />
            <div className="flex flex-wrap gap-2">
              {VERDICTS.map((v) => (
                <Button
                  key={v.value}
                  variant={v.variant}
                  disabled={busy}
                  onClick={() => submit(v.value)}
                >
                  {v.label}
                </Button>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
