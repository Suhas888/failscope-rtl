"""
Clustering methods B0–B3 for FailScope RTL.

B0 — Exact first-error line (no normalisation)
B1 — Normalised signature bucketing
B2 — TF-IDF + agglomerative clustering (fuzzy)
B3 — B2 + structured metadata features

All methods take a list of FailureRecord objects and return
a list of integer cluster labels (one per record).

Ground-truth labels are never accessed inside this module.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from failscope.signatures import (
    NormalisationConfig,
    compute_b0_key,
    compute_b1_signature,
)
from failscope.features import (
    build_tfidf_text,
    extract_structured_features,
)


@dataclass
class ClusteringConfig:
    """Configuration shared across clustering methods."""
    # B1
    norm_config: NormalisationConfig = field(default_factory=NormalisationConfig)

    # B2 / B3 TF-IDF
    max_features: int = 500
    ngram_range: tuple = (1, 2)
    min_df: int = 1
    sublinear_tf: bool = True
    use_idf: bool = False             # False preserves shared phrase similarity in short error logs

    # B2 / B3 agglomerative clustering
    distance_threshold: float = 0.5   # cosine distance threshold (0=identical, 1=orthogonal)
    linkage: str = "average"

    # B3 feature weights (text vs. structured)
    text_weight: float = 0.7
    structured_weight: float = 0.3


@dataclass
class ClusterResult:
    """Output of a clustering method."""
    method: str                           # "B0", "B1", "B2", "B3"
    labels: list[int]                     # one per input record
    n_clusters: int
    params: dict = field(default_factory=dict)  # logged for reproducibility
    warnings: list[str] = field(default_factory=list)


def cluster_b0(records: list) -> ClusterResult:
    """
    B0: Group by exact first-error line.

    No normalisation is applied. Fallback is documented when the
    first_error_message field is unavailable.
    """
    key_to_id: dict[str, int] = {}
    labels: list[int] = []

    for rec in records:
        key = compute_b0_key(rec)
        if key not in key_to_id:
            key_to_id[key] = len(key_to_id)
        labels.append(key_to_id[key])

    return ClusterResult(
        method="B0",
        labels=labels,
        n_clusters=len(key_to_id),
        params={"strategy": "exact_first_error_line", "normalisation": "none"},
    )


def cluster_b1(
    records: list,
    config: Optional[ClusteringConfig] = None,
) -> ClusterResult:
    """
    B1: Group by normalised signature.

    Applies documented deterministic normalisation rules.
    """
    cfg = config or ClusteringConfig()
    key_to_id: dict[str, int] = {}
    labels: list[int] = []

    for rec in records:
        key = compute_b1_signature(rec, cfg.norm_config)
        if key not in key_to_id:
            key_to_id[key] = len(key_to_id)
        labels.append(key_to_id[key])

    return ClusterResult(
        method="B1",
        labels=labels,
        n_clusters=len(key_to_id),
        params={
            "strategy": "normalised_signature",
            "normalisation": {
                "replace_timestamps": cfg.norm_config.replace_timestamps,
                "replace_hex_addresses": cfg.norm_config.replace_hex_addresses,
                "replace_seeds": cfg.norm_config.replace_seeds,
                "replace_paths": cfg.norm_config.replace_paths,
                "replace_variable_numbers": cfg.norm_config.replace_variable_numbers,
            },
        },
    )


def _safe_agglomerative(
    similarity_matrix: np.ndarray,
    distance_threshold: float,
    linkage: str,
    method_name: str,
    warn_list: list[str],
) -> list[int]:
    """
    Run agglomerative clustering on a pre-computed cosine similarity matrix.

    Converts similarity to distance first.
    Handles degenerate inputs (single record, all identical, NaN).
    """
    n = similarity_matrix.shape[0]

    if n == 0:
        return []
    if n == 1:
        return [0]

    # Convert similarity → distance, clip to [0, 1]
    distance_matrix = 1.0 - np.clip(similarity_matrix, 0.0, 1.0)
    np.fill_diagonal(distance_matrix, 0.0)

    # Replace NaN with max distance
    if np.any(np.isnan(distance_matrix)):
        warn_list.append(f"{method_name}: NaN in distance matrix; replacing with 1.0")
        distance_matrix = np.nan_to_num(distance_matrix, nan=1.0)

    try:
        from sklearn.cluster import AgglomerativeClustering

        model = AgglomerativeClustering(
            n_clusters=None,
            metric="precomputed",
            linkage=linkage,
            distance_threshold=distance_threshold,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            labels = model.fit_predict(distance_matrix)
        return labels.tolist()
    except Exception as exc:
        warn_list.append(f"{method_name}: clustering failed ({exc}); assigning all to cluster 0")
        return [0] * n


def _build_cosine_similarity(texts: list[str], cfg: ClusteringConfig) -> np.ndarray:
    """Compute TF-IDF cosine similarity matrix."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    if len(texts) == 0:
        return np.zeros((0, 0), dtype=np.float32)
    if len(texts) == 1:
        return np.array([[1.0]], dtype=np.float32)

    # Adjust min_df to avoid zero-vocabulary issues on tiny datasets
    actual_min_df = min(cfg.min_df, max(1, len(texts) // 2))

    vec = TfidfVectorizer(
        max_features=cfg.max_features,
        ngram_range=cfg.ngram_range,
        min_df=actual_min_df,
        sublinear_tf=cfg.sublinear_tf,
        use_idf=cfg.use_idf,
    )
    try:
        tfidf_mat = vec.fit_transform(texts)
        return cosine_similarity(tfidf_mat).astype(np.float32)
    except ValueError:
        # Vocabulary empty — all records identical or all stop words
        return np.ones((len(texts), len(texts)), dtype=np.float32)


def cluster_b2(
    records: list,
    config: Optional[ClusteringConfig] = None,
) -> ClusterResult:
    """
    B2: TF-IDF cosine similarity + agglomerative clustering.

    Uses first_error_message + bounded context lines as text input.
    """
    cfg = config or ClusteringConfig()
    warn_list: list[str] = []

    if not records:
        return ClusterResult(method="B2", labels=[], n_clusters=0,
                             params={"error": "empty input"})

    texts = [build_tfidf_text(rec) for rec in records]
    sim_matrix = _build_cosine_similarity(texts, cfg)

    labels = _safe_agglomerative(
        sim_matrix,
        cfg.distance_threshold,
        cfg.linkage,
        "B2",
        warn_list,
    )
    n_clusters = len(set(labels)) if labels else 0

    return ClusterResult(
        method="B2",
        labels=labels,
        n_clusters=n_clusters,
        params={
            "distance_threshold": cfg.distance_threshold,
            "linkage": cfg.linkage,
            "max_features": cfg.max_features,
            "ngram_range": list(cfg.ngram_range),
            "sublinear_tf": cfg.sublinear_tf,
        },
        warnings=warn_list,
    )


def cluster_b3(
    records: list,
    config: Optional[ClusteringConfig] = None,
) -> ClusterResult:
    """
    B3: B2 text similarity + structured metadata features.

    Combines text similarity matrix with structured feature cosine similarity.
    Weights are configurable and logged for reproducibility.

    Missing structured features are represented as 0 (absent/unknown).
    B3 degrades gracefully when structured features are all unavailable.
    """
    cfg = config or ClusteringConfig()
    warn_list: list[str] = []

    if not records:
        return ClusterResult(method="B3", labels=[], n_clusters=0,
                             params={"error": "empty input"})

    # Text similarity (same as B2)
    texts = [build_tfidf_text(rec) for rec in records]
    text_sim = _build_cosine_similarity(texts, cfg)

    # Structured feature similarity
    struct_mat = extract_structured_features(records)
    if struct_mat.shape[1] == 0 or np.all(struct_mat == 0):
        warn_list.append("B3: structured features all zero/unavailable; using text-only similarity")
        combined_sim = text_sim
    else:
        from sklearn.metrics.pairwise import cosine_similarity as cossim
        struct_sim = cossim(struct_mat).astype(np.float32)
        combined_sim = (
            cfg.text_weight * text_sim
            + cfg.structured_weight * struct_sim
        )

    labels = _safe_agglomerative(
        combined_sim,
        cfg.distance_threshold,
        cfg.linkage,
        "B3",
        warn_list,
    )
    n_clusters = len(set(labels)) if labels else 0

    return ClusterResult(
        method="B3",
        labels=labels,
        n_clusters=n_clusters,
        params={
            "distance_threshold": cfg.distance_threshold,
            "linkage": cfg.linkage,
            "max_features": cfg.max_features,
            "ngram_range": list(cfg.ngram_range),
            "text_weight": cfg.text_weight,
            "structured_weight": cfg.structured_weight,
        },
        warnings=warn_list,
    )


def run_all_methods(
    records: list,
    config: Optional[ClusteringConfig] = None,
) -> dict[str, ClusterResult]:
    """Run B0, B1, B2, B3 on the same records and return results keyed by method."""
    return {
        "B0": cluster_b0(records),
        "B1": cluster_b1(records, config),
        "B2": cluster_b2(records, config),
        "B3": cluster_b3(records, config),
    }
