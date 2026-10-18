"""Check mode: ISO 10816 severity zone + fault-signature rules.

No history - every call is a one-shot classification of a single
KX134Features row, per planning/spec.md. Thresholds are starting points
(spec's own words); tune them once T2-T5 induced-fault data exists.

Single Z-axis for now (see kx134_sampler.cpp), so the imbalance rule's
"radial > axial" check is deferred until a second axis is compared.
"""

import math

from features import KX134Features

# ISO 10816-1 Class I (small machines) velocity RMS zone boundaries, mm/s.
ISO_ZONE_A_B = 0.71
ISO_ZONE_B_C = 1.8
ISO_ZONE_C_D = 4.5

IMBALANCE_1X_SHARE = 0.60  # 1x >= 60% of 10-800 Hz velocity energy
LOOSENESS_HARMONIC_RATIO = 0.50  # 2x+3x >= 50% of 1x (acceleration amplitude)
BEARING_HIGH_BAND_RATIO = 0.30  # 400-800 Hz share of 10-800 Hz band energy
BEARING_KURTOSIS = 4.0
OVERLOAD_SPEED_DROP = 0.05  # rotation Hz below rated by >5%


def iso_zone(velocity_rms_mm_s: float) -> str:
    if velocity_rms_mm_s < ISO_ZONE_A_B:
        return "A"
    if velocity_rms_mm_s < ISO_ZONE_B_C:
        return "B"
    if velocity_rms_mm_s < ISO_ZONE_C_D:
        return "C"
    return "D"


def evaluate(f: KX134Features, rated_hz: float | None = None) -> dict:
    """Returns {"zone": "A".."D", "faults": [...]} - faults is a list of
    strings naming each fault signature that matched."""
    faults = []

    if f.rotation_hz > 0 and f.velocity_rms_mm_s > 0:
        omega = 2.0 * math.pi * f.rotation_hz
        vel_1x_mm_s = f.amp_1x_g * 9.80665 / omega * 1000.0
        share_1x = (vel_1x_mm_s ** 2) / (2.0 * f.velocity_rms_mm_s ** 2)
        if share_1x >= IMBALANCE_1X_SHARE:
            faults.append("imbalance")

    if f.amp_1x_g > 0:
        harmonic_ratio = (f.amp_2x_g + f.amp_3x_g) / f.amp_1x_g
        if harmonic_ratio >= LOOSENESS_HARMONIC_RATIO:
            faults.append("looseness_or_misalignment")

    if f.band_high_ratio >= BEARING_HIGH_BAND_RATIO and f.kurtosis > BEARING_KURTOSIS:
        faults.append("bearing_or_impact")

    if rated_hz and f.rotation_hz > 0:
        if f.rotation_hz < rated_hz * (1.0 - OVERLOAD_SPEED_DROP):
            faults.append("overload")

    return {"zone": iso_zone(f.velocity_rms_mm_s), "faults": faults}
