"""
paintflow — 線画抽出 / 自動彩色 / 水滴ひずみ パイプライン

決定論的アルゴリズムのみで構成(生成AI不使用)。
seed固定で同じ結果が常に再現できるので、パイプラインツールとして扱える。

最短の使い方:
    from paintflow import Pipeline, PipelineParams, Timeline

    pipe = Pipeline()
    pipe.run_file("rough.png", "out.png")

タイムライン駆動:
    tl = Timeline(fps=24, duration=2.0)
    tl.add("drip.melt", [(0, 0.0), (1.6, 1.0, "ease_in_out")])
    img = paintflow.io_utils.imread("rough.png")
    pipe.render_sequence(img, tl, "renders/", gif_path="preview.gif")
"""
from . import distortion, flatting, io_utils, lineart
from .params import (CompositeParams, DripParams, FlattingParams,
                     LineArtParams, OutputParams, PipelineParams)
from .pipeline import Context, Pipeline, DEFAULT_STAGES
from .timeline import Keyframe, Timeline, Track, register_easing

__version__ = "0.1.0"
__all__ = [
    "Pipeline", "Context", "DEFAULT_STAGES",
    "PipelineParams", "LineArtParams", "FlattingParams",
    "CompositeParams", "DripParams", "OutputParams",
    "Timeline", "Track", "Keyframe", "register_easing",
    "lineart", "flatting", "distortion", "io_utils",
]
