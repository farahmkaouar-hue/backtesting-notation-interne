import numpy as np
import pandas as pd


def simulate_from_population(data: pd.DataFrame, rows: int, seed: int = 42) -> pd.DataFrame:
    """Génère des données synthétiques uniquement pour la charge et les tests UI.

    Les colonnes numériques sont simulées par copule gaussienne sur leurs rangs ;
    les colonnes catégorielles suivent les fréquences observées. Aucune sortie ne
    peut être utilisée dans une décision de validation réelle.
    """
    rng = np.random.default_rng(seed)
    numeric = data.select_dtypes(include="number").columns.tolist()
    result = pd.DataFrame(index=range(rows))
    if numeric:
        base = data[numeric].apply(pd.to_numeric, errors="coerce")
        usable = [c for c in numeric if base[c].notna().sum() >= 3]
        if usable:
            corr = base[usable].corr(method="spearman").fillna(0).to_numpy(copy=True)
            corr = (corr + corr.T) / 2
            eigenvalues, eigenvectors = np.linalg.eigh(corr)
            corr = eigenvectors @ np.diag(np.maximum(eigenvalues, 1e-6)) @ eigenvectors.T
            scale = np.sqrt(np.diag(corr))
            corr = corr / np.outer(scale, scale)
            latent = rng.multivariate_normal(np.zeros(len(usable)), corr, size=rows)
            for idx, col in enumerate(usable):
                sample = base[col].dropna().sort_values().to_numpy()
                ranks = np.clip(((latent[:, idx].argsort().argsort() + 0.5) / rows * len(sample)).astype(int), 0, len(sample) - 1)
                result[col] = sample[ranks]
        for col in set(numeric) - set(usable):
            result[col] = rng.choice(base[col].dropna().to_numpy(), size=rows) if base[col].notna().any() else np.nan
    for col in data.columns.difference(numeric):
        values = data[col].dropna()
        result[col] = rng.choice(values.to_numpy(), size=rows) if not values.empty else np.nan
    result["synthetic_data"] = True
    return result
