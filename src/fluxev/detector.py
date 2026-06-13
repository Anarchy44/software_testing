from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class DetectionResult:
    """Result of FluxEV anomaly detection.

    Paper-aligned notation:
        x   = raw values (after imputation)
        E   = fluctuation = x - EWMA prediction
        F   = first-step smoothing output (Delta_sigma, clipped to >=0)
        S   = second-step smoothing output (anomaly score, periodic-diff clipped)
    """

    values: np.ndarray  # x: imputed raw values
    prediction: np.ndarray  # EWMA predicted values
    fluctuation: np.ndarray  # E = x - prediction
    # First-step smoothing output F (also available as 'smoothed' for compat)
    F: np.ndarray
    # Second-step smoothing output S (the final anomaly score)
    S: np.ndarray
    score: np.ndarray  # alias for S (backward compatible)
    threshold: float
    labels: np.ndarray

    # Backward-compatible aliases (deprecated)
    @property
    def smoothed(self) -> np.ndarray:
        """Backward-compatible alias for F (first-step smoothing output)."""
        return self.F

    @property
    def seasonal_expected(self) -> np.ndarray:
        """Backward-compatible: returns zeros (not used in paper-aligned version)."""
        return np.zeros_like(self.values)


class FluxEVDetector:
    """FluxEV anomaly detector, aligned with WSDM 2021 paper.

    Implements the full FluxEV pipeline:
        1. Dual-strategy missing value imputation
        2. EWMA-based fluctuation extraction
        3. First-step smoothing (Delta_sigma / std-dev increase)
        4. Second-step smoothing (periodic max-diff with drift tolerance)
        5. SPOT automatic thresholding via MOM-POT

    Paper parameters (see Section 4):
        s     : EWMA window & first-step smoothing window (paper default 10)
        alpha : EWMA decay factor (0 < alpha <= 1)
        d     : half-window for data-drift tolerance (paper default 2)
        p     : number of past periods used for periodic comparison (paper default 5)
        l     : period length (e.g. 60 for 1h at 1-min intervals)
        k     : number of points for POT initialization (paper default ≈1000)
        risk  : false-positive risk coefficient (paper default 0.01)
        base_quantile : initial POT threshold quantile (paper default 0.98)
    """

    def __init__(
        self,
        # Paper-aligned primary parameters
        s: int = 10,
        alpha: float = 0.3,
        d: int = 2,
        p: int = 5,
        l: int | None = None,
        k: int = 1000,
        risk: float = 0.01,
        base_quantile: float = 0.98,
        # Backward-compatible legacy parameters (mapped to paper params)
        predictor_window: int | None = None,
        smooth_window: int | None = None,
        period: int | None = None,
        warmup: int | None = None,
    ) -> None:
        # Map legacy params if provided
        if predictor_window is not None:
            s = predictor_window
        if smooth_window is not None:
            s = smooth_window
        if period is not None:
            l = period

        if l is None:
            raise ValueError("period (l) must be specified")

        self.s = int(s)
        self.alpha = float(alpha)
        self.d = int(d)
        self.p = int(p)
        self.l = int(l)
        self.k = int(k)
        self.risk = float(risk)
        self.base_quantile = float(base_quantile)

        # Legacy access for backward compat
        self.predictor_window = self.s
        self.smooth_window = self.s
        self.period = self.l
        # Warmup = startup cost (cannot compute S before this index)
        self.warmup = 2 * self.s + self.d + self.l * (self.p - 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, values: np.ndarray | pd.Series) -> DetectionResult:
        """Run the full FluxEV detection pipeline on a 1-D KPI series.

        Args:
            values: 1-D array-like of metric values (may contain NaN).

        Returns:
            DetectionResult with all intermediate and final outputs.
        """
        # ---- Step 1: Data preprocessing (missing value imputation) ----
        x = self._impute(values)

        # ---- Step 2: Fluctuation extraction via EWMA prediction ----
        prediction = self._ewma_predict(x)
        E = x - prediction  # fluctuation (prediction error)

        # ---- Step 3: First-step smoothing (std-dev change) ----
        F = self._first_smooth(E)

        # ---- Step 4: Second-step smoothing (periodic max-diff) ----
        S = self._second_smooth(F)

        # ---- Step 5: Automatic thresholding via SPOT (MOM-POT) ----
        threshold, labels = self._spot_threshold(F, S, x, prediction, E)

        return DetectionResult(
            values=x,
            prediction=prediction,
            fluctuation=E,
            F=F,
            S=S,
            score=S,
            threshold=threshold,
            labels=labels,
        )

    # ------------------------------------------------------------------
    # Step 1: Dual-strategy missing value imputation
    # ------------------------------------------------------------------

    def _impute(self, values: np.ndarray | pd.Series) -> np.ndarray:
        """Dual-strategy imputation per FluxEV Section 4.1.

        - Short gaps (< 5 points): linear interpolation.
        - Long gaps (>= 5 points): period-fill = X_{t-l} + (mu_t - mu_{t-1})/2.
        """
        series = pd.Series(values, dtype="float64", copy=True)
        n = len(series)

        # Identify missing segments
        is_missing = series.isna()
        if not is_missing.any():
            return series.to_numpy()

        # Fill short gaps with linear interpolation
        filled = series.interpolate(method="linear", limit_direction="both", limit_area="inside")

        # Find long gaps and fill them with period-fill strategy
        missing_starts = []
        in_gap = False
        gap_start = 0
        for i in range(n):
            if is_missing.iloc[i] and not in_gap:
                gap_start = i
                in_gap = True
            elif not is_missing.iloc[i] and in_gap:
                gap_len = i - gap_start
                if gap_len >= 5:
                    missing_starts.append((gap_start, i))
                in_gap = False
        if in_gap:
            gap_len = n - gap_start
            if gap_len >= 5:
                missing_starts.append((gap_start, n))

        # Period-fill for long gaps
        l = self.l
        for gs, ge in missing_starts:
            # Compute period means around the gap
            period_start = max(0, gs - l)
            period_end = min(n, ge + l)
            mu_prev = filled.iloc[max(0, gs - 2 * l):max(0, gs - l)].mean()
            mu_curr = filled.iloc[gs:ge].mean() if not filled.iloc[gs:ge].isna().all() else 0
            bias = (mu_curr - mu_prev) / 2.0 if pd.notna(mu_prev) and pd.notna(mu_curr) else 0.0

            for i in range(gs, ge):
                j = i - l
                if j >= 0 and pd.notna(filled.iloc[j]):
                    filled.iloc[i] = filled.iloc[j] + bias
                else:
                    # Fallback: use forward fill from nearest valid value
                    pass  # linear interpolation already attempted

        # Final forward/backward fill for any remaining NaNs
        filled = filled.ffill().bfill()

        return filled.to_numpy()

    # ------------------------------------------------------------------
    # Step 2: EWMA fluctuation extraction
    # ------------------------------------------------------------------

    def _ewma_predict(self, x: np.ndarray) -> np.ndarray:
        """EWMA predictor per FluxEV Equation (1).

        EWMA(X_{i-s, i-1}) = weighted average of previous s values,
        with exponentially decaying weights controlled by alpha.

        Then E_i = X_i - EWMA(...)  (computed in detect()).
        """
        series = pd.Series(x, dtype="float64")

        # Use pandas ewm with adjust=True for the exact paper formula:
        #   ewma[i] = sum_{j=0}^{s-1} (1-alpha)^j * x[i-1-j]
        #           / sum_{j=0}^{s-1} (1-alpha)^j
        # Shift by 1 because EWMA should use only PAST values (not current)
        ewma = series.shift(1).ewm(alpha=self.alpha, adjust=True).mean()

        # Fill NaN at the beginning with the first valid value
        ewma = ewma.bfill()

        return ewma.to_numpy()

    # ------------------------------------------------------------------
    # Step 3: First-step smoothing (std-dev change)
    # ------------------------------------------------------------------

    def _first_smooth(self, E: np.ndarray) -> np.ndarray:
        """First-step smoothing per FluxEV Equation (3-4).

        Delta_sigma = sigma(E_{i-s, i}) - sigma(E_{i-s, i-1})
        F_i = max(Delta_sigma, 0)

        Points that do not increase the local standard deviation
        are considered normal and their fluctuation is set to zero.
        """
        n = len(E)
        s = self.s
        F = np.zeros(n, dtype="float64")

        for i in range(s, n):
            window_current = E[i - s:i + 1]
            window_prev = E[i - s:i]
            std_current = float(np.std(window_current, ddof=1))
            std_prev = float(np.std(window_prev, ddof=1))
            delta = std_current - std_prev
            F[i] = max(delta, 0.0)

        # For early points (i < s): use absolute fluctuation as fallback
        # (These will be inside warmup zone and not used for detection)
        for i in range(min(s, n)):
            F[i] = abs(E[i])

        return F

    # ------------------------------------------------------------------
    # Step 4: Second-step smoothing (periodic max-diff)
    # ------------------------------------------------------------------

    def _second_smooth(self, F: np.ndarray) -> np.ndarray:
        """Second-step smoothing per FluxEV Equation (5-7).

        M_{i-d} = max(F_{i-2d, ..., i})      -- drift-tolerant local maximum
        Delta_Fi = F_i - max(M_{i-l(p-1)}, ..., M_{i-l})  -- subtract historical ceiling
        S_i = max(Delta_Fi, 0)                -- clip negative values

        Parameters:
            d = drift half-window
            l = period length
            p = number of past periods for comparison
        """
        n = len(F)
        d = self.d
        l = self.l
        p = self.p

        # Compute the drift-tolerant maxima M
        M = np.zeros(n, dtype="float64")
        half_window = 2 * d  # window from i-2d to i
        for i in range(n):
            start = max(0, i - half_window)
            M[i] = float(np.max(F[start:i + 1]))

        # Second-step smoothing: subtract historical maximum
        S = np.zeros(n, dtype="float64")
        for i in range(n):
            # Collect M values from same time slot in past p periods
            historical_maxima = []
            for period_offset in range(1, p + 1):
                j = i - period_offset * l
                if j >= 0:
                    historical_maxima.append(M[j])
            if historical_maxima:
                hist_max = max(historical_maxima)
                S[i] = max(F[i] - hist_max, 0.0)
            else:
                S[i] = F[i]  # no history available; keep raw F value

        return S

    # ------------------------------------------------------------------
    # Step 5: SPOT automatic thresholding via MOM-POT
    # ------------------------------------------------------------------

    def _spot_threshold(
        self,
        F: np.ndarray,
        S: np.ndarray,
        x: np.ndarray,
        prediction: np.ndarray,
        E: np.ndarray,
    ) -> tuple[float, np.ndarray]:
        """Apply SPOT thresholding with MOM-POT on the anomaly score S.

        For batch mode: uses all post-warmup data for calibration.
        For small datasets where k is a constraint, falls back gracefully.
        """
        n = len(S)
        warmup = self.warmup  # = 2s + d + l(p-1)

        # Batch mode: use all post-warmup data for POT calibration
        # (Streaming would only use next k points; here we need as many peaks as possible)
        calib_start = warmup
        calib_end = n
        if calib_end - calib_start < 30:
            calib_start = max(0, n // 4)
            calib_end = n

        # Fit threshold from calibration region
        threshold = self._mom_pot_threshold(S[calib_start:calib_end])

        # Label anomalies
        labels = np.zeros(n, dtype=int)
        labels[:warmup] = 0  # warmup zone: force normal
        for i in range(warmup, n):
            if S[i] > threshold:
                labels[i] = 1

        return float(threshold), labels

    # ------------------------------------------------------------------
    # MOM-POT threshold estimation (paper-aligned)
    # ------------------------------------------------------------------

    def _mom_pot_threshold(self, warm_scores: np.ndarray) -> float:
        """Estimate threshold via Method-of-Moments Peaks-Over-Threshold.

        Per FluxEV Equation (8-11):
            t = base_quantile of S
            Excess = {S_i - t | S_i > t}
            Fit GPD(shape=gamma, scale=sigma) to Excess via MOM
            th_F = t + (sigma/gamma) * ((risk * n / N_t)^{-gamma} - 1)
        """
        warm_scores = np.asarray(warm_scores, dtype=float)
        warm_scores = warm_scores[np.isfinite(warm_scores)]
        if warm_scores.size < 20:
            return float(np.nanquantile(warm_scores, 0.95))

        # Try paper-default base_quantile (0.98); fall back to lower quantiles
        # if not enough peaks for reliable MOM estimation
        for q in (self.base_quantile, 0.95, 0.90, 0.85):
            t = float(np.nanquantile(warm_scores, q))
            excess = warm_scores[warm_scores > t] - t
            if excess.size >= 5:
                break

        if excess.size < 5:
            # Too few peaks: fall back to a moderate quantile
            return float(np.nanquantile(warm_scores, 0.90))

        # MOM estimation of GPD parameters
        mu = float(np.mean(excess))  # sample mean
        s2 = float(np.var(excess, ddof=1))  # sample variance
        if mu <= 0 or s2 <= 0:
            return float(np.nanquantile(warm_scores, 0.95))

        # Equation (10-11) from paper:
        # sigma_hat = (mu/2) * (1 + mu^2/s2)
        # gamma_hat = 1/2 * (1 - mu^2/s2)
        gamma = 0.5 * (1.0 - (mu * mu / s2))
        gamma = float(np.clip(gamma, -0.45, 0.45))
        sigma = max(mu * (1.0 - gamma), 1e-6)  # = mu/2 * (1 + mu^2/s2)

        # Threshold formula Equation (9):
        # th_F = t + (sigma/gamma) * ((risk * n / N_t)^{-gamma} - 1)
        n_total = warm_scores.size
        n_peaks = excess.size
        ratio = max((self.risk * n_total) / n_peaks, 1.0 + 1e-6)

        if abs(gamma) < 1e-6:
            return t + sigma * np.log(1.0 / ratio)

        # th_F = t + (sigma/gamma) * (ratio^{-gamma} - 1)
        return t + (sigma / gamma) * (ratio ** (-gamma) - 1.0)
