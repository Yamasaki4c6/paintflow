"""
render_worker.py — バックグラウンドレンダラ(ステージ単位キャッシュ)

パラメータ変更のたびに全パイプラインを回すと重いので、
各ステージのパラメータのJSONをキーにキャッシュする:

  lineart変更  → 全再計算
  flatting変更 → flatting以降を再計算
  drip変更     → dripだけ再計算(meltスライダーはこれで軽快に動く)

render_stages() は純粋関数に近い形なので、GUIスレッドなしでも
テスト・エクスポートに使い回せる。
"""
from __future__ import annotations

import dataclasses
import json
import time
from typing import Dict, Optional

import numpy as np
from PySide6.QtCore import QMutex, QThread, QWaitCondition, Signal

from paintflow import distortion, flatting, lineart
from paintflow.params import PipelineParams, hex_to_bgr
from paintflow.pipeline import Context, stage_composite


def _key(obj) -> str:
    return json.dumps(dataclasses.asdict(obj), sort_keys=True)


class StageCache:
    """入力トークン+ステージparamsで管理する軽量キャッシュ"""

    def __init__(self):
        self.clear()

    def clear(self):
        self.k_line = self.k_flat = self.k_comp = None
        self.line_mask = self.line_alpha = None
        self.flat = self.labels = None
        self.composed = None


def render_stages(cache: StageCache, img_token: str, input_bgr: np.ndarray,
                  params: PipelineParams,
                  reference: Optional[np.ndarray] = None) -> Dict[str, np.ndarray]:
    """キャッシュを使ってパイプラインを実行し、全レイヤーを返す"""
    k_line = img_token + "|" + _key(params.lineart)
    if cache.k_line != k_line:
        cache.line_mask, cache.line_alpha = lineart.extract_lines(
            input_bgr, params.lineart)
        cache.k_line = k_line
        cache.k_flat = cache.k_comp = None

    k_flat = k_line + "|" + _key(params.flatting)
    if cache.k_flat != k_flat:
        cache.flat, cache.labels = flatting.flatten(
            input_bgr, cache.line_mask, params.flatting, reference=reference)
        cache.k_flat = k_flat
        cache.k_comp = None

    k_comp = k_flat + "|" + _key(params.composite)
    if cache.k_comp != k_comp:
        ctx = Context(params=params)
        ctx.images.update(flat=cache.flat, labels=cache.labels,
                          line_alpha=cache.line_alpha)
        stage_composite(ctx)
        cache.composed = ctx.images["composed"]
        cache.k_comp = k_comp

    final, (dx, dy) = distortion.apply_drip(cache.composed, params.drip)

    return {
        "input": input_bgr,
        "line_mask": cache.line_mask,
        "line_alpha": cache.line_alpha,
        "flat": cache.flat,
        "labels": cache.labels,
        "composed": cache.composed,
        "final": final,
        "flow": (dx, dy),
    }


class RenderWorker(QThread):
    """latest-wins型のレンダスレッド。古いリクエストは捨てる"""

    rendered = Signal(int, dict, float)  # (req_id, images, elapsed_ms)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        self._pending = None
        self._quit = False
        self.cache = StageCache()

    def submit(self, req_id: int, img_token: str, input_bgr: np.ndarray,
               params: PipelineParams, reference=None):
        self._mutex.lock()
        self._pending = (req_id, img_token, input_bgr, params, reference)
        self._cond.wakeAll()
        self._mutex.unlock()

    def stop(self):
        self._mutex.lock()
        self._quit = True
        self._cond.wakeAll()
        self._mutex.unlock()
        self.wait(2000)

    def run(self):
        while True:
            self._mutex.lock()
            while self._pending is None and not self._quit:
                self._cond.wait(self._mutex)
            if self._quit:
                self._mutex.unlock()
                return
            req = self._pending
            self._pending = None
            self._mutex.unlock()

            req_id, token, img, params, ref = req
            t0 = time.perf_counter()
            try:
                images = render_stages(self.cache, token, img, params, ref)
            except Exception as e:  # パラメータ端値でも落とさない
                print("render error:", e)
                continue
            self.rendered.emit(req_id, images,
                               (time.perf_counter() - t0) * 1000.0)


def labels_preview(labels: np.ndarray) -> np.ndarray:
    """領域ラベルの可視化(確認用カラーマップ)"""
    import cv2
    n = int(labels.max()) + 1
    rng = np.random.default_rng(1)
    hsv = np.stack([rng.random(n) * 179, np.full(n, 160.0),
                    np.full(n, 220.0)], 1).astype(np.uint8).reshape(-1, 1, 3)
    lut = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR).reshape(-1, 3)
    return lut[labels]


def hexcol(bgr) -> str:
    b, g, r = int(bgr[0]), int(bgr[1]), int(bgr[2])
    return f"#{r:02x}{g:02x}{b:02x}"
