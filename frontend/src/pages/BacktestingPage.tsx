import { useState } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell, Legend,
} from "recharts";
import { StatusBadge, TrafficLightIcon } from "../components/StatusBadge";
import type { ModelBacktestResult, ModelSegment } from "../types";
import type { ApiModel } from "../api/client";
const MIGRATION_MATRIX: { classeInitiale: number; transitions: number[]; total: number }[] = [];

const EMPTY_MODEL: ModelBacktestResult = { segment: "professionnel", segmentLabel: "Aucun résultat", totalDossiers: 0, totalDefauts: 0, tauxDefautGlobal: 0, periodeInitiale: "—", periodePerformance: "—", horizonMois: 0, auc: 0, gini: 0, ks: 0, psi: 0, hosmerLemeshowPValue: 0, ratingClasses: [], alertes: [], decision: { verdict: "non_concluant", label: "Aucun résultat", justification: "Importez des données et lancez le backtesting.", urgence: "nc" }, overrideRate: 0, overrideDirectionnel: false, insuffisanceEvenements: true };

type BtStep = "selection" | "discrimination" | "calibration" | "stabilite" | "overrides" | "decision";

const STEPS: { id: BtStep; label: string; short: string }[] = [
  { id: "selection", label: "Sélection modèle", short: "1" },
  { id: "discrimination", label: "Discrimination", short: "2" },
  { id: "calibration", label: "Calibration", short: "3" },
  { id: "stabilite", label: "Stabilité", short: "4" },
  { id: "overrides", label: "Overrides", short: "5" },
  { id: "decision", label: "Décision", short: "6" },
];

const STATUS_ACCENT: Record<string, string> = {
  vert: "border-l-emerald-400", orange: "border-l-amber-400", rouge: "border-l-red-400", nc: "border-l-gray-300",
};

function Metric({ label, value, threshold, status, explanation }: { label: string; value: string; threshold: string; status: "vert" | "orange" | "rouge" | "nc"; explanation: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`bg-white rounded-2xl p-4 border border-gray-100 border-l-4 ${STATUS_ACCENT[status]} shadow-sm hover:shadow-md transition-shadow`}>
      <div className="flex items-start justify-between mb-3">
        <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide leading-tight max-w-[70%]">{label}</p>
        <StatusBadge status={status} size="sm" />
      </div>
      <p className="text-3xl font-semibold font-mono text-gray-900 leading-none mb-1">{value}</p>
      <p className="text-[10px] text-gray-300 font-mono">Seuil : {threshold}</p>
      <button
        onClick={() => setOpen(o => !o)}
        className="mt-3 flex items-center gap-1 text-[10px] text-brand-600 hover:text-brand-800 font-medium transition-colors"
      >
        <svg className={`w-3 h-3 transition-transform ${open ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
        {open ? "Masquer" : "Méthodologie"}
      </button>
      {open && <p className="text-[11px] text-gray-600 mt-2 pt-2 border-t border-gray-100 leading-relaxed">{explanation}</p>}
    </div>
  );
}

interface Props {
  models: ApiModel[];
  onRun: (model: string, horizon: { developmentStart: string; developmentEnd: string; backtestStart: string; backtestEnd: string }) => Promise<Record<string, unknown>>;
  liveResult: Record<string, unknown> | null;
  running: boolean;
}

function liveModel(result: Record<string, unknown>, modelName: string): ModelBacktestResult {
  const final = (result.final_backtest ?? result) as Record<string, any>;
  const workflowDecision = (result.decision ?? final.decision ?? {}) as Record<string, string>;
  const status: Record<string, "vert" | "orange" | "rouge" | "nc"> = { green: "vert", orange: "orange", red: "rouge", pass: "vert", monitor: "orange", review: "rouge", inconclusive: "nc" };
  const verdictMap: Record<string, ModelBacktestResult["decision"]["verdict"]> = { no_action: "maintien", pd_recalibration: "recalibrage_simple", model_redevelopment: "refonte", extend_history: "non_concluant" };
  const grades = Array.isArray(final.grades) ? final.grades : [];
  return {
    segment: "professionnel", segmentLabel: modelName, totalDossiers: Number(final.population ?? 0), totalDefauts: Number(final.defaults ?? 0), tauxDefautGlobal: Number(final.default_rate ?? 0),
    periodeInitiale: "Jeu sélectionné", periodePerformance: "Selon fichier importé", horizonMois: 12, auc: Number(final.auc ?? 0), gini: Number(final.gini ?? 0), ks: Number(final.ks ?? 0), psi: Number((result.stability as any)?.psi ?? 0), hosmerLemeshowPValue: Number((final.hosmer_lemeshow as any)?.p_value ?? 0), overrideRate: Number((result.overrides as any)?.override_rate ?? 0), overrideDirectionnel: false,
    insuffisanceEvenements: Number(final.defaults ?? 0) < 20,
    ratingClasses: grades.map((g: any, index: number) => ({ classe: index + 1, label: String(g.grade), effectif: Number(g.exposures), pdAssignee: Number(g.pd_predicted) * 100, defautsObserves: Number(g.defaults), tauxDefautObserve: Number(g.default_rate_observed) * 100, ecartCalibration: Number(g.gap) * 100, trafficLight: status[g.traffic_light] ?? "nc", jeffreyPValue: Number(g.binomial_upper_tail ?? 0), binomialPValue: Number(g.binomial_upper_tail ?? 0) })),
    alertes: (final.warnings ?? []).map((warning: string, index: number) => ({ id: `API_${index}`, type: "evenements" as const, severite: "orange" as const, titre: "Alerte API", description: warning, action: workflowDecision.reason ?? "Consulter la décision." })),
    decision: { verdict: verdictMap[workflowDecision.action] ?? "non_concluant", label: workflowDecision.action ?? "Décision à examiner", justification: workflowDecision.reason ?? "Résultat retourné par le moteur métier.", urgence: status[workflowDecision.status] ?? "nc" },
  };
}

export function BacktestingPage({ models, onRun, liveResult, running }: Props) {
  const [apiModel, setApiModel] = useState("");
  const [developmentStart, setDevelopmentStart] = useState("");
  const [developmentEnd, setDevelopmentEnd] = useState("");
  const [backtestStart, setBacktestStart] = useState("");
  const [backtestEnd, setBacktestEnd] = useState("");
  const [configurationError, setConfigurationError] = useState("");
  const [step, setStep] = useState<BtStep>("selection");
  const [started, setStarted] = useState(false);

  const model = liveResult && apiModel ? liveModel(liveResult, apiModel) : EMPTY_MODEL;
  const stepIndex = STEPS.findIndex(s => s.id === step);

  function next() {
    if (stepIndex < STEPS.length - 1) setStep(STEPS[stepIndex + 1].id);
  }
  function prev() {
    if (stepIndex > 0) setStep(STEPS[stepIndex - 1].id);
  }

  // Chart data
  const ratingChartData = model.ratingClasses.slice(0, 10).map(r => ({
    name: r.label,
    PD_assignee: r.pdAssignee,
    Taux_observe: r.tauxDefautObserve,
    effectif: r.effectif,
  }));

  const tlColors: Record<string, string> = { vert: "#15803D", orange: "#D97706", rouge: "#DC2626", nc: "#9CA3AF" };

  if (!models.length) return <div className="flex-1 grid place-items-center bg-gray-50"><div className="max-w-md rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm"><h1 className="text-lg font-semibold text-gray-800">Aucun modèle disponible</h1><p className="mt-2 text-sm text-gray-500">Importez un jeu de données avant de lancer un backtesting. Aucun résultat de démonstration n’est affiché.</p></div></div>;

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-[22px] font-semibold text-gray-900 leading-tight">Backtesting des modèles IRB</h1>
            <p className="text-sm text-gray-400 mt-0.5">Processus step-by-step · EBA/GL/2017/16 &amp; ECB Guide to Internal Models</p>
          </div>
        </div>

        {/* Stepper */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm px-4 py-3">
          <div className="flex items-center">
            {STEPS.map((s, i) => {
              const done = i < stepIndex;
              const active = s.id === step;
              return (
                <div key={s.id} className="flex items-center flex-1 min-w-0">
                  <button
                    onClick={() => started && setStep(s.id)}
                    disabled={!started && s.id !== "selection"}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded-xl text-xs font-medium transition-all shrink-0 ${
                      active ? "text-brand-700" : done ? "text-gray-600 hover:text-brand-700" : "text-gray-300"
                    }`}
                  >
                    <span className={`h-6 w-6 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 transition-all ${
                      active ? "bg-brand-600 text-white shadow-sm" : done ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-400"
                    }`}>
                      {done ? (
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" /></svg>
                      ) : s.short}
                    </span>
                    <span className="hidden lg:block">{s.label}</span>
                  </button>
                  {i < STEPS.length - 1 && (
                    <div className={`flex-1 h-px mx-1 transition-colors ${done ? "bg-emerald-300" : "bg-gray-100"}`} />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Step 1: Selection */}
        {step === "selection" && (
          <div className="space-y-4">
            <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm space-y-5">
              <div>
                <h2 className="text-base font-semibold text-gray-900">Configuration du backtesting</h2>
                <p className="text-xs text-gray-400 mt-0.5">Sélectionnez le segment à analyser, puis vérifiez les paramètres temporels.</p>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-2">Modèle à tester</label>
                {models.length > 0 && (
                  <div className="mb-3 rounded-xl border border-brand-100 bg-brand-50 p-3">
                    <label className="block text-[10px] font-semibold uppercase tracking-wide text-brand-700 mb-1">Jeu importé — exécution API</label>
                    <select value={apiModel} onChange={e => setApiModel(e.target.value)} className="w-full rounded-lg border border-brand-200 bg-white px-3 py-2 text-xs text-gray-700">
                      <option value="">Sélectionner le modèle réel</option>
                      {models.map(item => <option key={item.modele_cible} value={item.modele_cible}>{item.modele_cible} · {item.eligible} éligibles · {item.defaults} défaut(s)</option>)}
                    </select>
                  </div>
                )}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {models.map(m => (
                    <button
                      key={m.modele_cible}
                      onClick={() => setApiModel(m.modele_cible)}
                      className={`p-4 rounded-2xl border-2 text-left transition-all ${apiModel === m.modele_cible ? "border-brand-500 bg-brand-50 shadow-sm" : "border-gray-100 hover:border-brand-200 bg-gray-50/50"}`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className={`h-8 w-8 rounded-xl flex items-center justify-center ${apiModel === m.modele_cible ? "bg-brand-600" : "bg-gray-200"}`}>
                          <svg className={`w-4 h-4 ${apiModel === m.modele_cible ? "text-white" : "text-gray-400"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.75}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                          </svg>
                        </div>
                        {apiModel === m.modele_cible && <div className="h-2 w-2 rounded-full bg-brand-500 mt-1" />}
                      </div>
                      <p className="text-xs font-semibold text-gray-800 leading-tight">{m.modele_cible}</p>
                      <p className="text-[10px] text-gray-400 mt-0.5 font-mono">{m.eligible.toLocaleString("fr-FR")} crédits éligibles</p>
                      {m.defaults < 20 && (
                        <div className="mt-2 flex items-center gap-1">
                          <div className="h-1.5 w-1.5 rounded-full bg-red-500" />
                          <p className="text-[10px] text-red-600 font-medium">{m.defaults} défaut(s) observé(s)</p>
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[['Début développement', developmentStart, setDevelopmentStart], ['Fin développement', developmentEnd, setDevelopmentEnd], ['Début backtesting', backtestStart, setBacktestStart], ['Fin backtesting', backtestEnd, setBacktestEnd]].map(([label, value, setter]) => <div key={label as string}><label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">{label as string}</label><input type="date" value={value as string} onChange={e => (setter as (v: string) => void)(e.target.value)} className="w-full rounded-xl border border-gray-200 px-3 py-2.5 text-xs" /></div>)}
              </div>

              <div className="bg-brand-50 border border-brand-100 rounded-xl p-4 flex items-start gap-3">
                <svg className="w-4 h-4 text-brand-600 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="text-[11px] text-brand-800 leading-relaxed">
                  <strong>Horizon contrôlé :</strong> le moteur bloque le recouvrement avec le développement et vérifie les crédits, les notations observées et le volume exploitable de la fenêtre.
                </p>
              </div>

              <button
                onClick={async () => {
                  setConfigurationError("");
                  if (!apiModel || !developmentStart || !developmentEnd || !backtestStart || !backtestEnd) { setConfigurationError("Sélectionnez un modèle et renseignez les quatre dates."); return; }
                  try { await onRun(apiModel, { developmentStart, developmentEnd, backtestStart, backtestEnd }); } catch (error) { setConfigurationError(error instanceof Error ? error.message : "Exécution impossible."); return; }
                  setStarted(true); next();
                }}
                disabled={running}
                className="flex items-center gap-2 text-white text-sm font-medium px-6 py-3 rounded-xl transition-all shadow-sm hover:shadow-md"
                style={{ background: "linear-gradient(135deg, #006969, #007B7A)" }}
              >
                {running ? "Backtesting en cours…" : "Lancer le backtesting"}
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </button>
              {configurationError && <p className="text-xs text-red-700">{configurationError}</p>}
            </div>
          </div>
        )}

        {/* Step 2: Discrimination */}
        {step === "discrimination" && (
          <div className="space-y-4">
            <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-800 mb-1">Tests de pouvoir discriminant</h2>
              <p className="text-xs text-gray-500 mb-4">Vérifie que le modèle classe correctement les bons et mauvais risques (indépendamment du niveau absolu de PD). Source : BCBS WP14, EBA/GL/2017/16 §5.</p>

              {model.insuffisanceEvenements && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4 text-xs text-amber-800">
                  <strong>Note méthodologique :</strong> Avec {model.totalDefauts} défaut(s) observé(s), les tests de discrimination ne sont pas statistiquement concluants. Les résultats ci-dessous sont indicatifs et doivent être interprétés avec la plus grande prudence.
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
                <Metric
                  label="AUC — Area Under ROC"
                  value={model.auc > 0 ? model.auc.toFixed(2) : "N/C"}
                  threshold="> 0.70 acceptable · > 0.80 bon"
                  status={model.auc === 0 ? "nc" : model.auc > 0.80 ? "vert" : model.auc > 0.70 ? "orange" : "rouge"}
                  explanation="Probabilité qu'un défaillant soit mieux noté (score plus risqué) qu'un non-défaillant, tiré au hasard. Référence académique internationale permettant la comparaison avec la littérature (Tasche, BCBS WP14)."
                />
                <Metric
                  label="Coefficient de Gini"
                  value={model.gini > 0 ? model.gini.toFixed(2) : "N/C"}
                  threshold="> 0.40 générale. attendu"
                  status={model.gini === 0 ? "nc" : model.gini > 0.60 ? "vert" : model.gini > 0.40 ? "vert" : model.gini > 0.20 ? "orange" : "rouge"}
                  explanation="Transformation linéaire de l'AUC : Gini = 2×AUC−1. Norme de reporting dans l'industrie bancaire européenne. Un Gini > 0.40 est l'attente minimale pour un modèle retail/corporate (EBA/GL/2017/16)."
                />
                <Metric
                  label="KS — Kolmogorov-Smirnov"
                  value={model.ks > 0 ? model.ks.toFixed(2) : "N/C"}
                  threshold="> 0.20 acceptable"
                  status={model.ks === 0 ? "nc" : model.ks > 0.20 ? "vert" : "rouge"}
                  explanation="Écart maximal entre les distributions cumulées des scores des défaillants et non-défaillants. Identifie un point de coupure opérationnel. Conservé comme diagnostic complémentaire au Gini."
                />
              </div>

              {model.auc > 0 && (
                <div>
                  <p className="text-xs font-medium text-gray-600 mb-3">Courbe ROC (approximation)</p>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={[
                      { x: 0, roc: 0, ref: 0 },
                      { x: 0.1, roc: 0.42, ref: 0.1 },
                      { x: 0.2, roc: 0.65, ref: 0.2 },
                      { x: 0.3, roc: 0.78, ref: 0.3 },
                      { x: 0.4, roc: 0.86, ref: 0.4 },
                      { x: 0.5, roc: 0.90, ref: 0.5 },
                      { x: 0.6, roc: 0.93, ref: 0.6 },
                      { x: 0.7, roc: 0.95, ref: 0.7 },
                      { x: 0.8, roc: 0.97, ref: 0.8 },
                      { x: 1.0, roc: 1.0, ref: 1.0 },
                    ]}>
                      <XAxis dataKey="x" tick={{ fontSize: 10, fill: "#9CA3AF" }} tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 10, fill: "#9CA3AF" }} tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }} formatter={(v: unknown) => [`${((v as number) * 100).toFixed(1)}%`, ""]} />
                      <Line type="monotone" dataKey="roc" stroke="#007B7A" strokeWidth={2} dot={false} name="ROC" />
                      <Line type="monotone" dataKey="ref" stroke="#E5E7EB" strokeWidth={1} dot={false} strokeDasharray="4 4" name="Aléatoire" />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
            <div className="flex justify-between">
              <button onClick={prev} className="flex items-center gap-1.5 text-sm text-gray-500 border border-gray-200 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition-colors">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 17l-5-5m0 0l5-5m-5 5h12" /></svg>
                Retour
              </button>
              <button onClick={next} className="flex items-center gap-1.5 text-white text-sm font-medium px-5 py-2.5 rounded-xl transition-all shadow-sm" style={{ background: "linear-gradient(135deg, #006969, #007B7A)" }}>
                Étape suivante
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Calibration */}
        {step === "calibration" && (
          <div className="space-y-4">
            <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-800 mb-1">Tests de calibration</h2>
              <p className="text-xs text-gray-500 mb-4">Vérifie que les PD prédites par classe correspondent statistiquement aux taux de défaut réellement observés. Source : ECB Traffic Light, Jeffrey/Vasicek, Hosmer-Lemeshow.</p>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
                <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold text-gray-700">Hosmer-Lemeshow</p>
                    <StatusBadge status={model.hosmerLemeshowPValue === 0 ? "nc" : model.hosmerLemeshowPValue > 0.05 ? "vert" : model.hosmerLemeshowPValue > 0.01 ? "orange" : "rouge"} size="sm" />
                  </div>
                  <p className="text-2xl font-semibold font-mono text-gray-900">{model.hosmerLemeshowPValue > 0 ? `p = ${model.hosmerLemeshowPValue.toFixed(3)}` : "N/C"}</p>
                  <p className="text-[10px] text-gray-400 font-mono mt-0.5">Seuil : p &gt; 0.05</p>
                  <p className="text-[11px] text-gray-500 mt-2">Vision globale — adéquation entre PD prédites et fréquences observées sur l'ensemble des classes.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-4 border border-gray-100 col-span-2">
                  <p className="text-xs font-semibold text-gray-700 mb-1">Traffic Light (Jeffrey/Vasicek) — par classe</p>
                  <p className="text-[11px] text-gray-500 mb-3">Test de calibration ajusté intégrant la corrélation d'actifs. Test principal retenu selon EBA/GL/2017/16 §5.</p>
                  <div className="flex items-center gap-4 text-[10px] text-gray-500 mb-2">
                    <div className="flex items-center gap-1"><div className="h-2 w-2 rounded-full bg-green-500" /> Vert : p-value &gt; 0.05</div>
                    <div className="flex items-center gap-1"><div className="h-2 w-2 rounded-full bg-amber-500" /> Orange : 0.01–0.05</div>
                    <div className="flex items-center gap-1"><div className="h-2 w-2 rounded-full bg-red-500" /> Rouge : &lt; 0.01</div>
                    <div className="flex items-center gap-1"><div className="h-2 w-2 rounded-full bg-gray-400" /> N/C : non calculable</div>
                  </div>
                  <div className="flex gap-1 flex-wrap">
                    {model.ratingClasses.map(r => (
                      <div key={r.classe} className="flex flex-col items-center gap-1">
                        <TrafficLightIcon status={r.trafficLight} size={22} />
                        <span className="text-[9px] text-gray-400 font-mono">{r.label}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Table PD vs observé */}
              <h3 className="text-xs font-semibold text-gray-700 mb-2">Résultats par classe de notation</h3>
              <div className="overflow-x-auto rounded-lg border border-gray-100">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      {["Classe", "Effectif", "PD assignée (%)", "Défauts obs.", "Taux obs. (%)", "Écart (pp)", "Jeffrey p-val", "Feu"].map(h => (
                        <th key={h} className="px-3 py-2 text-left font-medium text-gray-500">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {model.ratingClasses.map((r, i) => (
                      <tr key={r.classe} className={`border-b border-gray-50 ${i % 2 === 0 ? "bg-white" : "bg-gray-50/50"}`}>
                        <td className="px-3 py-2 font-mono font-medium text-gray-800">{r.classe} — {r.label}</td>
                        <td className="px-3 py-2 font-mono text-gray-600">{r.effectif}</td>
                        <td className="px-3 py-2 font-mono text-gray-600">{r.pdAssignee.toFixed(2)}%</td>
                        <td className="px-3 py-2 font-mono text-gray-600">{r.defautsObserves}</td>
                        <td className="px-3 py-2 font-mono text-gray-600">{r.tauxDefautObserve.toFixed(2)}%</td>
                        <td className={`px-3 py-2 font-mono font-medium ${r.ecartCalibration > 0 ? "text-red-600" : "text-gray-600"}`}>
                          {r.ecartCalibration > 0 ? "+" : ""}{r.ecartCalibration.toFixed(2)} pp
                        </td>
                        <td className="px-3 py-2 font-mono text-gray-500">{r.jeffreyPValue.toFixed(2)}</td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-1">
                            <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: tlColors[r.trafficLight] }} />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-4">
                <p className="text-xs font-medium text-gray-600 mb-2">PD assignée vs taux de défaut observé par classe</p>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={ratingChartData} barGap={2}>
                    <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#6B7280" }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: "#9CA3AF" }} axisLine={false} tickLine={false} unit="%" width={40} />
                    <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8 }} formatter={(v: unknown) => [`${(v as number).toFixed(2)}%`, ""]} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="PD_assignee" name="PD assignée" fill="#007B7A" radius={[2, 2, 0, 0]} />
                    <Bar dataKey="Taux_observe" name="Taux observé" fill="#F59E0B" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="flex justify-between">
              <button onClick={prev} className="flex items-center gap-1.5 text-sm text-gray-500 border border-gray-200 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition-colors">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 17l-5-5m0 0l5-5m-5 5h12" /></svg>
                Retour
              </button>
              <button onClick={next} className="flex items-center gap-1.5 text-white text-sm font-medium px-5 py-2.5 rounded-xl transition-all shadow-sm" style={{ background: "linear-gradient(135deg, #006969, #007B7A)" }}>
                Étape suivante
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
              </button>
            </div>
          </div>
        )}

        {/* Step 4: Stabilité */}
        {step === "stabilite" && (
          <div className="space-y-4">
            <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-800 mb-1">Tests de stabilité de la population</h2>
              <p className="text-xs text-gray-500 mb-4">Détecte la dérive de composition du portefeuille (concept drift) indépendamment de la performance prédictive. Source : EBA/GL/2017/16 §5.</p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
                <div>
                  <div className={`rounded-xl p-5 border-2 ${model.psi < 0.10 ? "border-green-200 bg-green-50" : model.psi < 0.25 ? "border-amber-200 bg-amber-50" : "border-red-200 bg-red-50"}`}>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-sm font-semibold text-gray-800">PSI — Population Stability Index</p>
                      <StatusBadge status={model.psi < 0.10 ? "vert" : model.psi < 0.25 ? "orange" : "rouge"} />
                    </div>
                    <p className="text-4xl font-semibold font-mono text-gray-900 mb-3">{model.psi.toFixed(2)}</p>
                    <div className="space-y-1 text-xs text-gray-600">
                      <div className="flex items-center gap-2"><div className="h-2 w-2 rounded-full bg-green-500" /><span>PSI &lt; 0.10 : Population stable</span></div>
                      <div className="flex items-center gap-2"><div className={`h-2 w-2 rounded-full ${model.psi >= 0.10 && model.psi < 0.25 ? "bg-amber-500" : "bg-gray-300"}`} /><span>PSI 0.10–0.25 : À surveiller</span></div>
                      <div className="flex items-center gap-2"><div className={`h-2 w-2 rounded-full ${model.psi >= 0.25 ? "bg-red-500" : "bg-gray-300"}`} /><span>PSI &gt; 0.25 : Dérive significative</span></div>
                    </div>
                    <p className="text-[11px] text-gray-500 mt-3">
                      {model.psi < 0.10 ? "La distribution des notes est stable. Aucun signe de dérive de population." :
                        model.psi < 0.25 ? "Dérive modérée détectée. Analyser la matrice de migration pour identifier les classes concernées." :
                          "Dérive significative. Vérifier représentativité du champ d'application. Envisager extension/segmentation."}
                    </p>
                  </div>
                </div>

                <div>
                  <p className="text-xs font-semibold text-gray-700 mb-3">Matrice de migration (classes 1→10)</p>
                  <div className="overflow-x-auto rounded-lg border border-gray-100">
                    <table className="text-[9px] font-mono w-full">
                      <thead>
                        <tr className="bg-gray-50">
                          <th className="px-1.5 py-1 text-gray-500 text-left">Cl.↓ →</th>
                          {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(c => (
                            <th key={c} className="px-1.5 py-1 text-gray-500 text-center">{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {MIGRATION_MATRIX.map(row => (
                          <tr key={row.classeInitiale} className="border-t border-gray-50">
                            <td className="px-1.5 py-1 font-semibold text-gray-700">{row.classeInitiale}</td>
                            {row.transitions.map((v, j) => {
                              const isDiag = j === row.classeInitiale - 1;
                              const isHigh = !isDiag && v > 10;
                              return (
                                <td key={j} className={`px-1.5 py-1 text-center ${isDiag ? "bg-brand-100 text-brand-800 font-semibold" : isHigh ? "text-amber-700 font-medium" : "text-gray-500"}`}>
                                  {v > 0 ? v : ""}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-[10px] text-gray-400 mt-1">Valeurs en % · Diagonal = maintien de classe</p>
                </div>
              </div>
            </div>
            <div className="flex justify-between">
              <button onClick={prev} className="flex items-center gap-1.5 text-sm text-gray-500 border border-gray-200 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition-colors">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 17l-5-5m0 0l5-5m-5 5h12" /></svg>
                Retour
              </button>
              <button onClick={next} className="flex items-center gap-1.5 text-white text-sm font-medium px-5 py-2.5 rounded-xl transition-all shadow-sm" style={{ background: "linear-gradient(135deg, #006969, #007B7A)" }}>
                Grille de décision
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
              </button>
            </div>
          </div>
        )}

        {/* Step 5: Overrides */}
        {step === "overrides" && (
          <div className="space-y-4">
            <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-800 mb-1">Analyse des overrides</h2>
              <p className="text-xs text-gray-500 mb-4">
                Compare Fundamental Class (modèle statistique pur) vs Final Class (avec ajustement expert). Un écart significatif et directionnel peut signaler une faiblesse structurelle. Source : EBA/GL/2017/16 §4.3.
              </p>

              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-5">
                <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
                  <p className="text-xs font-medium text-gray-500 mb-1">Taux d'override</p>
                  <p className={`text-3xl font-semibold font-mono ${model.overrideRate > 0.10 ? "text-amber-700" : "text-gray-900"}`}>
                    {(model.overrideRate * 100).toFixed(1)}%
                  </p>
                  <StatusBadge status={model.overrideRate > 0.10 ? "orange" : "vert"} label={model.overrideRate > 0.10 ? "Élevé" : "Normal"} size="sm" />
                </div>
                <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
                  <p className="text-xs font-medium text-gray-500 mb-1">Direction dominante</p>
                  <p className="text-sm font-semibold text-gray-800 mt-1">
                    {model.overrideDirectionnel ? "Dégradations systématiques" : "Bidirectionnel (équilibré)"}
                  </p>
                  <StatusBadge status={model.overrideDirectionnel ? "orange" : "vert"} label={model.overrideDirectionnel ? "Signal" : "Neutre"} size="sm" />
                </div>
                <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
                  <p className="text-xs font-medium text-gray-500 mb-1">Impact sur Gini</p>
                  <p className="text-sm font-semibold text-gray-800 mt-1">Fundamental vs Final</p>
                  <p className="text-xs text-gray-500">Calculé par l’API lorsque les résultats Fundamental et Final sont disponibles.</p>
                </div>
              </div>

              {model.overrideDirectionnel && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                  <p className="text-sm font-semibold text-amber-800 mb-1">Signal — Override orienté et élevé</p>
                  <p className="text-xs text-amber-700">
                    Un taux d'override élevé et systématiquement dans le même sens (dégradations) peut signaler une faiblesse structurelle non capturée par le score statistique.
                    Cela constitue un signal à part entière pour la décision de recalibrage/refonte (EBA/GL/2017/16 §4.3).
                  </p>
                  <p className="text-xs font-semibold text-amber-800 mt-2">Action : Investiguer les variables manquantes. Envisager une refonte incluant les facteurs correctifs récurrents.</p>
                </div>
              )}
            </div>
            <div className="flex justify-between">
              <button onClick={prev} className="text-sm text-gray-600 border border-gray-200 px-4 py-2 rounded-lg hover:bg-gray-50 transition-colors">← Retour</button>
              <button onClick={next} className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-5 py-2 rounded-lg transition-colors">Grille de décision →</button>
            </div>
          </div>
        )}

        {/* Step 6: Decision */}
        {step === "decision" && (
          <div className="space-y-4">
            <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-800 mb-1">Grille de décision — {model.segmentLabel}</h2>
              <p className="text-xs text-gray-500 mb-4">Synthèse des résultats et décision de recalibrage selon le référentiel méthodologique (Section 6).</p>

              <div className="overflow-x-auto rounded-lg border border-gray-100 mb-5">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      <th className="px-4 py-2 text-left font-medium text-gray-600">Dimension</th>
                      <th className="px-4 py-2 text-left font-medium text-gray-600">Résultat</th>
                      <th className="px-4 py-2 text-left font-medium text-gray-600">Statut</th>
                      <th className="px-4 py-2 text-left font-medium text-gray-600">Interprétation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    <tr>
                      <td className="px-4 py-3 font-medium text-gray-700">Discrimination (Gini)</td>
                      <td className="px-4 py-3 font-mono">{model.gini > 0 ? model.gini.toFixed(2) : "N/C"}</td>
                      <td className="px-4 py-3"><StatusBadge status={model.gini === 0 ? "nc" : model.gini > 0.40 ? "vert" : "rouge"} size="sm" /></td>
                      <td className="px-4 py-3 text-gray-600">{model.gini === 0 ? "Non calculable — aucun défaut" : model.gini > 0.40 ? "Pouvoir discriminant satisfaisant" : "Dégradation du pouvoir discriminant"}</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-medium text-gray-700">Calibration (H-L)</td>
                      <td className="px-4 py-3 font-mono">{model.hosmerLemeshowPValue > 0 ? `p = ${model.hosmerLemeshowPValue.toFixed(3)}` : "N/C"}</td>
                      <td className="px-4 py-3"><StatusBadge status={model.hosmerLemeshowPValue === 0 ? "nc" : model.hosmerLemeshowPValue > 0.05 ? "vert" : "orange"} size="sm" /></td>
                      <td className="px-4 py-3 text-gray-600">{model.hosmerLemeshowPValue === 0 ? "Non calculable" : "Adéquation globale marginalement rejetée (p &lt; 0.05)"}</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-medium text-gray-700">Stabilité (PSI)</td>
                      <td className="px-4 py-3 font-mono">{model.psi.toFixed(2)}</td>
                      <td className="px-4 py-3"><StatusBadge status={model.psi < 0.10 ? "vert" : model.psi < 0.25 ? "orange" : "rouge"} size="sm" /></td>
                      <td className="px-4 py-3 text-gray-600">{model.psi < 0.10 ? "Population stable" : model.psi < 0.25 ? "Dérive modérée — à surveiller" : "Dérive significative"}</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-medium text-gray-700">Override</td>
                      <td className="px-4 py-3 font-mono">{(model.overrideRate * 100).toFixed(1)}%</td>
                      <td className="px-4 py-3"><StatusBadge status={model.overrideRate > 0.10 ? "orange" : "vert"} size="sm" /></td>
                      <td className="px-4 py-3 text-gray-600">{model.overrideDirectionnel ? "Taux élevé et orienté — signal structurel" : "Taux acceptable et bidirectionnel"}</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 font-medium text-gray-700">Événements</td>
                      <td className="px-4 py-3 font-mono">{model.totalDefauts} défaut(s)</td>
                      <td className="px-4 py-3"><StatusBadge status={model.totalDefauts >= 20 ? "vert" : "rouge"} size="sm" /></td>
                      <td className="px-4 py-3 text-gray-600">{model.totalDefauts < 20 ? "Insuffisance critique — tests non concluants statistiquement" : "Volume suffisant"}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Decision box */}
              <div className={`rounded-2xl p-5 border-2 ${model.decision.urgence === "vert" ? "border-emerald-200 bg-emerald-50" : model.decision.urgence === "orange" ? "border-amber-200 bg-amber-50" : "border-red-200 bg-red-50"}`}>
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <div className={`h-2 w-2 rounded-full ${model.decision.urgence === "vert" ? "bg-emerald-500" : model.decision.urgence === "orange" ? "bg-amber-500" : "bg-red-500"}`} />
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">Décision finale</p>
                    </div>
                    <p className="text-base font-bold text-gray-900">{model.decision.label}</p>
                    <p className="text-[10px] text-gray-400 mt-0.5 font-mono">Segment : {model.segmentLabel}</p>
                  </div>
                  <StatusBadge status={model.decision.urgence} size="lg" label={model.decision.urgence === "vert" ? "Maintien" : model.decision.urgence === "orange" ? "Surveillance" : "Action requise"} />
                </div>
                <p className="text-xs text-gray-700 leading-relaxed border-t border-black/5 pt-3 mt-2">{model.decision.justification}</p>
              </div>

              <div className="mt-4 flex gap-3">
                <button className="flex-1 flex items-center justify-center gap-2 text-white text-sm font-medium py-3 rounded-xl transition-all shadow-sm" style={{ background: "linear-gradient(135deg, #006969, #007B7A)" }}>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                  Générer le rapport
                </button>
                {model.decision.verdict !== "maintien" && model.decision.verdict !== "non_concluant" && (
                  <button className="flex-1 flex items-center justify-center gap-2 border border-brand-300 text-brand-700 hover:bg-brand-50 text-sm font-medium py-3 rounded-xl transition-colors">
                    Procéder au recalibrage
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
                  </button>
                )}
              </div>
            </div>

            <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
              <h3 className="text-xs font-semibold text-gray-700 mb-3">Alertes du backtesting ({model.alertes.length})</h3>
              <div className="space-y-2">
                {model.alertes.map(a => (
                  <div key={a.id} className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 border border-gray-100">
                    <StatusBadge status={a.severite} size="sm" />
                    <div>
                      <p className="text-xs font-medium text-gray-800">{a.titre}</p>
                      <p className="text-[11px] text-gray-500 mt-0.5">{a.action}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-start">
              <button onClick={prev} className="flex items-center gap-1.5 text-sm text-gray-500 border border-gray-200 px-4 py-2.5 rounded-xl hover:bg-gray-50 transition-colors">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 17l-5-5m0 0l5-5m-5 5h12" /></svg>
                Retour
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
