"""例3: パイプラインの改造 — 自作ステージと自作イージングの追加

ステージは「Contextを読み書きする関数」なので、
ポスタリゼーション/ハーフトーン/色収差/3DCG背景との合成など
何でも差し込める。ここではポスタリゼーションを drip の前に挿入する。
"""
import sys
sys.path.insert(0, "..")

import numpy as np
from paintflow import (Context, Pipeline, PipelineParams, Timeline,
                       io_utils, register_easing)

# ---------------------------------------------------------------- 自作ステージ
def stage_posterize(ctx: Context) -> None:
    """composed(BGRA)の色数を落とす。levelsはmetaから取る例"""
    levels = int(ctx.meta.get("posterize_levels", 5))
    img = ctx.images["composed"].astype(np.float32)
    img[..., :3] = np.round(img[..., :3] / 255 * (levels - 1)) \
        / (levels - 1) * 255
    ctx.images["composed"] = img.astype(np.uint8)


# ---------------------------------------------------------------- 自作イージング
@register_easing("overshoot")
def overshoot(u: float) -> float:
    """行き過ぎて戻る。timeline.jsonからも "overshoot" で使える"""
    c = 1.70158
    u -= 1.0
    return u * u * ((c + 1) * u + c) + 1.0


# ---------------------------------------------------------------- 組み立て
params = PipelineParams()
pipe = Pipeline(params)
pipe.insert_after("composite", "posterize", stage_posterize)

# 3DCG背景と合成するステージの雛形(final出力後に差し込む例):
def stage_comp_over_bg(ctx: Context) -> None:
    bg = ctx.meta.get("bg_image")  # 事前に ctx.meta へ渡しておく
    if bg is None:
        return
    fg = ctx.images["final"].astype(np.float32) / 255
    a = fg[..., 3:4]
    out = fg[..., :3] * a + (bg.astype(np.float32) / 255) * (1 - a)
    ctx.images["final"] = (np.dstack([out, np.ones_like(a)]) * 255).astype(np.uint8)

# pipe.insert_after("drip", "comp_bg", stage_comp_over_bg)

tl = Timeline(fps=12, duration=1.0)
tl.add("drip.melt", [(0.0, 0.0), (1.0, 1.0, "overshoot")])

img = io_utils.imread("../test_input.png")
pipe.render_sequence(img, tl, "renders_custom",
                     gif_path="renders_custom/preview.gif")
print("done")
