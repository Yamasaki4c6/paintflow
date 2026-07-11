"""
flatting.py — 自動色塗り(フラッティング)ステージ

生成AIは使わない完全決定論アルゴリズム:
  1. 線マスクを gap_close px 太らせて「壁」を作る(線の途切れ対策)
  2. 壁以外を連結成分ラベリング → 領域分割
  3. 微小領域を隣にマージ
  4. 各領域に色を割り当て(palette / reference / auto)
  5. 壁の下の画素も最近傍領域の色で埋める(distance transform)

戻り値の labels は後段(選択マスク・領域単位のエフェクト等)で再利用できる。
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy import ndimage

from .params import FlattingParams, hex_to_bgr


def _assign_palette(n_labels: int, p: FlattingParams) -> np.ndarray:
    """領域面積順に palette を循環割り当て(seedでシャッフル)"""
    rng = np.random.default_rng(p.seed)
    pal = np.array([hex_to_bgr(c) for c in p.palette], dtype=np.uint8)
    idx = rng.permutation(len(pal))
    lut = np.zeros((n_labels, 3), dtype=np.uint8)
    for i in range(1, n_labels):
        lut[i] = pal[idx[(i - 1) % len(pal)]]
    return lut


def _assign_auto(n_labels: int, p: FlattingParams) -> np.ndarray:
    """ラベルIDのハッシュから決定論的にパステル色を生成"""
    rng = np.random.default_rng(p.seed)
    hues = rng.random(n_labels) * 179.0
    hsv = np.stack([
        hues,
        np.full(n_labels, p.auto_sat * 255.0),
        np.full(n_labels, p.auto_val * 255.0),
    ], axis=1).astype(np.uint8).reshape(-1, 1, 3)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR).reshape(-1, 3)


def _assign_reference(labels: np.ndarray, n_labels: int,
                      ref_bgr: np.ndarray) -> np.ndarray:
    """領域ごとの reference 画像平均色。ラフ塗り→クリーンなフラットに便利"""
    lut = np.zeros((n_labels, 3), dtype=np.uint8)
    flat_labels = labels.ravel()
    for c in range(3):
        sums = np.bincount(flat_labels, weights=ref_bgr[..., c].ravel(),
                           minlength=n_labels)
        cnts = np.bincount(flat_labels, minlength=n_labels).clip(min=1)
        lut[:, c] = np.clip(sums / cnts, 0, 255).astype(np.uint8)
    return lut


def _merge_small(labels: np.ndarray, min_area: int) -> np.ndarray:
    """微小領域を 0(未割り当て)に落とし、後段の最近傍埋めで隣に吸収させる"""
    if min_area <= 0:
        return labels
    areas = np.bincount(labels.ravel())
    small = areas < min_area
    small[0] = False
    out = labels.copy()
    out[small[labels]] = 0
    return out


def flatten(bgr: np.ndarray, line_mask: np.ndarray, p: FlattingParams,
            reference: np.ndarray | None = None):
    """returns (flat_bgr: uint8 HxWx3, labels: int32 HxW)"""
    h, w = line_mask.shape

    # 1. 壁を作る
    wall = line_mask.astype(np.uint8) * 255
    if p.gap_close > 0:
        k = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (p.gap_close * 2 + 1, p.gap_close * 2 + 1))
        wall = cv2.dilate(wall, k)

    # 2. 領域分割
    free = (wall == 0).astype(np.uint8)
    n_labels, labels = cv2.connectedComponents(free, connectivity=4)
    labels = labels.astype(np.int32)

    # 3. 微小領域除去
    labels = _merge_small(labels, p.min_region)

    # 4. 壁と微小領域を最近傍ラベルで埋める(領域を線の下まで伸ばす)
    empty = labels == 0
    if empty.any():
        _, (iy, ix) = ndimage.distance_transform_edt(empty, return_indices=True)
        labels = labels[iy, ix]

    # 5. 色割り当て
    n = int(labels.max()) + 1
    if p.color_source == "reference":
        ref = reference if reference is not None else bgr
        lut = _assign_reference(labels, n, ref)
    elif p.color_source == "palette":
        lut = _assign_palette(n, p)
    else:
        lut = _assign_auto(n, p)

    # 6. 色上書き(正規化座標が指す領域のLUTを差し替え。解像度非依存)
    for ov in p.color_overrides:
        xi = int(round(float(ov["x"]) * (w - 1)))
        yi = int(round(float(ov["y"]) * (h - 1)))
        xi = min(max(xi, 0), w - 1)
        yi = min(max(yi, 0), h - 1)
        lut[labels[yi, xi]] = hex_to_bgr(ov["color"])

    flat = lut[labels]
    return flat, labels
