import { useState, useRef, useEffect } from "react";
import { api } from "../api/client";

interface Message { role: "user" | "ai"; text: string; ts: string }

const CANNED: Record<string, string> = {
  gini: "Le coefficient de Gini mesure le pouvoir discriminant du modèle — sa capacité à ordonner les bons et mauvais risques. Il varie de -1 à 1, et vaut 2×AUC−1. Un Gini > 0.40 est généralement attendu en retail/corporate (EBA/GL/2017/16). Un Gini élevé ne garantit pas une bonne calibration : le modèle peut bien classer les risques tout en sous- ou surestimant les PD en valeur absolue.",
  auc: "L'AUC (Area Under the ROC Curve) est la probabilité qu'un défaillant soit mieux noté (score plus risqué) qu'un non-défaillant tiré au hasard. AUC > 0.70 est jugé acceptable, AUC > 0.80 est bon (BCBS WP14). C'est la référence académique internationale permettant la comparaison inter-modèles.",
  ks: "La statistique KS (Kolmogorov-Smirnov) représente l'écart maximal entre les distributions cumulées des scores des défaillants et des non-défaillants. KS > 0.20 est acceptable. Elle identifie un point de coupure opérationnel utile pour les décisions d'octroi. Conservée en diagnostic complémentaire au Gini.",
  psi: "Le PSI (Population Stability Index) mesure la dérive de la distribution des notes entre deux périodes. Seuils : PSI < 0.10 → stable (vert) ; 0.10–0.25 → surveiller (orange) ; > 0.25 → dérive significative (rouge). Un PSI élevé sans dégradation du Gini indique que le portefeuille a changé — pas nécessairement que le modèle a faibli.",
  calibration: "La calibration vérifie que les PD prédites par classe correspondent aux taux de défaut réellement observés. Trois tests complémentaires : (1) Binomial simple — rapide mais suppose l'indépendance des défauts ; (2) Jeffrey/Vasicek — intègre la corrélation de défaut entre débiteurs d'une même classe, test principal retenu ; (3) Hosmer-Lemeshow — vision globale multi-classes. Une bonne discrimination n'implique pas une bonne calibration.",
  recalibrage: "Deux niveaux selon le référentiel (§6) : (1) Recalibrage simple — si Gini/AUC/KS sont stables mais la calibration est dégradée : ré-estimation du mapping score→PD par ajustement de central tendency ou régression logistique de recalibration ; (2) Refonte du modèle — si Gini/AUC/KS en baisse significative : ré-estimation des coefficients, voire changement des variables explicatives.",
  jeffrey: "Le test de Jeffrey/Vasicek est le test de calibration principal retenu par ce référentiel (EBA/GL/2017/16 §5). Il intègre une corrélation d'actifs entre débiteurs d'une même classe, corrigeant le biais du test binomial qui suppose l'indépendance. La p-value est calculée par classe. p < 0.05 indique un écart statistiquement significatif entre PD prédite et taux observé.",
  insuffisance: "Avec moins de 20 événements de défaut, les tests statistiques ne sont pas robustes — l'AUC, le Gini et les tests de calibration peuvent être très sensibles à 1–2 défauts supplémentaires. EBA/GL/2017/16 recommande d'agréger plusieurs cohortes annuelles. Dans ce contexte, la calibration bayésienne avec prior historique est privilégiée sur l'approche fréquentiste.",
  hosmer: "Le test de Hosmer-Lemeshow évalue l'adéquation globale entre les PD prédites et les fréquences observées sur l'ensemble des classes de notation. Il donne une vision synthétique pour le comité des risques. Limite : peu granulaire — il ne dit pas quelle classe précise pose problème. Conservé en complément du test de Jeffrey.",
  bayesien: "La calibration bayésienne introduit un a priori (prior) construit sur l'historique long ou un dire d'expert pour stabiliser l'estimation avec peu de défauts. Adaptée aux Low Default Portfolios — typiquement Corporate. Elle intègre une part de jugement à documenter et justifier explicitement (EBA/GL/2017/16 §4.3 sur la marge de conservatisme).",
};

function getAnswer(q: string): string {
  const lower = q.toLowerCase();
  if (lower.includes("gini")) return CANNED.gini;
  if (lower.includes("auc") || lower.includes("roc")) return CANNED.auc;
  if (lower.includes("ks") || lower.includes("kolmogorov")) return CANNED.ks;
  if (lower.includes("psi") || lower.includes("stabilit")) return CANNED.psi;
  if (lower.includes("hosmer") || lower.includes("lemeshow")) return CANNED.hosmer;
  if (lower.includes("calibr")) return CANNED.calibration;
  if (lower.includes("recalib") || lower.includes("refonte")) return CANNED.recalibrage;
  if (lower.includes("jeffrey") || lower.includes("vasicek") || lower.includes("binomial")) return CANNED.jeffrey;
  if (lower.includes("insuffisan") || lower.includes("événement") || lower.includes("défaut") || lower.includes("defaut")) return CANNED.insuffisance;
  if (lower.includes("bayes") || lower.includes("prior") || lower.includes("ldp")) return CANNED.bayesien;
  return "Je peux expliquer : Gini, AUC, KS, PSI, calibration, test de Jeffrey, Hosmer-Lemeshow, recalibrage, approche bayésienne, ou insuffisance d'événements. Reformulez votre question en mentionnant l'un de ces termes.";
}

const SUGGESTIONS = [
  "Que signifie le Gini ?",
  "Pourquoi le PSI est en orange ?",
  "Expliquer le test de Jeffrey",
  "Qu'est-ce que le recalibrage simple ?",
  "Calibration bayésienne ?",
];

export function AIAssistant({ open, onClose, token, runId, model }: { open: boolean; onClose: () => void; token: string; runId?: string; model?: string }) {
  const ts = () => new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

  const [messages, setMessages] = useState<Message[]>([
    { role: "ai", text: "Bonjour. Je suis disponible pour expliquer les indicateurs, méthodes et résultats du backtesting selon le référentiel EBA/GL/2017/16 et le guide BCE.\n\nJe n'interviens pas dans les données ni les décisions — posez-moi vos questions.", ts: ts() },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function send(text?: string) {
    const q = (text ?? input).trim();
    if (!q) return;
    const now = ts();
    setMessages(m => [...m, { role: "user", text: q, ts: now }]);
    setInput("");
    setLoading(true);
    api.chat(token, q, runId, model).then(response => {
      const sources = response.references?.map(reference => reference.value).join(" · ");
      setMessages(m => [...m, { role: "ai", text: `${response.answer}${sources ? `\n\nRéférences : ${sources}` : ""}${response.guardrail ? `\n\n${response.guardrail}` : ""}`, ts: ts() }]);
    }).catch(() => {
      setMessages(m => [...m, { role: "ai", text: `${getAnswer(q)}\n\nNote : la réponse provient du mode explicatif local car l’API est indisponible.`, ts: ts() }]);
    }).finally(() => {
      setLoading(false);
    });
  }

  if (!open) return null;

  return (
    <div className="fixed right-0 top-0 h-full w-80 bg-white border-l border-gray-200 flex flex-col z-40 shadow-2xl">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3.5 border-b border-gray-100"
        style={{ background: "linear-gradient(135deg, #004040, #006969)" }}>
        <div className="h-8 w-8 rounded-full bg-white/15 flex items-center justify-center shrink-0">
          <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <div className="flex-1">
          <p className="text-sm font-semibold text-white leading-none">Assistant IA</p>
          <p className="text-[10px] text-white/50 leading-none mt-0.5">Référentiel EBA/GL/2017/16</p>
        </div>
        <button onClick={onClose} className="text-white/50 hover:text-white transition-colors">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Disclaimer */}
      <div className="px-3 py-2 bg-amber-50 border-b border-amber-100">
        <p className="text-[10px] text-amber-700 leading-relaxed">
          Rôle explicatif uniquement — ne modifie ni les données ni les décisions.
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-2 ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            {m.role === "ai" && (
              <div className="h-6 w-6 rounded-full bg-brand-100 flex items-center justify-center shrink-0 mt-0.5">
                <span className="text-[9px] font-bold text-brand-700">IA</span>
              </div>
            )}
            <div className={`max-w-[85%] ${m.role === "user" ? "items-end" : "items-start"} flex flex-col gap-1`}>
              <div className={`rounded-2xl px-3 py-2 text-xs leading-relaxed ${
                m.role === "user"
                  ? "bg-brand-600 text-white rounded-br-sm"
                  : "bg-gray-100 text-gray-800 rounded-bl-sm"
              }`}>
                {m.text}
              </div>
              <span className="text-[9px] text-gray-300 px-1">{m.ts}</span>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex gap-2 justify-start">
            <div className="h-6 w-6 rounded-full bg-brand-100 flex items-center justify-center shrink-0">
              <span className="text-[9px] font-bold text-brand-700">IA</span>
            </div>
            <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-3 py-2">
              <div className="flex gap-1 items-center h-4">
                {[0, 0.15, 0.3].map(d => (
                  <div key={d} className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: `${d}s` }} />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      <div className="px-3 pt-2 border-t border-gray-100">
        <p className="text-[9px] text-gray-400 uppercase tracking-wider mb-1.5">Suggestions</p>
        <div className="flex flex-wrap gap-1 mb-2">
          {SUGGESTIONS.map(s => (
            <button
              key={s}
              onClick={() => send(s)}
              className="text-[10px] bg-brand-50 text-brand-700 border border-brand-100 rounded-full px-2 py-0.5 hover:bg-brand-100 transition-colors leading-snug"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Input */}
      <div className="p-3 pb-4">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
            placeholder="Votre question..."
            className="flex-1 text-xs border border-gray-200 rounded-xl px-3 py-2.5 focus:outline-none focus:border-brand-400 bg-gray-50 placeholder:text-gray-300"
          />
          <button
            onClick={() => send()}
            disabled={!input.trim()}
            className="bg-brand-600 hover:bg-brand-700 text-white rounded-xl px-3 py-2.5 transition-colors disabled:opacity-40"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
