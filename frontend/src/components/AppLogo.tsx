interface Props {
  inverted?: boolean;
  className?: string;
}

/**
 * Logo texte de l'application.
 */
export default function AppLogo({ inverted = false, className = "" }: Props) {
  const textColor = inverted ? "text-white" : "text-brand-800";
  const subtitleColor = inverted ? "text-white/60" : "text-brand-600";

  return (
    <div className={`inline-flex items-center gap-2 ${className}`} aria-label="Backtesting">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-500 text-sm font-bold text-white shadow-sm">
        B
      </span>
      <span className={`text-lg font-bold tracking-tight ${textColor}`}>
        Backtesting
        <span className={`ml-1 text-[9px] font-medium tracking-[0.12em] ${subtitleColor}`}>
          NOTATION
        </span>
      </span>
    </div>
  );
}
