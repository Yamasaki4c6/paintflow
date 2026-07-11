"""例2: タイムラインで melt を駆動して「水が垂れていく」連番を出す

出力されるPNG連番(ストレートアルファ)はそのまま
UE5のFlipbook / Composure / AfterEffects等に持ち込める。
"""
import sys
sys.path.insert(0, "..")

from paintflow import Pipeline, PipelineParams, Timeline, io_utils

params = PipelineParams()
params.flatting.color_source = "auto"
params.flatting.seed = 5
params.drip.strength = 22.0
params.drip.seed = 7

# 2秒 @ 24fps = 48フレーム
tl = Timeline(fps=24, duration=2.0)
tl.add("drip.melt",   [(0.0, 0.0), (1.6, 1.0, "ease_in_out"), (2.0, 1.0)])
tl.add("drip.wobble", [(0.0, 1.0), (2.0, 7.0, "ease_in")])
# ひずみ以外のパラメータも同じ仕組みで動かせる:
# tl.add("composite.line_opacity", [(0.0, 1.0), (2.0, 0.6)])

img = io_utils.imread("../test_input.png")
pipe = Pipeline(params)
paths = pipe.render_sequence(img, tl, "renders", gif_path="renders/preview.gif")
print(f"{len(paths)} frames rendered")
