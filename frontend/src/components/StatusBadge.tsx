import type { TrafficLight } from "../types";

interface Props {
  status: TrafficLight;
  label?: string;
  size?: "xs" | "sm" | "md" | "lg";
  dot?: boolean;
  pill?: boolean;
}

const CFG: Record<TrafficLight, { bg: string; text: string; dot: string; ring: string; defaultLabel: string }> = {
  vert:   { bg: "bg-emerald-50",  text: "text-emerald-700", dot: "bg-emerald-500", ring: "bg-emerald-300", defaultLabel: "Conforme" },
  orange: { bg: "bg-amber-50",   text: "text-amber-700",   dot: "bg-amber-500",  ring: "bg-amber-300",  defaultLabel: "Surveillance" },
  rouge:  { bg: "bg-red-50",     text: "text-red-700",     dot: "bg-red-500",    ring: "bg-red-300",    defaultLabel: "Alerte" },
  nc:     { bg: "bg-gray-100",   text: "text-gray-500",    dot: "bg-gray-400",   ring: "bg-gray-300",   defaultLabel: "N/C" },
};

const SIZE_CLASS: Record<string, string> = {
  xs: "text-[9px] px-1.5 py-0.5 gap-1",
  sm: "text-[10px] px-2 py-0.5 gap-1",
  md: "text-xs px-2.5 py-1 gap-1.5",
  lg: "text-sm px-3 py-1.5 gap-2",
};

const DOT_SIZE: Record<string, string> = {
  xs: "h-1.5 w-1.5",
  sm: "h-1.5 w-1.5",
  md: "h-2 w-2",
  lg: "h-2.5 w-2.5",
};

export function StatusBadge({ status, label, size = "sm", dot = true, pill = true }: Props) {
  const c = CFG[status];
  const text = label ?? c.defaultLabel;

  return (
    <span className={`inline-flex items-center font-medium border border-current/10 ${c.bg} ${c.text} ${SIZE_CLASS[size]} ${pill ? "rounded-full" : "rounded-md"}`}>
      {dot && (
        <span className={`relative flex shrink-0 ${DOT_SIZE[size]}`}>
          {status !== "nc" && (
            <span className={`absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping ${c.ring}`} />
          )}
          <span className={`relative inline-flex rounded-full h-full w-full ${c.dot}`} />
        </span>
      )}
      {text}
    </span>
  );
}

export function TrafficLightIcon({ status, size = 22 }: { status: TrafficLight; size?: number }) {
  const active = { vert: "#16a34a", orange: "#d97706", rouge: "#dc2626", nc: "#9ca3af" }[status];
  return (
    <svg width={size} height={size} viewBox="0 0 22 22" fill="none">
      <rect x="7" y="1" width="8" height="20" rx="4" fill="#111827" opacity="0.12" />
      <rect x="7.5" y="1.5" width="7" height="19" rx="3.5" stroke="#111827" strokeOpacity="0.08" strokeWidth="1" />
      <circle cx="11" cy="5.5" r="2.5" fill={status === "rouge" ? active : "#374151"} opacity={status === "rouge" ? 1 : 0.18} />
      <circle cx="11" cy="11" r="2.5"  fill={status === "orange" ? active : "#374151"} opacity={status === "orange" ? 1 : 0.18} />
      <circle cx="11" cy="16.5" r="2.5" fill={status === "vert" ? active : status === "nc" ? "#9ca3af" : "#374151"} opacity={status === "vert" ? 1 : status === "nc" ? 0.5 : 0.18} />
    </svg>
  );
}

/* A compact inline metric with colored figure */
export function MetricPill({ label, value, status }: { label: string; value: string; status: TrafficLight }) {
  const color = { vert: "text-emerald-700", orange: "text-amber-700", rouge: "text-red-700", nc: "text-gray-400" }[status];
  return (
    <div className="flex flex-col items-center gap-0.5">
      <span className={`text-sm font-semibold font-mono leading-none ${color}`}>{value}</span>
      <span className="text-[9px] text-gray-400 uppercase tracking-wide leading-none">{label}</span>
    </div>
  );
}
