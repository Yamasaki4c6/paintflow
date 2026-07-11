"""
params.py — 全パラメータの定義(Single Source of Truth)

すべてのステージのパラメータを dataclass として一箇所に集約する。
- Python から直接いじれる
- JSON から上書きできる (from_json / override_from_dict)
- タイムラインから "drip.melt" のようなドットパスで駆動できる

新しいステージを自作する場合は、ここに dataclass を追加して
PipelineParams にぶら下げるだけでタイムライン駆動の対象になる。
"""
from __future__ import annotations

import copy
import dataclasses
import json
from dataclasses import dataclass, field
from typing import Any, List


# ---------------------------------------------------------------- 線画抽出
@dataclass
class LineArtParams:
    # "adaptive": スキャン線画/ラフに強い(推奨デフォルト)
    # "xdog"    : 写真・グレー画像から漫画的な線を作る
    # "canny"   : エッジ検出ベース(3DCGレンダの輪郭抽出などに)
    mode: str = "adaptive"

    # 共通前処理
    denoise: int = 5            # bilateralフィルタ強度 (0で無効)
    invert_input: bool = False  # 黒地に白線の入力なら True

    # adaptive
    block_size: int = 15        # 奇数。局所閾値のウィンドウサイズ
    c: float = 7.0              # 閾値バイアス。大きいほど線が減る

    # xdog
    sigma: float = 0.6
    k: float = 1.6
    p: float = 19.0
    phi: float = 10.0
    epsilon: float = 0.02

    # canny
    canny_lo: int = 60
    canny_hi: int = 160

    # 後処理
    thickness: int = 0          # 線の太らせ(px)。0で無効
    despeckle: int = 6          # この面積(px)未満の孤立ドットを除去


# ---------------------------------------------------------------- 自動彩色
@dataclass
class FlattingParams:
    gap_close: int = 3          # 線の隙間をどれだけ塞いで領域分割するか(px)
    min_region: int = 48        # この面積未満の領域は隣にマージ

    # "palette"  : palette から決定論的に割り当て(シード固定で再現可能)
    # "reference": reference画像(またはカラー入力そのもの)の領域平均色
    # "auto"     : 領域ごとにハッシュからパステル調の色を生成
    color_source: str = "auto"
    palette: List[str] = field(default_factory=lambda: [
        "#e8e3d8", "#a8b8a0", "#7d8a97", "#c9a86c",
        "#8c6f5a", "#5d6b5d", "#d9c8b4", "#4a5568",
    ])
    seed: int = 0

    # autoモードの色域コントロール
    auto_sat: float = 0.35      # 彩度 0..1
    auto_val: float = 0.92      # 明度 0..1

    # 領域ごとの色上書き(GUIのバケツツール用)。
    # 正規化座標 {"x":0..1, "y":0..1, "color":"#rrggbb"} のリスト。
    # 座標が指す領域の色を上書きするので、解像度が変わっても追従する。
    color_overrides: List[dict] = field(default_factory=list)


# ---------------------------------------------------------------- 合成
@dataclass
class CompositeParams:
    line_over: bool = True      # 塗りの上に線を重ねる
    line_color: str = "#2b2624" # 線の色
    line_opacity: float = 1.0
    knockout_bg: bool = False   # 画面端に接する最大領域を透明化(3DCG合成用)


# ---------------------------------------------------------------- 水滴ひずみ
@dataclass
class DripParams:
    melt: float = 1.0           # 0..1 全体の進行度 ★タイムラインで駆動する主対象
    strength: float = 18.0      # 垂れの最大変位(px)
    drip_density: float = 1.6   # 幅100pxあたりの雫の本数
    drip_length: float = 0.35   # 雫の長さ(画像高さ比 0..1)
    drip_width: float = 5.0     # 雫の太さσ(px)
    wobble: float = 5.0         # 横揺れ(px)
    ambient_warp: float = 0.12  # 画面全体の湿った歪み(strength比)
    noise_scale: float = 0.015  # ノイズの粗さ(小=大きなうねり)
    seed: int = 7
    border_mode: str = "reflect"  # "reflect" | "replicate" | "constant"


# ---------------------------------------------------------------- 出力
@dataclass
class OutputParams:
    save_layers: bool = False   # lines/flat を個別PNGでも保存
    save_flow: bool = False     # 変位フィールドをflow map PNGで保存(UE5再現用)
    flow_max_px: float = 32.0   # flow mapエンコード時の最大変位(UE5側と合わせる)


# ---------------------------------------------------------------- 統合
@dataclass
class PipelineParams:
    lineart: LineArtParams = field(default_factory=LineArtParams)
    flatting: FlattingParams = field(default_factory=FlattingParams)
    composite: CompositeParams = field(default_factory=CompositeParams)
    drip: DripParams = field(default_factory=DripParams)
    output: OutputParams = field(default_factory=OutputParams)

    # ------------------------------------------------ utility
    def clone(self) -> "PipelineParams":
        return copy.deepcopy(self)

    def set_path(self, dotted: str, value: Any) -> None:
        """'drip.melt' のようなドットパスで値をセット(タイムライン用)"""
        obj: Any = self
        *heads, tail = dotted.split(".")
        for h in heads:
            obj = getattr(obj, h)
        cur = getattr(obj, tail)
        # 型をなるべく維持する(int パラメータに float が来たら丸める)
        if isinstance(cur, int) and not isinstance(cur, bool):
            value = int(round(value))
        setattr(obj, tail, value)

    def get_path(self, dotted: str) -> Any:
        obj: Any = self
        for h in dotted.split("."):
            obj = getattr(obj, h)
        return obj

    def override_from_dict(self, d: dict) -> None:
        """{"drip": {"strength": 24}, "lineart": {"mode": "xdog"}} 形式で上書き"""
        for group, sub in d.items():
            target = getattr(self, group)
            for k, v in sub.items():
                if not hasattr(target, k):
                    raise KeyError(f"unknown param: {group}.{k}")
                setattr(target, k, v)

    @classmethod
    def from_json(cls, path: str) -> "PipelineParams":
        p = cls()
        with open(path, "r", encoding="utf-8") as f:
            p.override_from_dict(json.load(f))
        return p

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def hex_to_bgr(hexstr: str) -> tuple:
    h = hexstr.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (b, g, r)
