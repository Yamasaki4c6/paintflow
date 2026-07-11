"""
io_utils.py — 入出力ユーティリティ

重要: Windows + 日本語パス対策
cv2.imread / imwrite は非ASCIIパス(例: C:/Users/いくら/絵/ラフ.png)で
静かに失敗する。np.fromfile + cv2.imdecode / imencode + tofile 経由なら安全。
"""
from __future__ import annotations

import os

import cv2
import numpy as np


def imread(path: str, flags: int = cv2.IMREAD_COLOR) -> np.ndarray:
    """日本語パス対応の imread"""
    buf = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(buf, flags)
    if img is None:
        raise IOError(f"failed to decode image: {path}")
    return img


def imwrite(path: str, img: np.ndarray) -> None:
    """日本語パス対応の imwrite(拡張子から形式推定)"""
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise IOError(f"failed to encode image: {path}")
    buf.tofile(path)


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def to_bgra(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    if img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    return img


def save_gif(frames_bgr: list, path: str, fps: float = 24.0) -> None:
    """PNG連番とは別に、確認用GIFをPillowで書き出す"""
    from PIL import Image
    ims = [Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
           for f in frames_bgr]
    ims[0].save(path, save_all=True, append_images=ims[1:],
                duration=int(1000 / fps), loop=0)
