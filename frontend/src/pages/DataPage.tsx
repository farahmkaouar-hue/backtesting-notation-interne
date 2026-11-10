import { useRef, useState } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { StatusBadge } from "../components/StatusBadge";
import { api } from "../api/client";

type Step = "upload" | "controls" | "segmentation";

const COLORS = ["#007B7A", "#3BBFBF", "#9BD5D4", "#CBD5E1"];
const DATA_QUALITY_REPORT = { totalLignes: 0, doublons: 0, valeursManquantes: 0, incohérencesDate: 0, dossierExclus: 0, lignesValides: 0, colonnesDetectees: [] as string[], segmentDistribution: [] as { segment: string; count: number }[], alertesQualite: [] as { code: string; message: string; severite: "vert" | "orange" | "rouge" | "nc" }[] };

const STEPS: { id: Step; label: string; short: string }[] = [
  { id: "upload",       label: "Import des données",    short: "Import" },
  { id: "controls",    label: "Contrôles qualité",     short: "Qualité" },
  { id: "segmentation",label: "Segmentation",          short: "Segments" },
];

function StepIndicator({ current }: { current: Step }) {
  const idx = STEPS.findIndex(s => s.id === current);
  return (
    <div className="flex items-center gap-0">
      {STEPS.map((s, i) => {
        const done   = i < idx;
        const active = i === idx;
        return (
          <div key={s.id} className="flex items-center flex-1 min-w-0">
            <div className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold transition-all whitespace-nowrap
              ${active ? "bg-brand-600 text-white shadow-md shadow-brand-200"
              : done   ? "bg-brand-50 text-brand-700"
              :          "text-gray-400"}`}
            >
              {done ? (
                <span className="h-5 w-5 rounded-full bg-brand-100 text-brand-600 flex items-center justify-center shrink-0">
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                </span>
              ) : (
                <span className={`h-5 w-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0
                  ${active ? "bg-white text-brand-700" : "bg-gray-200 text-gray-500"}`}>
                  {i + 1}
                </span>
              )}
              <span className="hidden sm:inline">{s.label}</span>
              <span className="sm:hidden">{s.short}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`flex-1 h-0.5 mx-2 rounded-full transition-all ${done ? "bg-brand-300" : "bg-gray-200"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

interface Props {
  token: string;
  onUploaded: (datasetId: string, report: Record<string, unknown>) => Promise<void>;
}

export function DataPage({ token, onUploaded }: Props) {
  const [step, setStep]           = useState<Step>("upload");
  const [fileLoaded, setFileLoaded] = useState(false);
  const [dragging, setDragging]   = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [liveReport, setLiveReport] = useState<Record<string, unknown> | null>(null);
  const [performanceDate, setPerformanceDate] = useState("");
  const [actualRatingColumn, setActualRatingColumn] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const report = DATA_QUALITY_REPORT;

  async function upload(file?: File) {
    if (!file) return inputRef.current?.click();
    setUploadError("");
    setUploading(true);
    try {
      const response = await api.upload(token, file, performanceDate || undefined, actualRatingColumn || undefined);
      setLiveReport(response.preparation_report);
      await onUploaded(response.dataset_id, response.preparation_report);
      setFileLoaded(true);
      setStep("controls");
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Import impossible.");
    } finally {
      setUploading(false);
    }
  }

  if (liveReport && step !== "upload") {
    const issues = (liveReport.issues ?? {}) as Record<string, unknown>;
    return <div className="flex-1 overflow-y-auto bg-gray-50/60 p-6"><div className="mx-auto max-w-4xl space-y-5"><div><p className="text-xs font-semibold uppercase tracking-widest text-brand-600">Module 1</p><h1 className="mt-1 text-2xl font-semibold text-gray-900">Préparation terminée</h1><p className="mt-1 text-sm text-gray-500">Rapport calculé et enregistré par le backend.</p></div><div className="grid gap-4 sm:grid-cols-3"><ApiMetric label="Lignes importées" value={liveReport.rows}/><ApiMetric label="Lignes éligibles" value={liveReport.eligible}/><ApiMetric label="Défauts observés" value={liveReport.defaults}/></div><div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm"><h2 className="text-sm font-semibold text-gray-800">Anomalies contrôlées</h2><div className="mt-3 space-y-2">{Object.entries(issues).map(([name, value]) => <div key={name} className="flex justify-between rounded-lg bg-gray-50 px-3 py-2 text-sm"><span>{name.replaceAll("_", " ")}</span><b>{String(value)}</b></div>)}</div></div><p className="rounded-xl border border-brand-100 bg-brand-50 p-4 text-sm text-brand-800">Les trois partitions SQL ont été créées à partir du modèle de scoring : Professionnel, Corpo/TPME avec EF et Corpo/TPME sans EF. Passez au module Backtesting pour sélectionner une partition et définir les périodes.</p></div></div>;
  }

  return (
    <div className="flex-1 overflow-y-auto bg-gray-50/60">
      {/* Page header */}
      <div className="bg-gradient-to-r from-brand-900 via-brand-800 to-brand-700 px-6 pt-6 pb-8">
        <div className="max-w-4xl mx-auto">
          <p className="text-brand-300 text-xs font-medium uppercase tracking-widest mb-1">Module 1</p>
          <h1 className="text-2xl font-bold text-white tracking-tight">Données &amp; Préparation</h1>
          <p className="text-brand-200 text-sm mt-1">Import, contrôle qualité et segmentation des données de notation</p>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 -mt-4 pb-10 space-y-5">
        {/* Step indicator card */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm px-5 py-4">
          <StepIndicator current={step} />
        </div>

        {/* ── Step 1: Upload ─────────────────────────────────── */}
        {step === "upload" && (
          <div className="space-y-4">
            <div className="grid gap-4 rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:grid-cols-2">
              <label className="text-sm font-medium text-gray-700">Date de performance (recommandée)
                <input type="date" value={performanceDate} onChange={e => setPerformanceDate(e.target.value)} className="mt-2 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
                <span className="mt-1 block text-xs font-normal text-gray-400">Active le contrôle de look-ahead entre notation et observation.</span>
              </label>
              <label className="text-sm font-medium text-gray-700">Colonne de notation réelle (si ambiguë)
                <input value={actualRatingColumn} onChange={e => setActualRatingColumn(e.target.value)} placeholder="Ex. Rating_réel 082026" className="mt-2 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
                <span className="mt-1 block text-xs font-normal text-gray-400">Laissez vide si une seule colonne est détectée automatiquement.</span>
              </label>
            </div>
            <div
              onDragOver={e => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={e => { e.preventDefault(); setDragging(false); void upload(e.dataTransfer.files[0]); }}
              onClick={() => void upload()}
              className={`group border-2 border-dashed rounded-2xl p-14 text-center cursor-pointer transition-all duration-200
                ${dragging
                  ? "border-brand-400 bg-brand-50 scale-[1.01]"
                  : fileLoaded
                  ? "border-emerald-300 bg-emerald-50"
                  : "border-gray-200 bg-white hover:border-brand-300 hover:bg-brand-50/40 hover:shadow-md"}`}
            >
              {fileLoaded ? (
                <div className="flex flex-col items-center gap-3">
                  <div className="h-14 w-14 rounded-full bg-emerald-100 flex items-center justify-center shadow-inner">
                    <svg className="w-7 h-7 text-emerald-600" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-emerald-800">Fichier importé et contrôlé</p>
                    <p className="text-xs text-emerald-600 mt-0.5">Le rapport de préparation provient de l’API.</p>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-4">
                  <div className="h-16 w-16 rounded-2xl bg-brand-50 border border-brand-100 flex items-center justify-center group-hover:bg-brand-100 transition-colors shadow-sm">
                    <svg className="w-8 h-8 text-brand-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-800">{uploading ? "Import et préparation en cours…" : "Déposez votre fichier Excel ici"}</p>
                    <p className="text-xs text-gray-400 mt-1">ou cliquez pour sélectionner &nbsp;·&nbsp; .xlsx, .xls &nbsp;·&nbsp; max 50 Mo</p>
                  </div>
                  <div className="flex flex-wrap justify-center gap-1.5 mt-1">
                    {["Identifiant crédit", "Modèle de scoring", "Classe de notation finale", "Notation réelle", "Override", "Date de performance"].map(c => (
                      <span key={c} className="text-[10px] font-mono bg-gray-100 text-gray-500 px-2 py-0.5 rounded-md border border-gray-200">
                        {c}
                      </span>
                    ))}
                    <span className="text-[10px] text-gray-400 self-center">+ colonnes optionnelles</span>
                  </div>
                </div>
              )}
              <input ref={inputRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={e => void upload(e.target.files?.[0])} />
            </div>

            {uploadError && <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">{uploadError}</p>}

            <div className="bg-white border border-brand-100 rounded-2xl p-5 shadow-sm">
              <div className="flex items-start gap-3">
                <div className="h-8 w-8 rounded-xl bg-brand-100 flex items-center justify-center shrink-0 mt-0.5">
                  <svg className="w-4 h-4 text-brand-600" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                  </svg>
                </div>
                <div>
                  <p className="text-xs font-bold text-brand-900 mb-1.5">Règle métier — Variable de défaut</p>
                  <p className="text-xs text-brand-700 leading-relaxed">
                    La règle de défaut et la date de performance sont configurées et versionnées côté backend.
                    &nbsp;·&nbsp;
                    <span className="text-brand-500 mt-1 inline-block">Aucune règle ou période fictive n’est appliquée dans l’interface.</span>
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── Step 2: Quality controls ──────────────────────── */}
        {step === "controls" && (
          <div className="space-y-4">
            {/* KPI row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                { label: "Lignes totales",    value: Number(liveReport?.rows ?? report.totalLignes).toLocaleString("fr-FR"), sub: "fichier source",    color: "text-gray-900",   icon: "📄", accent: "border-t-gray-300" },
                { label: "Doublons exclus",   value: String(report.doublons),                    sub: "lignes ignorées",   color: "text-amber-700",  icon: "⚠️", accent: "border-t-amber-300" },
                { label: "Valeurs manquantes",value: String(report.valeursManquantes),            sub: "champs vides",      color: "text-amber-700",  icon: "⚠️", accent: "border-t-amber-300" },
                { label: "Lignes valides",    value: Number(liveReport?.eligible ?? report.lignesValides).toLocaleString("fr-FR"),sub: "prêtes à l'analyse",color: "text-emerald-700", icon: "✅", accent: "border-t-emerald-400" },
              ].map(k => (
                <div key={k.label} className={`bg-white rounded-2xl border border-gray-100 border-t-2 ${k.accent} p-4 shadow-sm hover:shadow-md transition-shadow`}>
                  <p className="text-[10px] text-gray-400 uppercase tracking-widest mb-1">{k.label}</p>
                  <p className={`text-2xl font-bold font-mono ${k.color}`}>{k.value}</p>
                  <p className="text-[10px] text-gray-400 mt-1">{k.sub}</p>
                </div>
              ))}
            </div>

            {/* Alerts */}
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-50">
                <h3 className="text-sm font-semibold text-gray-800">Alertes qualité détectées</h3>
                <p className="text-xs text-gray-400 mt-0.5">Anomalies identifiées lors de l'analyse du fichier importé</p>
              </div>
              <div className="p-4 space-y-2">
                {report.alertesQualite.map(a => (
                  <div key={a.code} className="flex items-start gap-3 p-3.5 rounded-xl bg-gray-50/80 border border-gray-100 hover:border-gray-200 transition-colors">
                    <StatusBadge status={a.severite} size="sm" />
                    <div className="min-w-0">
                      <p className="text-[10px] font-mono text-gray-400 mb-0.5">{a.code}</p>
                      <p className="text-xs text-gray-700 leading-relaxed">{a.message}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Detected columns */}
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-50">
                <h3 className="text-sm font-semibold text-gray-800">
                  Colonnes détectées
                  <span className="ml-2 text-xs font-normal text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                    {report.colonnesDetectees.length}
                  </span>
                </h3>
              </div>
              <div className="p-4 flex flex-wrap gap-1.5">
                {report.colonnesDetectees.map(c => {
                  const isCritical = ["Classe de notation finale", "Notation réelle", "Override", "Modèle de scoring"].includes(c);
                  return (
                    <span key={c} className={`text-[11px] font-mono px-2.5 py-1 rounded-lg border transition-all
                      ${isCritical
                        ? "bg-brand-50 text-brand-700 border-brand-200 font-semibold"
                        : "bg-gray-50 text-gray-500 border-gray-200"}`}>
                      {c}
                    </span>
                  );
                })}
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => setStep("segmentation")}
                className="inline-flex items-center gap-2 bg-brand-600 hover:bg-brand-700 active:bg-brand-800 text-white text-sm font-semibold px-6 py-2.5 rounded-xl shadow-md shadow-brand-200 hover:shadow-lg hover:shadow-brand-300 transition-all"
              >
                Valider et segmenter
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3: Segmentation ─────────────────────────── */}
        {step === "segmentation" && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Pie chart card */}
              <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
                <div className="px-5 py-4 border-b border-gray-50">
                  <h3 className="text-sm font-semibold text-gray-800">Distribution par segment</h3>
                  <p className="text-xs text-gray-400 mt-0.5">Répartition des dossiers selon le modèle de notation</p>
                </div>
                <div className="p-4">
                  <ResponsiveContainer width="100%" height={210}>
                    <PieChart>
                      <Pie
                        data={report.segmentDistribution}
                        dataKey="count"
                        nameKey="segment"
                        cx="50%"
                        cy="48%"
                        outerRadius={76}
                        innerRadius={40}
                        paddingAngle={3}
                        strokeWidth={0}
                      >
                        {report.segmentDistribution.map((_, i) => (
                          <Cell key={i} fill={COLORS[i % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{ fontSize: 11, borderRadius: 10, border: "1px solid #e5e7eb", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
                        formatter={(v: unknown) => [(v as number).toLocaleString("fr-FR") + " dossiers", ""]}
                      />
                      <Legend
                        iconType="circle"
                        iconSize={8}
                        wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="mt-2 space-y-2">
                    {report.segmentDistribution.map((s, i) => (
                      <div key={s.segment} className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: COLORS[i] }} />
                          <span className="text-xs text-gray-600">{s.segment}</span>
                        </div>
                        <span className="text-xs font-mono font-semibold text-gray-800">{s.count.toLocaleString("fr-FR")}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Segment detail cards */}
              <div className="space-y-3">
                {[
                  {
                    title: "Modèle Professionnel",
                    key: "Model_Scoring_Name = 'PRO'",
                    count: 2848,
                    color: COLORS[0],
                    note: "Variables comportementales & relationnelles. Vérifier Turnover et DEER.",
                  },
                  {
                    title: "Corporate avec États Financiers",
                    key: "Model_Scoring_Name = 'CORP_EF'",
                    count: 891,
                    color: COLORS[1],
                    note: "Ratios financiers structurels. Date EF &lt; date notation obligatoire.",
                  },
                  {
                    title: "Corporate sans États Financiers",
                    key: "Model_Scoring_Name = 'CORP_SEF'",
                    count: 643,
                    color: COLORS[2],
                    note: "Indicateurs comportementaux. Vérifier biais de sélection.",
                  },
                ].map(s => (
                  <div key={s.title} className="bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
                    <div className="h-1 w-full" style={{ backgroundColor: s.color }} />
                    <div className="px-4 py-3.5">
                      <div className="flex items-start justify-between gap-3 mb-1.5">
                        <h4 className="text-xs font-bold text-gray-800 leading-snug">{s.title}</h4>
                        <span className="text-base font-mono font-bold shrink-0" style={{ color: s.color }}>
                          {s.count.toLocaleString("fr-FR")}
                        </span>
                      </div>
                      <p className="text-[10px] font-mono text-gray-400 bg-gray-50 px-2 py-0.5 rounded-md inline-block mb-2">{s.key}</p>
                      <p className="text-[11px] text-gray-500 leading-relaxed">{s.note}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Ready banner */}
            <div className="bg-gradient-to-r from-emerald-50 to-teal-50 border border-emerald-200 rounded-2xl p-5">
              <div className="flex items-start gap-3">
                <div className="h-8 w-8 rounded-xl bg-emerald-100 flex items-center justify-center shrink-0 mt-0.5">
                  <svg className="w-4 h-4 text-emerald-600" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-bold text-emerald-900">Données prêtes pour le backtesting</p>
                  <p className="text-xs text-emerald-700 mt-0.5 leading-relaxed">
                    Les effectifs, partitions et contrôles sont affichés uniquement après import et préparation par le backend.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ApiMetric({ label, value }: { label: string; value: unknown }) { return <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm"><p className="text-xs text-gray-500">{label}</p><p className="mt-2 text-2xl font-semibold text-gray-900">{Number(value ?? 0).toLocaleString("fr-FR")}</p></div>; }
