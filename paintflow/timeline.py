"""
timeline.py — タイムライン駆動パラメータ

任意のパラメータ("drip.melt" 等のドットパス)をキーフレームで駆動する。
Houdini の channel / UE5 の Sequencer トラックと同じメンタルモデル。

JSON 例 (timeline.json):
{
  "fps": 24,
  "duration": 2.0,
  "tracks": {
    "drip.melt":   [{"t": 0.0, "v": 0.0},
                    {"t": 1.6, "v": 1.0, "easing": "ease_in_out"},
                    {"t": 2.0, "v": 1.0}],
    "drip.wobble": [{"t": 0.0, "v": 2.0},
                    {"t": 2.0, "v": 8.0, "easing": "ease_in"}]
  }
}
easing はそのキーへ「入っていく」補間に適用される。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List

from .params import PipelineParams

# ---------------------------------------------------------------- easing
EASINGS: Dict[str, Callable[[float], float]] = {}


def register_easing(name: str):
    """自作イージングの登録用デコレータ。
    @register_easing("bounce") def bounce(u): ..."""
    def deco(fn):
        EASINGS[name] = fn
        return fn
    return deco


@register_easing("linear")
def _linear(u: float) -> float:
    return u


@register_easing("hold")
def _hold(u: float) -> float:
    return 0.0 if u < 1.0 else 1.0


@register_easing("ease_in")
def _ease_in(u: float) -> float:
    return u * u * u


@register_easing("ease_out")
def _ease_out(u: float) -> float:
    v = 1.0 - u
    return 1.0 - v * v * v


@register_easing("ease_in_out")
def _ease_in_out(u: float) -> float:
    return u * u * (3.0 - 2.0 * u)  # smoothstep


@register_easing("smootherstep")
def _smootherstep(u: float) -> float:
    return u * u * u * (u * (u * 6.0 - 15.0) + 10.0)


# ---------------------------------------------------------------- keyframe
@dataclass
class Keyframe:
    t: float
    v: float
    easing: str = "linear"


class Track:
    """1パラメータ分のキーフレーム列"""

    def __init__(self, keys: List[Keyframe]):
        self.keys = sorted(keys, key=lambda k: k.t)
        if not self.keys:
            raise ValueError("Track needs at least 1 keyframe")

    def evaluate(self, t: float) -> float:
        ks = self.keys
        if t <= ks[0].t:
            return ks[0].v
        if t >= ks[-1].t:
            return ks[-1].v
        for a, b in zip(ks, ks[1:]):
            if a.t <= t <= b.t:
                span = max(b.t - a.t, 1e-9)
                u = (t - a.t) / span
                u = EASINGS.get(b.easing, _linear)(u)
                return a.v + (b.v - a.v) * u
        return ks[-1].v


class Timeline:
    """複数トラックの束。apply() で PipelineParams に書き込む"""

    def __init__(self, tracks: Dict[str, Track] | None = None,
                 fps: float = 24.0, duration: float = 2.0):
        self.tracks: Dict[str, Track] = tracks or {}
        self.fps = fps
        self.duration = duration

    # -------- 構築系
    def add(self, path: str, keys: List[tuple]) -> "Timeline":
        """tl.add("drip.melt", [(0, 0), (1.5, 1, "ease_in_out")])"""
        kfs = [Keyframe(*k) if not isinstance(k, Keyframe) else k for k in keys]
        self.tracks[path] = Track(kfs)
        return self

    @classmethod
    def from_json(cls, path: str) -> "Timeline":
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        tl = cls(fps=d.get("fps", 24.0), duration=d.get("duration", 2.0))
        for p, keys in d.get("tracks", {}).items():
            tl.tracks[p] = Track([
                Keyframe(k["t"], k["v"], k.get("easing", "linear"))
                for k in keys
            ])
        return tl

    # -------- 評価系
    def evaluate(self, t: float) -> Dict[str, float]:
        return {p: tr.evaluate(t) for p, tr in self.tracks.items()}

    def apply(self, params: PipelineParams, t: float) -> PipelineParams:
        """paramsのコピーに t 時点の値を書き込んで返す(元は破壊しない)"""
        p = params.clone()
        for path, tr in self.tracks.items():
            p.set_path(path, tr.evaluate(t))
        return p

    @property
    def frame_count(self) -> int:
        return max(1, int(round(self.duration * self.fps)))

    def frame_times(self):
        n = self.frame_count
        for i in range(n):
            yield i, i / self.fps
