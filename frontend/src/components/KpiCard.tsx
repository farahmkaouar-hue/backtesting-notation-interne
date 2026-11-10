import type { TrafficLight } from "../types";

interface Props {
  label: string;
  value: string | number;
  unit?: string;
  status: TrafficLight;
  sub?: string;
  threshold?: string;
  trend?: { dir: "up" | "down" | "flat"; label: string };
  onClick?: () => void;
  icon?: "users" | "alert" | "check" | "chart" | "data";
}

const ICONS = {
  users: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z",
  alert: "M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z",
  check: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
  chart: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z",
  data: "M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4",
};

const STATUS_STYLES: Record<TrafficLight, { accent: string; iconBg: string; iconColor: string; border: string }> = {
  vert:   { accent: "bg-emerald-500", iconBg: "bg-emerald-50",  iconColor: "text-emerald-600", border: "border-l-emerald-400" },
  orange: { accent: "bg-amber-500",   iconBg: "bg-amber-50",    iconColor: "text-amber-600",   border: "border-l-amber-400" },
  rouge:  { accent: "bg-red-500",     iconBg: "bg-red-50",      iconColor: "text-red-600",     border: "border-l-red-400" },
  nc:     { accent: "bg-gray-300",    iconBg: "bg-gray-50",     iconColor: "text-gray-400",    border: "border-l-gray-300" },
};

const TREND_STYLES = {
  up:   { color: "text-red-500",     arrow: "↑" },
  down: { color: "text-emerald-500", arrow: "↓" },
  flat: { color: "text-gray-400",    arrow: "→" },
};

export function KpiCard({ label, value, unit, status, sub, threshold, trend, onClick, icon = "chart" }: Props) {
  const s = STATUS_STYLES[status];

  return (
    <div
      onClick={onClick}
      className={`bg-white rounded-xl border border-gray-100 border-l-4 ${s.border} p-4 shadow-sm flex flex-col gap-3 ${onClick ? "cursor-pointer hover:shadow-md" : ""} transition-shadow`}
    >
      <div className="flex items-start justify-between">
        <div className={`h-8 w-8 rounded-lg ${s.iconBg} flex items-center justify-center`}>
          <svg className={`w-4 h-4 ${s.iconColor}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.75}>
            <path strokeLinecap="round" strokeLinejoin="round" d={ICONS[icon]} />
          </svg>
        </div>
        <div className={`h-1.5 w-1.5 rounded-full ${s.accent}`} />
      </div>

      <div>
        <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wider leading-none mb-1.5">{label}</p>
        <div className="flex items-baseline gap-1">
          <span className="text-[28px] font-semibold font-mono text-gray-900 leading-none">{value}</span>
          {unit && <span className="text-sm text-gray-400 font-sans">{unit}</span>}
        </div>
      </div>

      <div className="flex items-center justify-between gap-2">
        {sub && <p className="text-[11px] text-gray-400 leading-tight">{sub}</p>}
        {trend && (
          <span className={`text-[10px] font-medium font-mono ${TREND_STYLES[trend.dir].color} ml-auto shrink-0`}>
            {TREND_STYLES[trend.dir].arrow} {trend.label}
          </span>
        )}
      </div>

      {threshold && (
        <p className="text-[10px] text-gray-300 font-mono border-t border-gray-50 pt-2 -mt-1">Seuil : {threshold}</p>
      )}
    </div>
  );
}
