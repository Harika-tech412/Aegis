/**
 * Public applicant view — a generic "QuickLend" digital loan application.
 *
 * Deliberately carries NO Aegis branding: this is the fraudster's side of the
 * split-screen demo. The form genuinely instruments applicant behaviour
 * (session timer, mouse-movement counter, paste counter) — the same signals
 * the model was trained on are measured live from the person filling it in.
 */

import { CheckCircle2, FileText, Landmark, Loader2, UploadCloud, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const EMPLOYMENT = ["salaried", "self_employed", "gig_worker", "unemployed"];
const PURPOSES = [
  "debt_consolidation",
  "home_improvement",
  "medical",
  "education",
  "business",
  "other",
];

interface FormState {
  full_name: string;
  date_of_birth: string;
  pan_number: string;
  email: string;
  mobile: string;
  address: string;
  city: string;
  state: string;
  pin_code: string;
  employment_type: string;
  employer_name: string;
  monthly_income_inr: string;
  years_in_employment: string;
  loan_amount_inr: string;
  loan_purpose: string;
  purpose_text: string;
}

const EMPTY: FormState = {
  full_name: "",
  date_of_birth: "",
  pan_number: "",
  email: "",
  mobile: "",
  address: "",
  city: "",
  state: "",
  pin_code: "",
  employment_type: "salaried",
  employer_name: "",
  monthly_income_inr: "",
  years_in_employment: "",
  loan_amount_inr: "",
  loan_purpose: "home_improvement",
  purpose_text: "",
};

const LEGIT_BASE: Partial<FormState> = {
  date_of_birth: "1988-06-14",
  pan_number: "ABCDE1234F",
  email: "applicant@example.in",
  mobile: "98200 12345",
  address: "42, Lakeview Residency, Baner Road",
  city: "Pune",
  state: "Maharashtra",
  pin_code: "411045",
  employment_type: "salaried",
  employer_name: "Trantow-Torphy Group",
  monthly_income_inr: "95000",
  years_in_employment: "5",
  loan_amount_inr: "450000",
  loan_purpose: "home_improvement",
  purpose_text: "Replacing the roof and rewiring the kitchen before the monsoon.",
};

function randomId(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

const inputCls =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 transition-colors placeholder:text-slate-400 focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600/25";
const labelCls = "mb-1.5 block text-xs font-medium tracking-wide text-slate-600";

export function Apply() {
  const [form, setForm] = useState<FormState>({ ...EMPTY });
  const [idFile, setIdFile] = useState<File | null>(null);
  const [idPreview, setIdPreview] = useState<string | null>(null);
  const [idVerify, setIdVerify] = useState<
    { name: string | null; method?: string } | "checking" | null
  >(null);
  const [addressFile, setAddressFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const [helperOpen, setHelperOpen] = useState(true);
  const [scenario, setScenario] = useState<string | null>(null);

  // ---- Real behavioral instrumentation ----
  const sessionStart = useRef(Date.now());
  const mouseEvents = useRef(0);
  const pasteEvents = useRef(0);
  const deviceRef = useRef(randomId("web_device"));
  const ipRef = useRef(randomId("web_ip"));
  const velocityOverride = useRef<number | null>(null);

  useEffect(() => {
    let last = 0;
    const onMove = () => {
      const now = performance.now();
      if (now - last > 50) {
        mouseEvents.current += 1;
        last = now;
      }
    };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  const set = (key: keyof FormState, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  // -------------------------------------------------------------------------
  // Scripted demo-bot channel (only ever driven by the /demo page's Fraud Bot
  // Console, same-origin). This is form-filling automation — a script doing
  // what a fraudster's hands would do. Detection downstream is untouched.
  // -------------------------------------------------------------------------
  useEffect(() => {
    async function onMessage(event: MessageEvent) {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type !== "aegis:botFill") return;

      const profile = event.data.profile as Record<string, any>;
      const notify = (stage: string, detail?: Record<string, unknown>) =>
        window.parent?.postMessage(
          { type: "aegis:botProgress", stage, ...detail },
          window.location.origin
        );

      try {
        setConfirmation(null);
        setError(null);
        setHelperOpen(false);
        setScenario(profile.scenario);
        deviceRef.current = profile.device_id;
        ipRef.current = profile.ip_hash;
        velocityOverride.current = profile.applications_from_device_last_24h ?? null;

        // Field-by-field fill, visible but brisk (~2.5s for 16 fields).
        const started = performance.now();
        const order: (keyof FormState)[] = [
          "full_name", "date_of_birth", "pan_number", "email", "mobile",
          "address", "city", "state", "pin_code", "employment_type",
          "employer_name", "monthly_income_inr", "years_in_employment",
          "loan_amount_inr", "loan_purpose", "purpose_text",
        ];
        setForm({ ...EMPTY });
        for (const key of order) {
          const value = profile[key];
          if (value === undefined || value === null) continue;
          set(key, String(value));
          await new Promise((r) => setTimeout(r, 150));
        }

        // Attach the scenario's document through the same path the manual
        // sample-ID buttons use.
        let attached: File | null = null;
        if (profile.id_document) {
          const blob = await fetch(
            `${API}/demo/id-image/${profile.id_document.filename}`
          ).then((r) => r.blob());
          attached = new File([blob], profile.id_document.filename, { type: "image/png" });
          setIdFile(attached);
          setIdPreview(URL.createObjectURL(blob));
          setIdVerify({ name: profile.id_document.id_name, method: "synthetic_template" });
        } else {
          setIdFile(null);
          setIdPreview(null);
          setIdVerify(null);
        }

        const elapsed = ((performance.now() - started) / 1000).toFixed(1);
        notify("filled", { fields: order.length, seconds: elapsed });

        // The bot's intended behavioural fingerprint replaces this page's
        // live human-interaction measurements (see submitApplication).
        const reference = await submitApplication(
          {
            ...profile,
            monthly_income_inr: Number(profile.monthly_income_inr),
            years_in_employment: Number(profile.years_in_employment ?? 0),
            loan_amount_inr: Number(profile.loan_amount_inr),
            scenario: undefined,
            scenario_label: undefined,
            scenario_description: undefined,
            id_document: undefined,
          },
          attached
        );
        notify("submitted", { reference });
      } catch (err) {
        notify("error", { message: (err as Error).message });
      }
    }

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form]);

  async function attachSampleId(mismatching: boolean) {
    const sample = await fetch(
      `${API}/demo/sample-id?scenario=${mismatching ? "mismatching" : "matching"}`
    ).then((r) => r.json());
    const blob = await fetch(`${API}/demo/id-image/${sample.filename}`).then((r) => r.blob());
    const file = new File([blob], sample.filename, { type: "image/png" });
    setIdFile(file);
    setIdPreview(URL.createObjectURL(blob));
    setIdVerify({ name: sample.id_name });
    return sample;
  }

  async function preset(kind: "legit" | "idfraud" | "ring") {
    setError(null);
    setScenario(kind);
    velocityOverride.current = null;
    deviceRef.current = randomId("web_device");
    ipRef.current = randomId("web_ip");

    if (kind === "legit") {
      const sample = await attachSampleId(false);
      setForm({ ...EMPTY, ...LEGIT_BASE, full_name: sample.applicant_name } as FormState);
    } else if (kind === "idfraud") {
      const sample = await attachSampleId(true);
      // The fraudster claims identity X but presents a document printed for Y.
      setForm({
        ...EMPTY,
        ...LEGIT_BASE,
        full_name: sample.applicant_name,
        monthly_income_inr: "180000",
        loan_amount_inr: "1500000",
        purpose_text: "Personal use of funds.",
      } as FormState);
    } else {
      const ring = await fetch(`${API}/demo/ring-device`).then((r) => r.json());
      deviceRef.current = ring.device_id;
      ipRef.current = ring.ip_hash;
      velocityOverride.current = Math.min(9, ring.known_ring_size);
      setIdFile(null);
      setIdPreview(null);
      setIdVerify(null);
      setForm({
        ...EMPTY,
        ...LEGIT_BASE,
        full_name: "Rohan Malhotra",
        employment_type: "gig_worker",
        monthly_income_inr: "140000",
        loan_amount_inr: "1200000",
        loan_purpose: "business",
        purpose_text: "Working capital for a new venture.",
      } as FormState);
    }
  }

  async function onIdChosen(file: File | undefined) {
    if (!file) return;
    setIdFile(file);
    setIdPreview(URL.createObjectURL(file));
    setIdVerify("checking");
    try {
      const fd = new FormData();
      fd.append("id_document", file);
      const result = await fetch(`${API}/public/verify-id`, { method: "POST", body: fd }).then(
        (r) => r.json()
      );
      setIdVerify({ name: result.name ?? null, method: result.extraction_method });
    } catch {
      setIdVerify({ name: null, method: "failed" });
    }
  }

  /**
   * @param overrides  Supplied only by the scripted demo bot. The bot's whole
   *   point is a specific behavioural fingerprint (5-second session, no mouse,
   *   everything pasted), and this page's live instrumentation — built to
   *   measure a real human — would otherwise record whatever the scripted fill
   *   happened to produce. So the bot's intended values replace the measured
   *   ones. Nothing downstream is affected: the request is the same multipart
   *   POST /public/apply a real applicant sends.
   */
  async function submitApplication(
    overrides?: Record<string, unknown>,
    fileOverride?: File | null
  ): Promise<string> {
    const payload = {
      ...form,
      monthly_income_inr: Number(form.monthly_income_inr),
      years_in_employment: Number(form.years_in_employment || 0),
      loan_amount_inr: Number(form.loan_amount_inr),
      device_id: deviceRef.current,
      ip_hash: ipRef.current,
      session_duration_seconds: Math.max(
        1,
        Math.round((Date.now() - sessionStart.current) / 1000)
      ),
      mouse_movement_events: mouseEvents.current,
      form_paste_count: pasteEvents.current,
      ...(velocityOverride.current
        ? {
            applications_from_device_last_24h: velocityOverride.current,
            applications_from_ip_last_24h: velocityOverride.current,
          }
        : {}),
      ...(overrides ?? {}),
    };
    const fd = new FormData();
    fd.append("payload", JSON.stringify(payload));
    const attachment = fileOverride !== undefined ? fileOverride : idFile;
    if (attachment) fd.append("id_document", attachment);
    if (addressFile) fd.append("address_proof", addressFile);

    const response = await fetch(`${API}/public/apply`, { method: "POST", body: fd });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(
        typeof detail.detail === "string" ? detail.detail : "Submission failed. Please retry."
      );
    }
    const body = await response.json();
    setConfirmation(body.reference);
    return body.reference as string;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await submitApplication();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // ---- Confirmation screen: all the applicant ever sees ----
  if (confirmation) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
        <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <CheckCircle2 className="mx-auto mb-4 h-14 w-14 text-emerald-500" />
          <h1 className="text-xl font-semibold text-slate-900">Application received</h1>
          <p className="mt-2 text-sm text-slate-600">
            Reference: <span className="font-mono font-semibold text-slate-900">{confirmation}</span>
          </p>
          <p className="mt-3 text-sm leading-relaxed text-slate-500">
            Thank you for choosing QuickLend. Our team will review your application and you will
            hear back within 24 hours.
          </p>
          <button
            onClick={() => {
              setConfirmation(null);
              setForm({ ...EMPTY });
              setIdFile(null);
              setIdPreview(null);
              setIdVerify(null);
              setScenario(null);
              sessionStart.current = Date.now();
              mouseEvents.current = 0;
              pasteEvents.current = 0;
              deviceRef.current = randomId("web_device");
              ipRef.current = randomId("web_ip");
              velocityOverride.current = null;
            }}
            className="mt-6 text-sm font-medium text-blue-700 hover:underline"
          >
            Submit another application →
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="min-h-screen bg-slate-100 pb-16 text-slate-900"
      onPaste={() => (pasteEvents.current += 1)}
    >
      {/* Bank header — no Aegis branding on the applicant side */}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-14 max-w-3xl items-center gap-2.5 px-4">
          <Landmark className="h-6 w-6 text-blue-700" />
          <span className="text-lg font-semibold tracking-tight text-slate-900">
            QuickLend <span className="font-normal text-slate-500">Digital Loans</span>
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 pt-6">
        {/* Demo helper strip */}
        {helperOpen && (
          <div className="mb-5 rounded-lg border border-dashed border-violet-300 bg-violet-50 p-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wider text-violet-700">
                Demo mode — quick-fill scenarios
              </p>
              <button onClick={() => setHelperOpen(false)} className="text-violet-400 hover:text-violet-700">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                onClick={() => preset("legit")}
                className="rounded-md border border-emerald-300 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50"
              >
                Legitimate applicant
              </button>
              <button
                onClick={() => preset("idfraud")}
                className="rounded-md border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
              >
                Identity fraud attempt
              </button>
              <button
                onClick={() => preset("ring")}
                className="rounded-md border border-orange-300 bg-white px-3 py-1.5 text-xs font-medium text-orange-700 hover:bg-orange-50"
              >
                Fraud ring member
              </button>
              {scenario && (
                <span className="self-center text-xs text-violet-600">
                  loaded: {scenario === "legit" ? "legitimate" : scenario === "idfraud" ? "identity fraud" : "ring member"}
                </span>
              )}
            </div>
          </div>
        )}

        <h1 className="text-2xl font-semibold text-slate-900">Personal Loan Application</h1>
        <p className="mt-1 text-sm text-slate-500">
          Complete all sections. Fields marked * are required.
        </p>

        <form onSubmit={submit} className="mt-5 space-y-5">
          {/* Section 1 */}
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-sm font-semibold text-slate-800">1 · Personal Information</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className={labelCls}>Full name (as per PAN) *</label>
                <input className={inputCls} required value={form.full_name} onChange={(e) => set("full_name", e.target.value)} />
              </div>
              <div>
                <label className={labelCls}>Date of birth *</label>
                <input type="date" className={inputCls} required value={form.date_of_birth} onChange={(e) => set("date_of_birth", e.target.value)} />
              </div>
              <div>
                <label className={labelCls}>PAN number *</label>
                <input className={inputCls} required maxLength={10} placeholder="ABCDE1234F" value={form.pan_number} onChange={(e) => set("pan_number", e.target.value.toUpperCase())} />
              </div>
              <div>
                <label className={labelCls}>Email *</label>
                <input type="email" className={inputCls} required value={form.email} onChange={(e) => set("email", e.target.value)} />
              </div>
              <div>
                <label className={labelCls}>Mobile *</label>
                <input className={inputCls} required value={form.mobile} onChange={(e) => set("mobile", e.target.value)} />
              </div>
            </div>
          </section>

          {/* Section 2 */}
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-sm font-semibold text-slate-800">2 · Address</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="sm:col-span-3">
                <label className={labelCls}>Current address *</label>
                <textarea className={`${inputCls} min-h-[64px]`} required value={form.address} onChange={(e) => set("address", e.target.value)} />
              </div>
              <div>
                <label className={labelCls}>City *</label>
                <input className={inputCls} required value={form.city} onChange={(e) => set("city", e.target.value)} />
              </div>
              <div>
                <label className={labelCls}>State *</label>
                <input className={inputCls} required value={form.state} onChange={(e) => set("state", e.target.value)} />
              </div>
              <div>
                <label className={labelCls}>PIN code *</label>
                <input className={inputCls} required maxLength={6} value={form.pin_code} onChange={(e) => set("pin_code", e.target.value)} />
              </div>
            </div>
          </section>

          {/* Section 3 */}
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-sm font-semibold text-slate-800">3 · Employment & Income</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className={labelCls}>Employment type *</label>
                <select className={inputCls} value={form.employment_type} onChange={(e) => set("employment_type", e.target.value)}>
                  {EMPLOYMENT.map((t) => (
                    <option key={t} value={t}>{t.replace("_", " ")}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelCls}>Employer name *</label>
                <input className={inputCls} required value={form.employer_name} onChange={(e) => set("employer_name", e.target.value)} />
              </div>
              <div>
                <label className={labelCls}>Monthly income (₹) *</label>
                <input type="number" min={1} className={inputCls} required value={form.monthly_income_inr} onChange={(e) => set("monthly_income_inr", e.target.value)} />
              </div>
              <div>
                <label className={labelCls}>Years in current employment</label>
                <input type="number" min={0} step={0.5} className={inputCls} value={form.years_in_employment} onChange={(e) => set("years_in_employment", e.target.value)} />
              </div>
            </div>
          </section>

          {/* Section 4 */}
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-sm font-semibold text-slate-800">4 · Loan Details</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className={labelCls}>Loan amount requested (₹) *</label>
                <input type="number" min={1} className={inputCls} required value={form.loan_amount_inr} onChange={(e) => set("loan_amount_inr", e.target.value)} />
              </div>
              <div>
                <label className={labelCls}>Purpose *</label>
                <select className={inputCls} value={form.loan_purpose} onChange={(e) => set("loan_purpose", e.target.value)}>
                  {PURPOSES.map((p) => (
                    <option key={p} value={p}>{p.replace("_", " ")}</option>
                  ))}
                </select>
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls}>Briefly describe why you need this loan</label>
                <textarea className={`${inputCls} min-h-[56px]`} value={form.purpose_text} onChange={(e) => set("purpose_text", e.target.value)} />
              </div>
            </div>
          </section>

          {/* Section 5 */}
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-1 text-sm font-semibold text-slate-800">5 · Document Upload</h2>
            <p className="mb-4 text-xs text-slate-500">Captured for KYC compliance.</p>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <div>
                <label className={labelCls}>Identity proof (PAN / Aadhaar / Driving License)</label>
                <label className="flex cursor-pointer items-center gap-2 rounded-md border border-dashed border-slate-300 bg-slate-50 px-3 py-3 text-sm text-slate-600 hover:border-blue-500">
                  <UploadCloud className="h-4 w-4" />
                  {idFile ? idFile.name : "Choose image (PNG/JPG)"}
                  <input type="file" accept="image/png,image/jpeg" className="hidden" onChange={(e) => onIdChosen(e.target.files?.[0])} />
                </label>
                {idPreview && (
                  <div className="mt-3">
                    <img src={idPreview} alt="ID preview" className="h-24 rounded border border-slate-200" />
                    <div
                      className={`mt-2 rounded-md border px-3 py-2 text-xs ${
                        idVerify !== "checking" && idVerify && !idVerify.name
                          ? "border-amber-300 bg-amber-50 text-amber-800"
                          : "border-blue-200 bg-blue-50 text-blue-800"
                      }`}
                    >
                      {idVerify === "checking" ? (
                        <span className="flex items-center gap-1.5">
                          <Loader2 className="h-3 w-3 animate-spin" /> Verifying document…
                        </span>
                      ) : idVerify?.name ? (
                        // Both extraction strategies report the name the same
                        // way — we don't overclaim confidence for either.
                        <>
                          Verify ID: document reads{" "}
                          <span className="font-semibold">{idVerify.name}</span>
                        </>
                      ) : (
                        <>
                          Extraction uses a deep-learning OCR model calibrated for real-world
                          document conditions, but this document could not be read. Very heavy
                          glare, extreme angles, or non-English-only text may still fail — for
                          guaranteed results, use the sample ID buttons above.
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
              <div>
                <label className={labelCls}>Address proof (Utility bill / Bank statement)</label>
                <label className="flex cursor-pointer items-center gap-2 rounded-md border border-dashed border-slate-300 bg-slate-50 px-3 py-3 text-sm text-slate-600 hover:border-blue-500">
                  <FileText className="h-4 w-4" />
                  {addressFile ? addressFile.name : "Choose file"}
                  <input type="file" className="hidden" onChange={(e) => setAddressFile(e.target.files?.[0] ?? null)} />
                </label>
              </div>
            </div>
          </section>

          {error && (
            <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-blue-700 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:bg-blue-800 hover:shadow disabled:opacity-60 sm:w-auto sm:px-10"
          >
            {busy ? "Submitting…" : "Submit Application"}
          </button>
        </form>

        <p className="mt-8 text-center text-xs text-slate-400">
          QuickLend Digital Loans · Demonstration environment · all data is synthetic ·{" "}
          <Link to="/" className="underline">staff sign-in</Link>
        </p>
      </main>
    </div>
  );
}
