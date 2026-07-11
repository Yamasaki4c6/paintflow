"""
lineart.py — 線画抽出ステージ

入力(BGR)→ 線マスク(bool, True=線)と線アルファ(float32 0..1)を作る。
3モード:
  adaptive : 局所適応二値化。スキャン原稿・ラフの抽出に強い
  xdog     : eXtended Difference of Gaussians。グレー諧調から漫画線を生成
  canny    : エッジ検出。3DCGレンダ画像の輪郭線化などに
"""
from __future__ import annotations

import cv2
import numpy as np

from .params import LineArtParams


def _preprocess(bgr: np.ndarray, p: LineArtParams) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    if p.invert_input:
        gray = 255 - gray
    if p.denoise > 0:
        gray = cv2.bilateralFilter(gray, d=0, sigmaColor=p.denoise * 10,
                                   sigmaSpace=p.denoise)
    return gray


def _xdog(gray: np.ndarray, p: LineArtParams) -> np.ndarray:
    g = gray.astype(np.float32) / 255.0
    g1 = cv2.GaussianBlur(g, (0, 0), p.sigma)
    g2 = cv2.GaussianBlur(g, (0, 0), p.sigma * p.k)
    s = (1.0 + p.p) * g1 - p.p * g2
    e = np.where(s >= p.epsilon, 1.0, 1.0 + np.tanh(p.phi * (s - p.epsilon)))
    e = np.clip(e, 0.0, 1.0)
    # e: 1=白地, 0=線 → 線マスクへ
    return (e < 0.5).astype(np.uint8) * 255


def _adaptive(gray: np.ndarray, p: LineArtParams) -> np.ndarray:
    bs = max(3, p.block_size | 1)  # 奇数化
    binv = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY_INV, bs, p.c)
    return binv


def _canny(gray: np.ndarray, p: LineArtParams) -> np.ndarray:
    return cv2.Canny(gray, p.canny_lo, p.canny_hi)


def _despeckle(mask255: np.ndarray, min_area: int) -> np.ndarray:
    if min_area <= 0:
        return mask255
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask255, connectivity=8)
    keep = np.zeros(n, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def extract_lines(bgr: np.ndarray, p: LineArtParams):
    """returns (line_mask: bool HxW, line_alpha: float32 HxW 0..1)"""
    gray = _preprocess(bgr, p)

    if p.mode == "xdog":
        mask = _xdog(gray, p)
    elif p.mode == "canny":
        mask = _canny(gray, p)
    else:
        mask = _adaptive(gray, p)

    mask = _despeckle(mask, p.despeckle)

    if p.thickness > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                      (p.thickness * 2 + 1, p.thickness * 2 + 1))
        mask = cv2.dilate(mask, k)

    # ソフトなアルファ(1pxのアンチエイリアス)
    alpha = cv2.GaussianBlur(mask.astype(np.float32) / 255.0, (3, 3), 0)
    return mask > 127, np.clip(alpha, 0.0, 1.0)
