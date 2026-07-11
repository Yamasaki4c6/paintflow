"""例1: 静止画1枚をパラメータ調整しながら処理する最小構成"""
import sys
sys.path.insert(0, "..")  # パッケージをインストールしていない場合用

from paintflow import Pipeline, PipelineParams, io_utils

params = PipelineParams()

# --- 線画抽出の調整 ---
params.lineart.mode = "adaptive"   # ラフ/スキャンなら adaptive
params.lineart.block_size = 17
params.lineart.c = 6.0
params.lineart.thickness = 0

# --- 彩色の調整 ---
params.flatting.color_source = "palette"
params.flatting.palette = ["#dcd6c8", "#9db0a2", "#6f7d8c", "#c2a06a", "#54463c"]
params.flatting.gap_close = 4      # 線の途切れが多いラフは大きめに
params.flatting.seed = 3           # 色の割り当てが気に入らなければseedを変える

# --- ひずみの調整 ---
params.drip.melt = 0.8
params.drip.strength = 20.0
params.drip.seed = 11

# --- 3DCG合成用: 背景領域を透明化 + flow map出力 ---
params.composite.knockout_bg = True
params.output.save_flow = True

pipe = Pipeline(params, verbose=True)
ctx = pipe.run_file("../test_input.png", "still_out.png")

# 中間レイヤーにもアクセスできる
print("labels max:", ctx.images["labels"].max(), "regions")
