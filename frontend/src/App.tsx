import { lazy, Suspense, useState } from "react";
import type { PageView, User } from "./types";
import { Sidebar } from "./components/Sidebar";
import { AIAssistant } from "./components/AIAssistant";
import { api, userFromToken } from "./api/client";
import type { ApiModel, ApiRun } from "./api/client";

const LoginPage = lazy(() => import("./pages/LoginPage").then(module => ({ default: module.LoginPage })));
const DashboardPage = lazy(() => import("./pages/DashboardPage").then(module => ({ default: module.DashboardPage })));
const DataPage = lazy(() => import("./pages/DataPage").then(module => ({ default: module.DataPage })));
const BacktestingPage = lazy(() => import("./pages/BacktestingPage").then(module => ({ default: module.BacktestingPage })));

function PageLoader() {
  return (
    <div className="flex flex-1 items-center justify-center bg-gray-50 text-sm text-gray-400">
      Chargement de la page…
    </div>
  );
}

function DataBoundModule({ title, description }: { title: string; description: string }) {
  return <div className="flex flex-1 items-center justify-center bg-gray-50 p-6"><div className="max-w-lg rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm"><h1 className="text-lg font-semibold text-gray-800">{title}</h1><p className="mt-2 text-sm leading-relaxed text-gray-500">{description}</p><p className="mt-4 text-xs text-brand-700">Les chiffres fictifs ont été désactivés : ce module n’affiche que des données enregistrées par le backend.</p></div></div>;
}

const PAGE_LABELS: Record<PageView, string> = {
  login: "Connexion",
  dashboard: "Tableau de bord",
  data: "Données & Préparation",
  backtesting: "Backtesting",
  recalibration: "Recalibrage",
  supervisor: "Vue Superviseur",
  reports: "Rapports & Historique",
};

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem("backtesting_token") ?? "");
  const [user, setUser] = useState<User | null>(() => {
    const current = userFromToken(localStorage.getItem("backtesting_token") ?? "");
    if (!current) return null;
    const roleMap: Record<string, User["role"]> = { analyst: "analyste", supervisor: "superviseur", admin: "admin" };
    return { name: current.username, role: roleMap[current.role], initials: current.username.slice(0, 2).toUpperCase() };
  });
  const [page, setPage] = useState<PageView>("dashboard");
  const [aiOpen, setAiOpen] = useState(false);
  const [datasetId, setDatasetId] = useState("");
  const [models, setModels] = useState<ApiModel[]>([]);
  const [liveResult, setLiveResult] = useState<Record<string, unknown> | null>(null);
  const [runId, setRunId] = useState("");
  const [runs, setRuns] = useState<ApiRun[]>([]);
  const [running, setRunning] = useState(false);

  async function refreshModels(id: string) {
    const response = await api.models(token, id);
    setModels(response.models);
  }

  async function authenticate(username: string, password: string) {
    const response = await api.login(username, password);
    const current = userFromToken(response.access_token);
    if (!current) throw new Error("Jeton de connexion invalide.");
    const roleMap: Record<string, User["role"]> = { analyst: "analyste", supervisor: "superviseur", admin: "admin" };
    setToken(response.access_token);
    localStorage.setItem("backtesting_token", response.access_token);
    setUser({ name: current.username, role: roleMap[current.role], initials: current.username.slice(0, 2).toUpperCase() });
    try { setRuns(await api.runs(response.access_token)); } catch { setRuns([]); }
  }

  async function handleUpload(id: string) {
    setDatasetId(id);
    await refreshModels(id);
  }

  async function handleBacktest(model: string, horizon: { developmentStart: string; developmentEnd: string; backtestStart: string; backtestEnd: string }) {
    if (!datasetId) throw new Error("Importez un jeu de données avant de lancer le backtesting.");
    setRunning(true);
    try {
      const result = await api.backtest(token, datasetId, model, horizon);
      setLiveResult(result);
      setRunId(String(result.run_id ?? ""));
      try { setRuns(await api.runs(token)); } catch { /* access may be analyst-only */ }
      return result;
    } finally { setRunning(false); }
  }

  if (!user) {
    return (
      <Suspense fallback={<PageLoader />}>
        <LoginPage onLogin={async (username, password) => { await authenticate(username, password); setPage("dashboard"); }} />
      </Suspense>
    );
  }

  // Le badge ne reflète que les alertes réellement calculées par la dernière exécution.
  const alertCount = Array.isArray((liveResult as { final_backtest?: { warnings?: unknown[] } } | null)?.final_backtest?.warnings)
    ? (liveResult as { final_backtest: { warnings: unknown[] } }).final_backtest.warnings.length
    : 0;

  return (
    <div className="flex h-screen bg-[#EFF3F4] overflow-hidden">
      <Sidebar current={page} user={user} onNavigate={setPage} onAI={() => setAiOpen(o => !o)} alertCount={alertCount} />

      <main className={`flex-1 flex flex-col overflow-hidden transition-[margin] duration-200 ${aiOpen ? "mr-80" : ""}`}>
        {/* Topbar */}
        <header className="h-12 shrink-0 bg-white border-b border-gray-100 flex items-center justify-between px-5 shadow-[0_1px_0_rgba(0,0,0,0.04)]">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-gray-400">Risques</span>
            <svg className="w-3 h-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span className="font-semibold text-gray-800">{PAGE_LABELS[page]}</span>
          </div>

          <div className="flex items-center gap-2.5">
            {/* Live indicator */}
            <div className="hidden sm:flex items-center gap-1.5 text-[10px] text-gray-400 font-mono bg-gray-50 border border-gray-100 px-2.5 py-1 rounded-full">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Session sécurisée
            </div>

            {/* AI toggle */}
            <button
              onClick={() => setAiOpen(o => !o)}
              className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border transition-all ${
                aiOpen
                  ? "bg-brand-600 text-white border-brand-600 shadow-sm"
                  : "bg-white text-gray-600 border-gray-200 hover:border-brand-300 hover:text-brand-700"
              }`}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              <span className="hidden sm:inline">Assistant IA</span>
            </button>

            {/* User avatar */}
            <div className="h-7 w-7 rounded-full flex items-center justify-center text-white text-[11px] font-semibold cursor-default"
              style={{ background: "linear-gradient(135deg, #2FA0A0, #007B7A)" }}>
              {user.initials}
            </div>
          </div>
        </header>

        {/* Page content with fade animation */}
        <Suspense fallback={<PageLoader />}>
          <div key={page} className="flex-1 overflow-hidden flex flex-col page-enter">
            {page === "dashboard"     && <DashboardPage onNavigate={setPage} models={models} result={liveResult} />}
          {page === "data"          && <DataPage token={token} onUploaded={handleUpload} />}
          {page === "backtesting"   && <BacktestingPage models={models} onRun={handleBacktest} liveResult={liveResult} running={running} />}
          {page === "recalibration" && <DataBoundModule title="Recalibrage" description="Lancez d’abord un backtesting valide. La proposition de recalibrage sera affichée uniquement lorsqu’elle aura été calculée, enregistrée et soumise à la validation indépendante." />}
          {page === "supervisor"    && <DataBoundModule title="Vue superviseur" description={runs.length ? `${runs.length} exécution(s) sont enregistrées. La vue consolidée sera alimentée uniquement à partir du journal d’audit.` : "Aucune exécution enregistrée."} />}
            {page === "reports"       && <DataBoundModule title="Rapports & historique" description="Aucun rapport de démonstration n’est présenté. Les rapports seront générés depuis une exécution validée et conservés dans le journal d’audit." />}
          </div>
        </Suspense>
      </main>

      <AIAssistant open={aiOpen} onClose={() => setAiOpen(false)} token={token} runId={runId || undefined} model={models.find(m => m.modele_cible === (liveResult as any)?.model)?.modele_cible} />
    </div>
  );
}
