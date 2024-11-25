"""
Base object used to set up explainability objects.
"""

import numpy as np
from sklearn.base import BaseEstimator
from sklearn.utils import check_random_state
from .utils._parallelize import parallel_loop
from .utils import check_feature_names, check_inputs, check_measure, check_qoi
from .visualization._visualization import ShaRPViz


class ShaRP(BaseEstimator):
    """
    The ShaRP (Shapley for Rankings and Preferences) class provides a novel framework for
    explaining the contributions of features to various aspects of ranked outcomes. Built
    on Shapley values, it quantifies feature importance for rankings, which is fundamentally
    different from feature importance in classification or regression. This framework is essential
    for understanding, auditing, and improving algorithmic ranking systems in critical domains
    such as hiring, education, and lending.

    ShaRP extends the Quantitative Input Influence (QII) framework to compute feature contributions
    to multiple ranking-specific Quantities of Interest (QoIs). These QoIs include:
    - Score: Contribution of features to an item's score.
    - Rank: Impact of features on an item's rank.
    - Top-k: Influence of features on whether an item appears in the top-k positions.
    - Pairwise Preference: Contribution of features to the relative order between two items.

    ShaRP uses Shapley values, a cooperative game theory concept, to distribute the "value" of
    a ranked outcome among the features. For each QoI, the class:
    - Constructs feature coalitions by masking subsets of features.
    - Evaluates the impact of these coalitions on the QoI using a payoff function.
    - Aggregates the marginal contributions of features across all possible coalitions
    to compute their Shapley values.

    This algorithm is an implementation of Shapley for Rankings and Preferences (ShaRP),
    as presented in [1]_.

    Parameters
    ----------
    qoi : str, optional
        The quantity of interest to compute feature contributions for. Options include:
        - "score" : Contribution to an item's score.
        - "rank" : Contribution to an item's rank.
        - "top-k" : Contribution to whether an item appears in the top-k.
        - "pairwise" : Contribution to the relative order between two items.
        By default, in method ``fit()``, "rank" will be used.
        If QoI is None, ``target_function`` and parameters ``X`` and ``y`` need to be passed.

    target_function : function, optional
        A custom function defining the outcome of interest for the data. Ignored if `qoi` is specified.

    measure : str, default="shapley"
        The method used to compute feature contributions. Options include:
        - "set"
        - "marginal"
        - "shapley"
        - "banzhaff"

    sample_size : int, optional
        The number of perturbations to apply per data point when calculating
        feature importance. Default is `None`, which uses all available samples.

    coalition_size : int, optional
        The maximum size of feature coalitions to consider. Default is `None`,
        which uses all features except one.

    replace : bool, default=False
        Whether to sample feature values with replacement during perturbation.

    random_state : int, RandomState instance, or None, optional
        Seed or random number generator for reproducibility. Default is `None`.

    n_jobs : int, default=1
        Number of jobs to run in parallel for computations. Use `-1` to use all
        available processors.

    verbose : int, default=0
        Verbosity level. Use 0 for no output and higher numbers for more verbose output.

    kwargs : dict, optional
        Additional parameters such as:
        - ``X`` : array-like, reference input data.
        - ``y`` : array-like, target outcomes for the reference data.

    Notes
    -----
    See the original paper: [1]_ for more details.

    References
    ----------
    .. [1] V. Pliatsika, J. Fonseca, T. Wang, J. Stoyanovich, "ShaRP: Explaining
       Rankings with Shapley Values", Under submission.
    """

    def __init__(
        self,
        qoi=None,
        target_function=None,
        measure="shapley",
        sample_size=None,
        coalition_size=None,
        replace=False,
        random_state=None,
        n_jobs=1,
        verbose=0,
        **kwargs
    ):
        self.qoi = qoi
        self.target_function = target_function
        self.measure = measure
        self.sample_size = sample_size
        self.coalition_size = coalition_size
        self.replace = replace
        self.random_state = random_state
        self.n_jobs = n_jobs
        self.verbose = verbose
        self.plot = ShaRPViz(self)
        self._X = kwargs["X"] if "X" in kwargs.keys() else None
        self._y = kwargs["y"] if "y" in kwargs.keys() else None

    def fit(self, X, y=None):
        X_, y_ = check_inputs(X, y)

        self._X = X_
        self._y = y_

        self._rng = check_random_state(self.random_state)

        if self.qoi is None:
            self.qoi_ = check_qoi(
                "rank",
                target_function=self.target_function,
                X=X_,
            )
        elif isinstance(self.qoi, str):
            self.qoi_ = check_qoi(
                self.qoi,
                target_function=self.target_function,
                X=X_,
            )
        else:
            self.qoi_ = self.qoi

        self.feature_names_ = check_feature_names(X)

        self.measure_ = check_measure(self.measure)

    def individual(self, sample, X=None, y=None, **kwargs):
        """
        set_cols_idx should be passed in kwargs if measure is marginal
        """
        if X is None:
            X = self.qoi_.X

        X_, y_ = check_inputs(X, y)

        if "set_cols_idx" in kwargs.keys():
            set_cols_idx = kwargs["set_cols_idx"]
        else:
            set_cols_idx = None

        if "coalition_size" in kwargs.keys():
            coalition_size = kwargs["coalition_size"]
        elif self.coalition_size is not None:
            coalition_size = self.coalition_size
        else:
            coalition_size = X_.shape[-1] - 1

        if isinstance(sample, int):
            sample = X_[sample]

        if "sample_size" in kwargs.keys():
            sample_size = kwargs["sample_size"]
        elif self.sample_size is not None:
            sample_size = self.sample_size
        else:
            sample_size = X_.shape[0]

        verbosity = kwargs["verbose"] if "verbose" in kwargs.keys() else self.verbose
        influences = parallel_loop(
            lambda col_idx: self.measure_(
                row=sample,
                col_idx=col_idx,
                set_cols_idx=set_cols_idx,
                X=X_,
                qoi=self.qoi_,
                sample_size=sample_size,
                coalition_size=coalition_size,
                replace=self.replace,
                rng=self._rng,
            ),
            range(len(self.feature_names_)),
            n_jobs=self.n_jobs,
            progress_bar=verbosity,
        )

        return influences

    def feature(self, feature, X=None, y=None, **kwargs):
        """
        set_cols_idx should be passed in kwargs if measure is marginal
        """
        X_, y_ = check_inputs(X, y)

        col_idx = (
            self.feature_names_.index(feature) if type(feature) is str else feature
        )

        if "set_cols_idx" in kwargs.keys():
            set_cols_idx = kwargs["set_cols_idx"]
        else:
            set_cols_idx = None

        if "coalition_size" in kwargs.keys():
            coalition_size = kwargs["coalition_size"]
        elif self.coalition_size is not None:
            coalition_size = self.coalition_size
        else:
            coalition_size = X_.shape[1] - 1

        if "sample_size" in kwargs.keys():
            sample_size = kwargs["sample_size"]
        elif self.sample_size is not None:
            sample_size = self.sample_size
        else:
            sample_size = X_.shape[0]

        influences = []
        for sample_idx in range(X_.shape[0]):
            sample = X_[sample_idx]
            cell_influence = self.measure_(
                row=sample,
                col_idx=col_idx,
                set_cols_idx=set_cols_idx,
                X=X_,
                qoi=self.qoi_,
                sample_size=sample_size,
                coalition_size=coalition_size,
                replace=self.replace,
                rng=self._rng,
            )
            influences.append(cell_influence)

        return np.mean(influences)

    def all(self, X=None, y=None, **kwargs):
        """
        set_cols_idx should be passed in kwargs if measure is marginal
        """
        X_ref = self._X if self._X is not None else check_inputs(X)[0]
        X_, y_ = check_inputs(X, y)

        influences = parallel_loop(
            lambda sample_idx: self.individual(
                X_[sample_idx], X_ref, verbose=False, **kwargs
            ),
            range(X_.shape[0]),
            n_jobs=self.n_jobs,
            progress_bar=self.verbose,
        )

        return np.array(influences)

    def pairwise(self, sample1, sample2, **kwargs):
        """
        Compare two samples, or one sample against a set of samples.
        If `sample1` or `sample2` are of type `int` or `list`, `X` also needs to be
        passed.

        set_cols_idx should be passed in kwargs if measure is marginal
        """
        if "X" in kwargs.keys():
            X = kwargs["X"]

            if type(sample1) in [int, list]:
                sample1 = X[sample1]

            if type(sample2) in [int, list]:
                sample2 = X[sample2]

        sample2 = sample2.reshape(1, -1) if sample2.ndim == 1 else sample2

        if "sample_size" in kwargs.keys():
            sample_size = kwargs["sample_size"]
        elif self.sample_size is not None:
            sample_size = (
                sample2.shape[0]
                if self.sample_size > sample2.shape[0]
                else self.sample_size
            )
        else:
            sample_size = sample2.shape[0]

        if "coalition_size" in kwargs.keys():
            coalition_size = kwargs["coalition_size"]
        elif self.coalition_size is not None:
            coalition_size = self.coalition_size
        else:
            coalition_size = sample1.shape[-1] - 1

        return self.individual(
            sample1,
            X=sample2,
            sample_size=sample_size,
            coalition_size=coalition_size,
            **kwargs
        )

    def pairwise_set(self, samples1, samples2, **kwargs):
        """
        set_cols_idx should be passed in kwargs if measure is marginal
        pairs is a list of tuples of indexes
        """
        contributions = parallel_loop(
            lambda samples: self.pairwise(*samples, verbose=False, **kwargs),
            zip(samples1, samples2),
            n_jobs=self.n_jobs,
            progress_bar=self.verbose,
        )

        return np.array(contributions)
