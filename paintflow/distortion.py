"""
distortion.py — 「水を垂らしたような」ひずみステージ

仕組み:
  1. fBm(value noise) で有機的なノイズ場を作る
  2. ランダムなX位置から下方向に減衰する「雫ストリーク」を生成
     (中心線はノイズで横に揺れる)
  3. dy = ストリーク強度 × strength × melt (下方向に引き伸ばす)
     dx = ノイズ × wobble × melt          (横揺れ)
  4. cv2.remap でピクセルを再サンプリング

melt (0..1) をタイムラインで動かすと「乾いた絵に水が垂れて滲んでいく」
アニメーションになる。seed 固定で完全再現可能。

get_displacement() は変位フィールド(dx, dy)を返すので、
UE5のpost-process materialでflow mapとして同じ歪みを再現できる。
"""
from __future__ import annotations

import cv2
import numpy as np

from .params import DripParams

_BORDER = {
    "reflect": cv2.BORDER_REFLECT101,
    "replicate": cv2.BORDER_REPLICATE,
    "constant": cv2.BORDER_CONSTANT,
}


def fbm(h: int, w: int, scale: float, octaves: int = 4,
        seed: int = 0) -> np.ndarray:
    """value-noise fBm。0..1 float32。外部ライブラリ不要"""
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    amp, total, freq = 1.0, 0.0, max(scale, 1e-4)
    for _ in range(octaves):
        gh = max(2, int(h * freq))
        gw = max(2, int(w * freq))
        grid = rng.random((gh, gw), dtype=np.float32)
        acc += amp * cv2.resize(grid, (w, h), interpolation=cv2.INTER_CUBIC)
        total += amp
        amp *= 0.5
        freq *= 2.0
    out = acc / total
    return np.clip(out, 0.0, 1.0)


def _drip_streaks(h: int, w: int, p: DripParams) -> np.ndarray:
    """雫の強度マップ(0..1)。各雫は下に向かって立ち上がり→減衰する帯"""
    rng = np.random.default_rng(p.seed)
    n_drips = max(1, int(round(w / 100.0 * p.drip_density)))
    canvas = np.zeros((h, w), np.float32)
    ys = np.arange(h, dtype=np.float32)
    xs = np.arange(w, dtype=np.float32)[None, :]

    # 雫中心線の横揺れ用1Dノイズ
    sway_noise = fbm(h, 8, scale=0.01, octaves=3, seed=p.seed + 101)[:, 0]

    for i in range(n_drips):
        x0 = rng.uniform(0, w)
        y0 = rng.uniform(-0.1 * h, 0.55 * h)
        length = h * p.drip_length * rng.uniform(0.5, 1.4)
        sig = p.drip_width * rng.uniform(0.6, 1.6)
        gain = rng.uniform(0.6, 1.0)

        # 縦方向プロファイル: 立ち上がり → テール減衰
        t = ys - y0
        rise = np.clip(t / max(length, 1.0), 0.0, 1.0)
        tail = np.clip(1.0 - (t - length) / max(0.45 * length, 1.0), 0.0, 1.0)
        profile = np.where(t < 0, 0.0, np.where(t <= length, rise, tail))

        # 中心線を揺らす
        centers = x0 + (sway_noise - 0.5) * 2.0 * sig * 2.5 * rng.uniform(0.5, 1.5)
        gauss = np.exp(-((xs - centers[:, None]) ** 2) / (2.0 * sig * sig))

        canvas += gain * profile[:, None] * gauss

    canvas = np.clip(canvas, 0.0, 1.0)
    return cv2.GaussianBlur(canvas, (0, 0), 2.0)


def get_displacement(h: int, w: int, p: DripParams):
    """returns (dx, dy) float32 HxW [px]。melt を含む最終変位"""
    streak = _drip_streaks(h, w, p)
    noise = fbm(h, w, scale=p.noise_scale, octaves=4, seed=p.seed + 7)
    signed = (noise - 0.5) * 2.0

    dy = streak * p.strength
    dy += (noise - 0.5) * 2.0 * p.strength * p.ambient_warp  # 全体の湿り
    dx = signed * p.wobble * (0.3 + 0.7 * streak)

    m = float(np.clip(p.melt, 0.0, 1.0))
    return dx * m, dy * m


def apply_drip(img: np.ndarray, p: DripParams):
    """returns (warped, (dx, dy))。imgはBGRでもBGRAでも可"""
    h, w = img.shape[:2]
    dx, dy = get_displacement(h, w, p)

    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    # 下の画素ほど上から拾う → 絵柄が下に垂れて見える
    map_x = gx - dx
    map_y = gy - dy

    border = _BORDER.get(p.border_mode, cv2.BORDER_REFLECT101)
    warped = cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderMode=border)
    return warped, (dx, dy)


def encode_flow_map(dx: np.ndarray, dy: np.ndarray,
                    max_px: float = 32.0) -> np.ndarray:
    """変位をRGにエンコードしたflow map(uint8 BGR)を返す。
    0.5 = 変位ゼロ。UE5マテリアル側では
      offset = (tex.rg - 0.5) * 2 * MaxPx / ScreenSize
    でUVオフセットに復元する。テクスチャは sRGB オフで読むこと。"""
    nx = np.clip(dx / max_px * 0.5 + 0.5, 0, 1)
    ny = np.clip(dy / max_px * 0.5 + 0.5, 0, 1)
    mag = np.clip(np.sqrt(dx * dx + dy * dy) / max_px, 0, 1)
    rgb = np.stack([mag, ny, nx], axis=-1)  # BGR順: B=mag, G=dy, R=dx
    return (rgb * 255).astype(np.uint8)
