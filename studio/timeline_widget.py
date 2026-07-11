"""
timeline_widget.py — タイムライン(キーフレーム編集+再生)

操作:
  ルーラー/空きクリック・ドラッグ  再生ヘッド移動(スクラブ)
  ◆ドラッグ                       キーの時刻移動
  ◆クリック                       選択 → 下の値/イージング欄で編集
  [+キー]                          再生ヘッド位置に現在のスライダー値でキー追加
  ▶                                プレビュー再生(ループ)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QHBoxLayout,
                               QLabel, QPushButton, QVBoxLayout, QWidget)

from paintflow.params import PipelineParams
from paintflow.timeline import EASINGS, Timeline

ANIMATABLE = [
    ("drip.melt", "にじみ進行"),
    ("drip.strength", "垂れ強さ"),
    ("drip.wobble", "横揺れ"),
    ("drip.drip_density", "雫の密度"),
    ("drip.ambient_warp", "湿り歪み"),
    ("composite.line_opacity", "線の不透明度"),
]
_LABELS = dict(ANIMATABLE)


@dataclass
class Key:
    t: float
    v: float
    easing: str = "ease_in_out"


class TrackArea(QWidget):
    """トラック描画+マウス操作"""
    time_changed = Signal(float)
    keys_changed = Signal()
    key_selected = Signal(object)  # (path, index) or None

    GUTTER = 130
    ROW_H = 26
    RULER_H = 20

    def __init__(self, owner: "TimelinePanel"):
        super().__init__()
        self.o = owner
        self._drag_key: Optional[Tuple[str, int]] = None
        self._scrub = False
        self.setMinimumHeight(self.RULER_H + self.ROW_H)
        self.setMouseTracking(True)

    # ------------------------------------------------ coords
    def _t2x(self, t: float) -> float:
        w = self.width() - self.GUTTER - 10
        return self.GUTTER + t / max(self.o.duration, 1e-6) * w

    def _x2t(self, x: float) -> float:
        w = self.width() - self.GUTTER - 10
        t = (x - self.GUTTER) / max(w, 1) * self.o.duration
        return min(max(t, 0.0), self.o.duration)

    def _row_y(self, row: int) -> float:
        return self.RULER_H + row * self.ROW_H + self.ROW_H / 2

    def sizeHintRows(self):
        rows = max(1, len(self.o.tracks))
        self.setMinimumHeight(self.RULER_H + rows * self.ROW_H + 4)

    # ------------------------------------------------ paint
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#232326"))

        # ルーラー
        p.setPen(QColor("#55555e"))
        n_ticks = int(self.o.duration * 4) + 1
        for i in range(n_ticks):
            t = i / 4
            x = self._t2x(t)
            major = i % 4 == 0
            p.drawLine(x, self.RULER_H - (10 if major else 5), x, self.RULER_H)
            if major:
                p.setPen(QColor("#9a9aa2"))
                p.drawText(QRectF(x - 20, 0, 40, 12), Qt.AlignCenter, f"{t:.0f}s")
                p.setPen(QColor("#55555e"))

        # トラック行
        paths = list(self.o.tracks.keys()) or [None]
        for row, path in enumerate(paths):
            y = self._row_y(row)
            p.fillRect(QRectF(0, y - self.ROW_H / 2, self.width(), self.ROW_H),
                       QColor("#28282c" if row % 2 else "#2c2c31"))
            p.setPen(QColor("#c8c8d0"))
            name = _LABELS.get(path, path) if path else "(トラックなし)"
            p.drawText(QRectF(8, y - 10, self.GUTTER - 12, 20),
                       Qt.AlignVCenter, name)
            if path is None:
                continue
            p.setPen(QPen(QColor("#4a4a52"), 1))
            p.drawLine(self.GUTTER, y, self.width() - 10, y)
            for i, k in enumerate(self.o.tracks[path]):
                x = self._t2x(k.t)
                sel = self.o.selected == (path, i)
                self._diamond(p, x, y, sel)

        # 再生ヘッド
        x = self._t2x(self.o.t)
        p.setPen(QPen(QColor("#4aa3ff"), 2))
        p.drawLine(x, 0, x, self.height())
        p.setBrush(QColor("#4aa3ff"))
        p.drawPolygon(QPolygonF([QPointF(x - 5, 0), QPointF(x + 5, 0),
                                 QPointF(x, 8)]))

    @staticmethod
    def _diamond(p: QPainter, x: float, y: float, selected: bool):
        r = 6
        poly = QPolygonF([QPointF(x, y - r), QPointF(x + r, y),
                          QPointF(x, y + r), QPointF(x - r, y)])
        p.setPen(QPen(QColor("#101014"), 1))
        p.setBrush(QColor("#ffd166") if selected else QColor("#c3c3cc"))
        p.drawPolygon(poly)

    # ------------------------------------------------ mouse
    def _hit_key(self, pos) -> Optional[Tuple[str, int]]:
        for row, (path, keys) in enumerate(self.o.tracks.items()):
            y = self._row_y(row)
            if abs(pos.y() - y) > self.ROW_H / 2:
                continue
            for i, k in enumerate(keys):
                if abs(pos.x() - self._t2x(k.t)) <= 7:
                    return (path, i)
        return None

    def mousePressEvent(self, ev):
        hit = self._hit_key(ev.position())
        if hit and ev.button() == Qt.LeftButton:
            self.o.selected = hit
            self._drag_key = hit
            self.key_selected.emit(hit)
        else:
            self.o.selected = None
            self.key_selected.emit(None)
            self._scrub = True
            self.o.set_time(self._x2t(ev.position().x()))
        self.update()

    def mouseMoveEvent(self, ev):
        if self._drag_key:
            path, i = self._drag_key
            self.o.tracks[path][i].t = round(self._x2t(ev.position().x()), 3)
            self.keys_changed.emit()
            self.update()
        elif self._scrub:
            self.o.set_time(self._x2t(ev.position().x()))

    def mouseReleaseEvent(self, _):
        if self._drag_key:
            path, i = self._drag_key
            key = self.o.tracks[path][i]
            self.o.tracks[path].sort(key=lambda k: k.t)
            self.o.selected = (path, self.o.tracks[path].index(key))
            self.key_selected.emit(self.o.selected)
            self.keys_changed.emit()
        self._drag_key = None
        self._scrub = False
        self.update()


class TimelinePanel(QWidget):
    """コントロール+TrackArea+選択キー編集"""
    time_changed = Signal(float)
    keys_changed = Signal()

    def __init__(self, get_params: Callable[[], PipelineParams]):
        super().__init__()
        self._get_params = get_params
        self.tracks: Dict[str, List[Key]] = {}
        self.duration = 2.0
        self.fps = 12
        self.t = 0.0
        self.selected: Optional[Tuple[str, int]] = None

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 4)

        # ---- 上段コントロール
        top = QHBoxLayout()
        self.play_btn = QPushButton("▶ 再生")
        self.play_btn.setCheckable(True)
        self.play_btn.toggled.connect(self._toggle_play)
        top.addWidget(self.play_btn)

        top.addWidget(QLabel("長さ"))
        self.dur_spin = QDoubleSpinBox()
        self.dur_spin.setRange(0.5, 10.0)
        self.dur_spin.setValue(self.duration)
        self.dur_spin.setSuffix(" s")
        self.dur_spin.setSingleStep(0.5)
        self.dur_spin.valueChanged.connect(self._set_duration)
        top.addWidget(self.dur_spin)

        top.addWidget(QLabel("fps"))
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(4, 30)
        self.fps_spin.setDecimals(0)
        self.fps_spin.setValue(self.fps)
        self.fps_spin.valueChanged.connect(lambda v: setattr(self, "fps", int(v)))
        top.addWidget(self.fps_spin)

        top.addSpacing(16)
        self.track_combo = QComboBox()
        for path, label in ANIMATABLE:
            self.track_combo.addItem(label, path)
        top.addWidget(self.track_combo)
        add_track = QPushButton("トラック追加")
        add_track.clicked.connect(self._add_track)
        top.addWidget(add_track)

        self.addkey_btn = QPushButton("◆ +キー")
        self.addkey_btn.setToolTip("再生ヘッド位置に現在のパラメータ値でキーを打つ")
        self.addkey_btn.clicked.connect(self._add_key)
        top.addWidget(self.addkey_btn)

        top.addStretch(1)
        self.time_label = QLabel("t = 0.00s")
        top.addWidget(self.time_label)
        v.addLayout(top)

        # ---- トラックエリア
        self.area = TrackArea(self)
        self.area.keys_changed.connect(self.keys_changed)
        self.area.key_selected.connect(self._on_select)
        v.addWidget(self.area)

        # ---- 選択キー編集
        bot = QHBoxLayout()
        bot.addWidget(QLabel("選択キー:"))
        self.val_spin = QDoubleSpinBox()
        self.val_spin.setRange(-999, 999)
        self.val_spin.setDecimals(3)
        self.val_spin.valueChanged.connect(self._edit_value)
        bot.addWidget(QLabel("値"))
        bot.addWidget(self.val_spin)
        self.ease_combo = QComboBox()
        self.ease_combo.addItems(list(EASINGS.keys()))
        self.ease_combo.currentTextChanged.connect(self._edit_easing)
        bot.addWidget(QLabel("イージング"))
        bot.addWidget(self.ease_combo)
        self.del_btn = QPushButton("キー削除")
        self.del_btn.clicked.connect(self._delete_key)
        bot.addWidget(self.del_btn)
        self.deltrack_btn = QPushButton("トラック削除")
        self.deltrack_btn.clicked.connect(self._delete_track)
        bot.addWidget(self.deltrack_btn)
        bot.addStretch(1)
        v.addLayout(bot)
        self._enable_editor(False)

        # ---- 再生タイマー
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------ playback
    def _toggle_play(self, on: bool):
        if on:
            self.play_btn.setText("■ 停止")
            self._timer.start(int(1000 / self.fps))
        else:
            self.play_btn.setText("▶ 再生")
            self._timer.stop()

    def _tick(self):
        t = self.t + 1.0 / self.fps
        if t > self.duration:
            t = 0.0
        self.set_time(t)

    def set_time(self, t: float):
        self.t = min(max(t, 0.0), self.duration)
        self.time_label.setText(f"t = {self.t:.2f}s")
        self.area.update()
        self.time_changed.emit(self.t)

    def _set_duration(self, v: float):
        self.duration = v
        self.set_time(min(self.t, v))
        self.area.update()

    # ------------------------------------------------ track / key ops
    def _add_track(self):
        path = self.track_combo.currentData()
        if path not in self.tracks:
            cur = float(self._get_params().get_path(path))
            self.tracks[path] = [Key(0.0, cur, "linear")]
            self.area.sizeHintRows()
            self.area.update()
            self.keys_changed.emit()

    def _add_key(self):
        path = self.track_combo.currentData()
        if path not in self.tracks:
            self._add_track()
        keys = self.tracks[path]
        cur = float(self._get_params().get_path(path))
        eps = 0.5 / self.fps
        for k in keys:
            if abs(k.t - self.t) < eps:
                k.v = cur
                break
        else:
            keys.append(Key(round(self.t, 3), cur))
            keys.sort(key=lambda k: k.t)
        self.area.update()
        self.keys_changed.emit()

    def _delete_key(self):
        if not self.selected:
            return
        path, i = self.selected
        self.tracks[path].pop(i)
        if not self.tracks[path]:
            del self.tracks[path]
            self.area.sizeHintRows()
        self.selected = None
        self._enable_editor(False)
        self.area.update()
        self.keys_changed.emit()

    def _delete_track(self):
        path = (self.selected[0] if self.selected
                else self.track_combo.currentData())
        if path in self.tracks:
            del self.tracks[path]
            self.selected = None
            self._enable_editor(False)
            self.area.sizeHintRows()
            self.area.update()
            self.keys_changed.emit()

    def _on_select(self, sel):
        self.selected = sel
        self._enable_editor(sel is not None)
        if sel:
            path, i = sel
            k = self.tracks[path][i]
            self.val_spin.blockSignals(True)
            self.val_spin.setValue(k.v)
            self.val_spin.blockSignals(False)
            self.ease_combo.blockSignals(True)
            self.ease_combo.setCurrentText(k.easing)
            self.ease_combo.blockSignals(False)

    def _enable_editor(self, on: bool):
        for w in (self.val_spin, self.ease_combo, self.del_btn):
            w.setEnabled(on)

    def _edit_value(self, v):
        if self.selected:
            path, i = self.selected
            self.tracks[path][i].v = float(v)
            self.keys_changed.emit()
            self.area.update()

    def _edit_easing(self, name):
        if self.selected:
            path, i = self.selected
            self.tracks[path][i].easing = name
            self.keys_changed.emit()

    # ------------------------------------------------ engine bridge
    def has_tracks(self) -> bool:
        return any(self.tracks.values())

    def build_engine_timeline(self) -> Timeline:
        tl = Timeline(fps=self.fps, duration=self.duration)
        for path, keys in self.tracks.items():
            tl.add(path, [(k.t, k.v, k.easing) for k in keys])
        return tl

    # ------------------------------------------------ preset io
    def to_dict(self) -> dict:
        return {"fps": self.fps, "duration": self.duration,
                "tracks": {p: [{"t": k.t, "v": k.v, "easing": k.easing}
                               for k in ks] for p, ks in self.tracks.items()}}

    def load_dict(self, d: dict):
        self.fps = int(d.get("fps", 12))
        self.duration = float(d.get("duration", 2.0))
        self.fps_spin.setValue(self.fps)
        self.dur_spin.setValue(self.duration)
        self.tracks = {p: [Key(k["t"], k["v"], k.get("easing", "linear"))
                           for k in ks]
                       for p, ks in d.get("tracks", {}).items()}
        self.selected = None
        self._enable_editor(False)
        self.area.sizeHintRows()
        self.area.update()
        self.set_time(0.0)
