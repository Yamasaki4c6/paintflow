"""
panels.py — パラメータパネル群

ParamBinder が「ドットパス ⇔ ウィジェット」を双方向に結ぶ。
ウィジェット操作 → params.set_path() → changed(path) シグナル。
プリセット読込時は refresh() で全ウィジェットに書き戻す。
"""
from __future__ import annotations

from functools import partial
from typing import Callable, Dict, List, Tuple

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox,
                               QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QListWidget, QPushButton,
                               QSlider, QSpinBox, QVBoxLayout, QWidget)

from paintflow.params import PipelineParams


# ================================================================ binder
class ParamBinder(QObject):
    changed = Signal(str)  # dotted path

    def __init__(self, get_params: Callable[[], PipelineParams]):
        super().__init__()
        self._get = get_params
        self._refreshers: Dict[str, Callable[[], None]] = {}

    # ---- 値の書き込み+通知
    def _write(self, path: str, value):
        self._get().set_path(path, value)
        self.changed.emit(path)

    def refresh(self):
        for fn in self._refreshers.values():
            fn()

    # ---- スライダー(int/float 両対応)
    def slider(self, path: str, mn: float, mx: float,
               step: float = 1.0, decimals: int = 0) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        s = QSlider(Qt.Horizontal)
        scale = 1.0 / step
        s.setRange(int(mn * scale), int(mx * scale))
        if decimals == 0:
            spin = QSpinBox()
            spin.setRange(int(mn), int(mx))
        else:
            spin = QDoubleSpinBox()
            spin.setDecimals(decimals)
            spin.setRange(mn, mx)
            spin.setSingleStep(step)
        spin.setFixedWidth(64)

        def from_slider(v):
            val = v / scale
            spin.blockSignals(True)
            spin.setValue(val)
            spin.blockSignals(False)
            self._write(path, val)

        def from_spin(v):
            s.blockSignals(True)
            s.setValue(int(round(v * scale)))
            s.blockSignals(False)
            self._write(path, v)

        s.valueChanged.connect(from_slider)
        spin.valueChanged.connect(from_spin)
        lay.addWidget(s, 1)
        lay.addWidget(spin)

        def refresh():
            v = float(self._get().get_path(path))
            s.blockSignals(True)
            spin.blockSignals(True)
            s.setValue(int(round(v * scale)))
            spin.setValue(v if decimals else int(v))
            s.blockSignals(False)
            spin.blockSignals(False)

        self._refreshers[path] = refresh
        refresh()
        return row

    # ---- コンボ
    def combo(self, path: str, options: List[Tuple[str, str]]) -> QComboBox:
        c = QComboBox()
        for value, label in options:
            c.addItem(label, value)
        c.currentIndexChanged.connect(
            lambda i: self._write(path, c.itemData(i)))

        def refresh():
            v = self._get().get_path(path)
            c.blockSignals(True)
            c.setCurrentIndex(max(0, c.findData(v)))
            c.blockSignals(False)

        self._refreshers[path] = refresh
        refresh()
        return c

    # ---- チェックボックス
    def check(self, path: str, label: str = "") -> QCheckBox:
        cb = QCheckBox(label)
        cb.toggled.connect(lambda v: self._write(path, bool(v)))

        def refresh():
            cb.blockSignals(True)
            cb.setChecked(bool(self._get().get_path(path)))
            cb.blockSignals(False)

        self._refreshers[path] = refresh
        refresh()
        return cb

    # ---- カラーボタン
    def color(self, path: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(48, 22)

        def paint():
            btn.setStyleSheet(
                f"background:{self._get().get_path(path)};"
                "border:1px solid #666; border-radius:4px;")

        def pick():
            cur = QColor(self._get().get_path(path))
            col = QColorDialog.getColor(cur, btn, "色を選択")
            if col.isValid():
                self._write(path, col.name())
                paint()

        btn.clicked.connect(pick)
        self._refreshers[path] = paint
        paint()
        return btn

    # ---- シードのランダマイズボタン付き行
    def seed_row(self, path: str) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        spin = QSpinBox()
        spin.setRange(0, 99999)
        spin.valueChanged.connect(lambda v: self._write(path, int(v)))
        dice = QPushButton("🎲")
        dice.setFixedWidth(30)

        def roll():
            import random
            spin.setValue(random.randint(0, 9999))

        dice.clicked.connect(roll)
        lay.addWidget(spin, 1)
        lay.addWidget(dice)

        def refresh():
            spin.blockSignals(True)
            spin.setValue(int(self._get().get_path(path)))
            spin.blockSignals(False)

        self._refreshers[path] = refresh
        refresh()
        return row


# ================================================================ palette
class PaletteEditor(QWidget):
    """flatting.palette のスウォッチ編集"""
    changed = Signal()

    def __init__(self, get_params: Callable[[], PipelineParams]):
        super().__init__()
        self._get = get_params
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(3)
        self.refresh()

    def refresh(self):
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        pal = self._get().flatting.palette
        for i, hexcol in enumerate(pal):
            b = QPushButton()
            b.setFixedSize(24, 24)
            b.setStyleSheet(f"background:{hexcol};border:1px solid #666;"
                            "border-radius:4px;")
            b.setToolTip("左クリック: 色変更 / 右クリック: 削除")
            b.clicked.connect(partial(self._edit, i))
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(partial(self._remove, i))
            self._lay.addWidget(b)
        add = QPushButton("+")
        add.setFixedSize(24, 24)
        add.clicked.connect(self._add)
        self._lay.addWidget(add)
        self._lay.addStretch(1)

    def _edit(self, i):
        pal = self._get().flatting.palette
        col = QColorDialog.getColor(QColor(pal[i]), self, "パレット色")
        if col.isValid():
            pal[i] = col.name()
            self.refresh()
            self.changed.emit()

    def _remove(self, i, _pos=None):
        pal = self._get().flatting.palette
        if len(pal) > 1:
            pal.pop(i)
            self.refresh()
            self.changed.emit()

    def _add(self):
        col = QColorDialog.getColor(QColor("#cccccc"), self, "パレット色を追加")
        if col.isValid():
            self._get().flatting.palette.append(col.name())
            self.refresh()
            self.changed.emit()


# ================================================================ panels
def build_param_panel(binder: ParamBinder,
                      get_params: Callable[[], PipelineParams]) -> QWidget:
    """左ドックに入るパラメータパネル一式"""
    root = QWidget()
    v = QVBoxLayout(root)
    v.setSpacing(8)

    # ---- 線画抽出
    g = QGroupBox("線画抽出")
    f = QFormLayout(g)
    f.addRow("方式", binder.combo("lineart.mode", [
        ("adaptive", "adaptive(スキャン/ラフ)"),
        ("xdog", "XDoG(グレー諧調)"),
        ("canny", "Canny(3DCGレンダ)")]))
    f.addRow("ノイズ除去", binder.slider("lineart.denoise", 0, 15))
    f.addRow("窓サイズ", binder.slider("lineart.block_size", 3, 51, 2))
    f.addRow("閾値バイアス", binder.slider("lineart.c", 0, 25, 0.5, 1))
    f.addRow("線の太さ+", binder.slider("lineart.thickness", 0, 6))
    f.addRow("ゴミ除去", binder.slider("lineart.despeckle", 0, 60))
    v.addWidget(g)

    # ---- 自動彩色
    g = QGroupBox("自動彩色")
    f = QFormLayout(g)
    f.addRow("色ソース", binder.combo("flatting.color_source", [
        ("auto", "auto(自動パステル)"),
        ("palette", "palette(指定色)"),
        ("reference", "reference(参照画像)")]))
    pal = PaletteEditor(get_params)
    f.addRow("パレット", pal)
    f.addRow("隙間閉じ", binder.slider("flatting.gap_close", 0, 12))
    f.addRow("微小領域", binder.slider("flatting.min_region", 0, 500, 4))
    f.addRow("シード", binder.seed_row("flatting.seed"))
    v.addWidget(g)

    # ---- 線の合成
    g = QGroupBox("線の合成")
    f = QFormLayout(g)
    f.addRow(binder.check("composite.line_over", "塗りの上に線を重ねる"))
    f.addRow("線の色", binder.color("composite.line_color"))
    f.addRow("不透明度", binder.slider("composite.line_opacity", 0, 1, 0.05, 2))
    f.addRow(binder.check("composite.knockout_bg", "背景を透明化(3DCG合成用)"))
    v.addWidget(g)

    # ---- 水滴ひずみ
    g = QGroupBox("水滴ひずみ")
    f = QFormLayout(g)
    f.addRow("にじみ進行", binder.slider("drip.melt", 0, 1, 0.01, 2))
    f.addRow("垂れ強さ", binder.slider("drip.strength", 0, 80, 0.5, 1))
    f.addRow("雫の密度", binder.slider("drip.drip_density", 0, 8, 0.1, 1))
    f.addRow("雫の長さ", binder.slider("drip.drip_length", 0.05, 1, 0.01, 2))
    f.addRow("雫の太さ", binder.slider("drip.drip_width", 1, 20, 0.5, 1))
    f.addRow("横揺れ", binder.slider("drip.wobble", 0, 25, 0.5, 1))
    f.addRow("湿り歪み", binder.slider("drip.ambient_warp", 0, 0.6, 0.01, 2))
    f.addRow("シード", binder.seed_row("drip.seed"))
    v.addWidget(g)

    v.addStretch(1)
    root._palette_editor = pal  # main_windowから参照
    return root


LAYERS = [("final", "完成"), ("composed", "歪み前"), ("flat", "フラット塗り"),
          ("lines", "線画"), ("labels", "領域分け"), ("input", "入力画像")]


class LayerPanel(QListWidget):
    layer_changed = Signal(str)

    def __init__(self):
        super().__init__()
        for key, label in LAYERS:
            self.addItem(label)
        self.setCurrentRow(0)
        self.currentRowChanged.connect(
            lambda r: self.layer_changed.emit(LAYERS[r][0]))

    def current_layer(self) -> str:
        return LAYERS[self.currentRow()][0]
