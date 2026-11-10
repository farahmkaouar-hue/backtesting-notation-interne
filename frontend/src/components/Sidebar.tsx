import type { ReactNode } from "react";
import type { PageView, User } from "../types";
import AppLogo from "./AppLogo";

interface NavItem { id: PageView; label: string; icon: ReactNode; badge?: number }

interface Props {
  current: PageView;
  user: User;
  onNavigate: (page: PageView) => void;
  onAI: () => void;
  alertCount: number;
}

function Icon({ d }: { d: string }) {
  return (
    <svg className="w-[18px] h-[18px] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  );
}

const ICONS = {
  dashboard: "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6",
  data: "M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12",
  backtesting: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z",
  recalibration: "M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4",
  supervisor: "M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  reports: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
};

export function Sidebar({ current, user, onNavigate, onAI, alertCount }: Props) {
  const nav: NavItem[] = [
    { id: "dashboard", label: "Tableau de bord", icon: <Icon d={ICONS.dashboard} />, badge: alertCount > 0 ? alertCount : undefined },
    { id: "data", label: "Données & Préparation", icon: <Icon d={ICONS.data} /> },
    { id: "backtesting", label: "Backtesting", icon: <Icon d={ICONS.backtesting} /> },
    { id: "recalibration", label: "Recalibrage", icon: <Icon d={ICONS.recalibration} /> },
    { id: "supervisor", label: "Vue Superviseur", icon: <Icon d={ICONS.supervisor} /> },
    { id: "reports", label: "Rapports & Historique", icon: <Icon d={ICONS.reports} /> },
  ];

  const roleLabel: Record<string, string> = {
    analyste: "Analyste Risques",
    superviseur: "Superviseur",
    admin: "Administrateur",
  };

  return (
    <aside className="w-56 shrink-0 flex flex-col h-full" style={{ background: "linear-gradient(180deg, #004040 0%, #002B2B 100%)" }}>
      {/* Logo */}
      <div className="px-5 pt-5 pb-4 border-b border-white/10">
        <AppLogo inverted />
        <p className="text-[10px] font-mono tracking-widest uppercase text-white/30 mt-2.5 leading-none">
          Backtesting IRB
        </p>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto p-2 mt-1 space-y-0.5">
        {nav.map(item => {
          const active = current === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-[13px] font-medium text-left relative group transition-all ${
                active
                  ? "bg-white/15 text-white shadow-sm"
                  : "text-white/50 hover:bg-white/8 hover:text-white/85"
              }`}
            >
              {active && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-brand-300 rounded-r-full" />
              )}
              <span className={`transition-colors ${active ? "text-brand-300" : "text-white/40 group-hover:text-white/60"}`}>
                {item.icon}
              </span>
              <span className="leading-none">{item.label}</span>
              {item.badge != null && (
                <span className="ml-auto bg-red-500 text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1 shadow-sm">
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Bottom section */}
      <div className="p-2 border-t border-white/10 space-y-1">
        {/* AI button */}
        <button
          onClick={onAI}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-[13px] text-white/50 hover:bg-white/8 hover:text-white/85 transition-all group"
        >
          <svg className="w-[18px] h-[18px] shrink-0 text-white/40 group-hover:text-brand-300 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <span>Assistant IA</span>
          <span className="ml-auto text-[9px] font-mono text-brand-400 border border-brand-700 rounded px-1 py-0.5">Bêta</span>
        </button>

        {/* User */}
        <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg">
          <div className="h-7 w-7 rounded-full flex items-center justify-center text-white text-[11px] font-semibold shrink-0"
            style={{ background: "linear-gradient(135deg, #2FA0A0, #007B7A)" }}>
            {user.initials}
          </div>
          <div className="min-w-0">
            <p className="text-[12px] font-medium text-white/80 truncate leading-tight">{user.name}</p>
            <p className="text-[10px] text-white/35 leading-tight">{roleLabel[user.role] ?? user.role}</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
