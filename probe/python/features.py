"""Parses the `get_kx134_features` CSV row from the MCU into a named tuple.

Field order matches kx134_get_features() in probe/sketch/kx134_sampler.cpp.
"""

from collections import namedtuple

KX134Features = namedtuple(
    "KX134Features",
    [
        "rotation_hz",
        "velocity_rms_mm_s",
        "amp_1x_g",
        "amp_2x_g",
        "amp_3x_g",
        "band_high_ratio",
        "kurtosis",
        "crest",
    ],
)


def parse_kx134_features(row: str) -> KX134Features:
    parts = [float(v) for v in row.split(",")]
    return KX134Features(*parts)
