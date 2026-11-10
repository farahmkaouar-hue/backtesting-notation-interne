export type TrafficLight = "vert" | "orange" | "rouge" | "nc";
export type ModelSegment = "professionnel" | "corporate_ef" | "corporate_sef";
export type PageView =
  | "login"
  | "dashboard"
  | "data"
  | "backtesting"
  | "recalibration"
  | "supervisor"
  | "reports";

export interface User {
  name: string;
  role: "analyste" | "superviseur" | "admin";
  initials: string;
}

export interface RatingClassRow {
  classe: number;
  label: string;
  effectif: number;
  pdAssignee: number;
  defautsObserves: number;
  tauxDefautObserve: number;
  ecartCalibration: number;
  trafficLight: TrafficLight;
  jeffreyPValue: number;
  binomialPValue: number;
}

export interface ModelBacktestResult {
  segment: ModelSegment;
  segmentLabel: string;
  totalDossiers: number;
  totalDefauts: number;
  tauxDefautGlobal: number;
  periodeInitiale: string;
  periodePerformance: string;
  horizonMois: number;
  auc: number;
  gini: number;
  ks: number;
  psi: number;
  hosmerLemeshowPValue: number;
  ratingClasses: RatingClassRow[];
  alertes: Alerte[];
  decision: DecisionRecalibrage;
  overrideRate: number;
  overrideDirectionnel: boolean;
  insuffisanceEvenements: boolean;
}

export interface Alerte {
  id: string;
  type: "calibration" | "discrimination" | "stabilite" | "donnees" | "evenements";
  severite: TrafficLight;
  titre: string;
  description: string;
  classe?: number;
  action: string;
}

export interface DecisionRecalibrage {
  verdict: "maintien" | "recalibrage_simple" | "refonte" | "non_concluant";
  label: string;
  justification: string;
  urgence: TrafficLight;
}

export interface DataQualityReport {
  totalLignes: number;
  doublons: number;
  valeursManquantes: number;
  incohérencesDate: number;
  dossierExclus: number;
  lignesValides: number;
  colonnesDetectees: string[];
  segmentDistribution: { segment: string; count: number }[];
  alertesQualite: { code: string; message: string; severite: TrafficLight }[];
}

export interface HistoricalRun {
  id: string;
  date: string;
  utilisateur: string;
  segment: string;
  verdict: string;
  gini: number | null;
  auc: number | null;
  psi: number | null;
  decision: string;
  rapport: string;
}

export interface MigrationMatrixRow {
  classeInitiale: number;
  transitions: number[];
  total: number;
}
