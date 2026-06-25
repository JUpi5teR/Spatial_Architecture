# coding: utf-8
"""Cortical histology reference data for DLPFC layers.

Provides the layer-table data from BIOLOGY_REPORT.md as a pure-data model
that can be consumed by any view without importing UI dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LayerInfo:
    """One row of the cortical histology reference table."""
    layer_id: str
    name_cn: str
    name_en: str
    neuron_type: str
    thickness: str


_LAYER_TABLE = (
    LayerInfo("L1", "分子层", "Molecular", "几乎无神经元，多为切线纤维", "薄"),
    LayerInfo("L2", "外颗粒层", "External Granular", "小颗粒细胞", "很薄"),
    LayerInfo("L3", "外锥体层", "External Pyramidal", "中等锥体细胞", "较厚"),
    LayerInfo("L4", "内颗粒层", "Internal Granular", "密集小颗粒细胞", "极薄"),
    LayerInfo("L5", "内锥体层", "Internal Pyramidal", "大锥体细胞，含Betz细胞", "厚"),
    LayerInfo("L6", "多形层", "Multiform", "梭形细胞", "中等"),
    LayerInfo("WM", "白质", "White Matter", "髓鞘化轴突纤维", "-"),
)

_BY_ID = {li.layer_id: li for li in _LAYER_TABLE}


def get_layer_table():
    return _LAYER_TABLE


def lookup_layer(label):
    if not label or str(label).upper() == "NA":
        return None
    s = str(label).strip()
    if s in _BY_ID:
        return _BY_ID[s]
    if s.lower().startswith("layer"):
        lid = "L" + s[5:]
        return _BY_ID.get(lid)
    try:
        n = int(s)
        if 1 <= n <= 6:
            return _BY_ID.get("L" + str(n))
    except ValueError:
        pass
    return None