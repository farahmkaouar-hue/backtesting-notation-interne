import { useState } from "react";
import AppLogo from "../components/AppLogo";
import { api } from "../api/client";

interface Props { onLogin: (username: string, password: string) => Promise<void> }

const FEATURES = [
  { icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z", label: "Backtesting AUC · Gini · KS · PSI" },
  { icon: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z", label: "Calibration Jeffrey · Hosmer-Lemeshow" },
  { icon: "M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4", label: "Recalibrage bayésien & central tendency" },
  { icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z", label: "Traçabilité réglementaire · CRR art. 189" },
];

export function LoginPage({ onLogin }: Props) {
  const [mode, setMode] = useState<"register" | "login">("register");
  const [login, setLogin] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      if (mode === "register") {
        const response = await api.register(login, fullName, email, password);
        setError(response.message);
        setMode("login");
      } else {
        await onLogin(login, password);
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : "Connexion impossible.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex" style={{ background: "#EFF3F4" }}>
      {/* Left branding panel */}
      <div className="hidden lg:flex w-[52%] flex-col justify-between p-14 relative overflow-hidden"
        style={{ background: "linear-gradient(160deg, #002B2B 0%, #005555 50%, #007B7A 100%)" }}>
        {/* Geometric decoration */}
        <div className="absolute inset-0 pointer-events-none opacity-[0.04]">
          <div className="absolute top-0 right-0 w-96 h-96 border-[40px] border-white rounded-full translate-x-1/3 -translate-y-1/3" />
          <div className="absolute bottom-0 left-0 w-64 h-64 border-[30px] border-white rounded-full -translate-x-1/3 translate-y-1/3" />
        </div>

        <AppLogo inverted className="relative" />

        <div className="relative">
          <p className="text-brand-300 text-sm font-medium mb-4 tracking-wide uppercase">
            Direction des Risques · Modèles Internes
          </p>
          <h1 className="text-[38px] font-light text-white leading-[1.15] mb-6">
            Backtesting &<br />
            <span className="font-semibold">Recalibrage IRB</span>
          </h1>
          <p className="text-white/50 text-sm leading-relaxed max-w-sm">
            Validation des systèmes de notation interne — Retail Professionnel & Corporate. Conforme EBA/GL/2017/16, CRR n°575/2013 et ECB Guide to Internal Models.
          </p>

          <div className="mt-10 space-y-4">
            {FEATURES.map(f => (
              <div key={f.label} className="flex items-center gap-3">
                <div className="h-8 w-8 rounded-lg bg-white/8 flex items-center justify-center shrink-0">
                  <svg className="w-4 h-4 text-brand-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.75}>
                    <path strokeLinecap="round" strokeLinejoin="round" d={f.icon} />
                  </svg>
                </div>
                <span className="text-white/60 text-sm">{f.label}</span>
              </div>
            ))}
          </div>
        </div>

        <p className="text-white/25 text-xs relative">
          © 2026 Union Bancaire pour le Commerce et l'Industrie
        </p>
      </div>

      {/* Right login panel */}
      <div className="flex-1 flex items-center justify-center px-8 py-12">
        <div className="w-full max-w-[360px]">
          <AppLogo className="mb-10 lg:hidden" />

          <div className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-1">{mode === "register" ? "Créer un compte" : "Connexion"}</h2>
            <p className="text-sm text-gray-400">{mode === "register" ? "Étape initiale : demande d’accès soumise à validation." : "Accès réservé aux comptes validés."}</p>
          </div>

          <div className="mb-6 flex rounded-xl bg-gray-100 p-1 text-xs font-semibold">
            <button type="button" onClick={() => { setMode("register"); setError(""); }} className={`flex-1 rounded-lg px-3 py-2 ${mode === "register" ? "bg-white text-brand-700 shadow-sm" : "text-gray-500"}`}>Créer un compte</button>
            <button type="button" onClick={() => { setMode("login"); setError(""); }} className={`flex-1 rounded-lg px-3 py-2 ${mode === "login" ? "bg-white text-brand-700 shadow-sm" : "text-gray-500"}`}>Se connecter</button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === "register" && <>
              <div><label className="block text-xs font-medium text-gray-600 mb-1.5">Nom complet</label><input value={fullName} onChange={e => setFullName(e.target.value)} className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" required /></div>
              <div><label className="block text-xs font-medium text-gray-600 mb-1.5">Adresse e-mail professionnelle</label><input type="email" value={email} onChange={e => setEmail(e.target.value)} className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" required /></div>
            </>}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">Identifiant</label>
              <input
                value={login}
                onChange={e => setLogin(e.target.value)}
                placeholder="prénom.nom"
                autoComplete="username"
                className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 bg-white transition-all"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">Mot de passe</label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                placeholder={mode === "register" ? "12 caractères minimum" : "••••••••"}
                  autoComplete="current-password"
                  className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 bg-white transition-all pr-11"
                  required
                />
                <button type="button" onClick={() => setShowPassword(p => !p)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 transition-colors">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.75}>
                    {showPassword
                      ? <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                      : <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    }
                  </svg>
                </button>
              </div>
            </div>

            {error && (
              <div className={`flex items-center gap-2 rounded-xl px-3 py-2.5 text-xs ${error.includes("enregistrée") ? "bg-emerald-50 border border-emerald-100 text-emerald-700" : "bg-red-50 border border-red-100 text-red-700"}`}>
                <svg className="w-4 h-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full text-white text-sm font-medium py-3 rounded-xl transition-all disabled:opacity-70 flex items-center justify-center gap-2"
              style={{ background: loading ? "#93CACA" : "linear-gradient(135deg, #006969, #007B7A)" }}
            >
              {loading && (
                <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              )}
              {loading ? "Traitement..." : mode === "register" ? "Envoyer la demande" : "Se connecter"}
            </button>
          </form>

          <div className="mt-8 p-4 bg-white rounded-xl border border-gray-100 shadow-sm">
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Gouvernance des accès</p>
            <p className="text-xs text-gray-500 leading-relaxed">Toute demande est journalisée et doit être validée par un administrateur. Aucun compte ni mot de passe par défaut n’est affiché.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
