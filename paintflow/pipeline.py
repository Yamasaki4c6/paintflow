"""
pipeline.py — パイプライン本体

設計方針(VATパイプラインと同じ思想):
  - ステージは「Contextを受け取って読み書きするだけの関数」
  - ctx.images に全中間レイヤーが残る(検証・デバッグ・再利用可能)
  - insert_after / replace / remove でPythonから自由に組み替え可能
  - 標準構成:
      lineart → flatting → composite → drip

Context.images のキー:
  "input"      入力BGR
  "line_mask"  bool 線マスク
  "line_alpha" float32 0..1
  "labels"     int32 領域ラベル(flattingの副産物。選択マスク等に再利用可)
  "flat"       uint8 フラット塗りBGR
  "composed"   歪み前の合成BGRA
  "final"      最終BGRA
  "flow"       (dx, dy) 変位フィールド ※dripステージ後
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from . import distortion, flatting, io_utils, lineart
from .params import PipelineParams, hex_to_bgr
from .timeline import Timeline

StageFn = Callable[["Context"], None]


@dataclass
class Context:
    params: PipelineParams
    t: float = 0.0
    images: Dict[str, np.ndarray] = field(default_factory=dict)
    meta: Dict[str, object] = field(default_factory=dict)
    reference: Optional[np.ndarray] = None  # flattingのreference用


# ---------------------------------------------------------------- 標準ステージ
def stage_lineart(ctx: Context) -> None:
    mask, alpha = lineart.extract_lines(ctx.images["input"], ctx.params.lineart)
    ctx.images["line_mask"] = mask
    ctx.images["line_alpha"] = alpha


def stage_flatting(ctx: Context) -> None:
    flat, labels = flatting.flatten(
        ctx.images["input"], ctx.images["line_mask"],
        ctx.params.flatting, reference=ctx.reference)
    ctx.images["flat"] = flat
    ctx.images["labels"] = labels


def stage_composite(ctx: Context) -> None:
    p = ctx.params.composite
    flat = ctx.images["flat"].astype(np.float32)
    out = flat.copy()

    if p.line_over:
        a = (ctx.images["line_alpha"] * p.line_opacity)[..., None]
        line_col = np.array(hex_to_bgr(p.line_color), np.float32)
        out = out * (1.0 - a) + line_col * a

    bgra = io_utils.to_bgra(np.clip(out, 0, 255).astype(np.uint8))

    if p.knockout_bg:
        labels = ctx.images["labels"]
        border = np.concatenate([labels[0], labels[-1],
                                 labels[:, 0], labels[:, -1]])
        vals, cnts = np.unique(border, return_counts=True)
        bg_label = int(vals[np.argmax(cnts)])
        bgra[..., 3] = np.where(labels == bg_label, 0, 255).astype(np.uint8)
        ctx.meta["bg_label"] = bg_label

    ctx.images["composed"] = bgra


def stage_drip(ctx: Context) -> None:
    warped, (dx, dy) = distortion.apply_drip(
        ctx.images["composed"], ctx.params.drip)
    ctx.images["final"] = warped
    ctx.images["flow"] = (dx, dy)


DEFAULT_STAGES: List[Tuple[str, StageFn]] = [
    ("lineart", stage_lineart),
    ("flatting", stage_flatting),
    ("composite", stage_composite),
    ("drip", stage_drip),
]


# ---------------------------------------------------------------- 本体
class Pipeline:
    def __init__(self, params: PipelineParams | None = None,
                 stages: List[Tuple[str, StageFn]] | None = None,
                 verbose: bool = False):
        self.params = params or PipelineParams()
        self.stages: List[Tuple[str, StageFn]] = list(stages or DEFAULT_STAGES)
        self.verbose = verbose

    # -------- ステージ操作(Python改造の入口)
    def _index(self, name: str) -> int:
        for i, (n, _) in enumerate(self.stages):
            if n == name:
                return i
        raise KeyError(f"stage not found: {name}")

    def insert_after(self, name: str, new_name: str, fn: StageFn) -> "Pipeline":
        self.stages.insert(self._index(name) + 1, (new_name, fn))
        return self

    def insert_before(self, name: str, new_name: str, fn: StageFn) -> "Pipeline":
        self.stages.insert(self._index(name), (new_name, fn))
        return self

    def replace(self, name: str, fn: StageFn) -> "Pipeline":
        self.stages[self._index(name)] = (name, fn)
        return self

    def remove(self, name: str) -> "Pipeline":
        self.stages.pop(self._index(name))
        return self

    # -------- 実行
    def run(self, input_bgr: np.ndarray, t: float = 0.0,
            params: PipelineParams | None = None,
            reference: np.ndarray | None = None) -> Context:
        ctx = Context(params=params or self.params, t=t, reference=reference)
        ctx.images["input"] = input_bgr
        for name, fn in self.stages:
            t0 = time.perf_counter()
            fn(ctx)
            if self.verbose:
                print(f"  [{name}] {(time.perf_counter() - t0) * 1000:6.1f} ms")
        if "final" not in ctx.images:  # dripを外した構成でも成立させる
            ctx.images["final"] = ctx.images.get(
                "composed", io_utils.to_bgra(input_bgr))
        return ctx

    def run_file(self, in_path: str, out_path: str, t: float = 0.0,
                 reference_path: str | None = None) -> Context:
        img = io_utils.imread(in_path)
        ref = io_utils.imread(reference_path) if reference_path else None
        ctx = self.run(img, t=t, reference=ref)
        io_utils.imwrite(out_path, ctx.images["final"])
        self._save_extras(ctx, out_path)
        return ctx

    # -------- 連番レンダリング(タイムライン駆動)
    def render_sequence(self, input_bgr: np.ndarray, timeline: Timeline,
                        out_dir: str, basename: str = "frame",
                        reference: np.ndarray | None = None,
                        gif_path: str | None = None) -> List[str]:
        io_utils.ensure_dir(out_dir)
        paths: List[str] = []
        gif_frames: List[np.ndarray] = []

        for i, t in timeline.frame_times():
            frame_params = timeline.apply(self.params, t)
            ctx = self.run(input_bgr, t=t, params=frame_params,
                           reference=reference)
            path = f"{out_dir}/{basename}_{i:04d}.png"
            io_utils.imwrite(path, ctx.images["final"])
            self._save_extras(ctx, path)
            paths.append(path)
            if self.verbose:
                print(f"frame {i:04d}  t={t:.3f}s")
            if gif_path:
                f = ctx.images["final"]
                gif_frames.append(cv2.cvtColor(f, cv2.COLOR_BGRA2BGR)
                                  if f.shape[2] == 4 else f)

        if gif_path and gif_frames:
            io_utils.save_gif(gif_frames, gif_path, fps=timeline.fps)
        return paths

    # -------- 付随出力
    def _save_extras(self, ctx: Context, main_path: str) -> None:
        stem = main_path.rsplit(".", 1)[0]
        op = ctx.params.output
        if op.save_layers:
            io_utils.imwrite(stem + "_lines.png",
                             (ctx.images["line_alpha"] * 255).astype(np.uint8))
            io_utils.imwrite(stem + "_flat.png", ctx.images["flat"])
        if op.save_flow and "flow" in ctx.images:
            dx, dy = ctx.images["flow"]
            io_utils.imwrite(stem + "_flow.png",
                             distortion.encode_flow_map(dx, dy, op.flow_max_px))
