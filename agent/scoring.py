"""Load the provided model and score a batch with it. Nothing else.

The model is used exactly as given: no retraining, no tuning, no post-hoc
adjustment of its output. Two guards around it, both of which exist because the
failure they prevent is silent rather than loud:

  1. Version check. Unpickling a scikit-learn estimator under a different version
     than it was saved with can succeed and still behave differently. sklearn
     raises InconsistentVersionWarning; a warning nobody reads is not a control,
     so this module turns it into a refusal.

  2. Feature-contract check. The pipeline selects columns by name, so a frame with
     the right names in the wrong order still scores - and a frame with an extra
     column may not. Asserting the exact contract up front turns a subtle wrong
     answer into an obvious crash.
"""

from __future__ import annotations

import pickle
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.exceptions import InconsistentVersionWarning

from .contracts import FEATURE_COLUMNS, ContractError


@dataclass
class LoadedModel:
    pipeline: object
    saved_with_sklearn: str
    running_sklearn: str
    path: Path

    def describe(self) -> str:
        clf = self.pipeline.named_steps["clf"]
        return (f"{type(clf).__name__}(n_estimators={clf.n_estimators}, max_depth={clf.max_depth}) "
                f"saved with sklearn {self.saved_with_sklearn}")


def load_model(path: Path, allow_version_mismatch: bool = False) -> LoadedModel:
    # scikit-learn strips _sklearn_version off the estimator while unpickling and
    # signals any mismatch through InconsistentVersionWarning instead. So the
    # warning is the contract: catch it, and refuse rather than log it.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", category=InconsistentVersionWarning)
        with path.open("rb") as fh:
            pipeline = pickle.load(fh)

    mismatches = [w.message for w in caught if isinstance(w.message, InconsistentVersionWarning)]
    if mismatches and not allow_version_mismatch:
        m = mismatches[0]
        raise ContractError(
            f"model.pkl was saved with scikit-learn {m.original_sklearn_version}, this "
            f"environment runs {m.current_sklearn_version}. Loading across versions can "
            f"succeed and still score differently. Install the pinned version from "
            f"requirements.txt, or pass allow_version_mismatch=True having understood the risk."
        )
    # No warning means sklearn considers the versions equivalent.
    saved = mismatches[0].original_sklearn_version if mismatches else sklearn.__version__

    contract = tuple(getattr(pipeline, "feature_names_in_", ()))
    if contract != FEATURE_COLUMNS:
        raise ContractError(
            "the model's feature contract is not what this code expects.\n"
            f"  model expects: {contract}\n"
            f"  code assumes:  {FEATURE_COLUMNS}"
        )

    return LoadedModel(pipeline=pipeline, saved_with_sklearn=saved,
                       running_sklearn=sklearn.__version__, path=path)


def score_batch(model: LoadedModel, df: pd.DataFrame) -> np.ndarray:
    """Probability of converting within 90 days, one per row, in the row order given.

    The frame is rebuilt as df[FEATURE_COLUMNS] so column order is guaranteed
    rather than assumed, and identifier columns cannot leak into the model.
    """
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise ContractError(f"cannot score: missing feature columns {missing}")

    features = df.loc[:, list(FEATURE_COLUMNS)]
    scores = model.pipeline.predict_proba(features)[:, 1]

    # predict_proba cannot return values outside [0, 1], so this is not defensive
    # programming against sklearn - it catches the case where `model` has been
    # swapped for something that only looks like a classifier.
    if not np.all((scores >= 0) & (scores <= 1)):
        raise ContractError("model returned values outside [0, 1]; this is not a probability")

    return scores
