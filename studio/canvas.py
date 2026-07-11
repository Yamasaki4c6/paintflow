"""
canvas.py — キャンバス(ズーム/パン/バケツクリック)

操作:
  ホイール          ズーム(カーソル基準)
  中ドラッグ/Space+ドラッグ  パン
  左クリック        clicked(x, y) 正規化座標を発行 → バケツ塗り
  右クリック        right_clicked(x, y) → その領域の上書き解除
  ダブルクリック    全体表示にフィット
"""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


def np_to_qimage(img: np.ndarray) -> QImage:
    """BGR/BGRA/GRAY → QImage(コピーして所有権を持たせる)"""
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    elif img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    img = np.ascontiguousarray(img)
    h, w = img.shape[:2]
    qimg = QImage(img.data, w, h, w * 4, QImage.Format_ARGB32)
    return qimg.copy()


class Canvas(QWidget):
    clicked = Signal(float, float)        # 正規化座標 (0..1)
    right_clicked = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pix: QPixmap | None = None
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self._panning = False
        self._space = False
        self._last = QPoint()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._checker = self._make_checker()

    # ---------------------------------------------------------- public
    def set_image(self, img: np.ndarray):
        first = self._pix is None
        self._pix = QPixmap.fromImage(np_to_qimage(img))
        if first:
            self.fit()
        self.update()

    def fit(self):
        if not self._pix:
            return
        pw, ph = self._pix.width(), self._pix.height()
        if pw == 0 or ph == 0:
            return
        s = min(self.width() / pw, self.height() / ph) * 0.95
        self._scale = max(0.02, s)
        self._offset = QPointF((self.width() - pw * s) / 2,
                               (self.height() - ph * s) / 2)
        self.update()

    # ---------------------------------------------------------- helpers
    @staticmethod
    def _make_checker() -> QPixmap:
        pm = QPixmap(16, 16)
        pm.fill(QColor("#3a3a3f"))
        p = QPainter(pm)
        p.fillRect(0, 0, 8, 8, QColor("#46464c"))
        p.fillRect(8, 8, 8, 8, QColor("#46464c"))
        p.end()
        return pm

    def _widget_to_norm(self, pos) -> tuple[float, float] | None:
        if not self._pix:
            return None
        x = (pos.x() - self._offset.x()) / self._scale
        y = (pos.y() - self._offset.y()) / self._scale
        w, h = self._pix.width(), self._pix.height()
        if 0 <= x < w and 0 <= y < h:
            return x / max(w - 1, 1), y / max(h - 1, 1)
        return None

    # ---------------------------------------------------------- events
    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#242428"))
        if not self._pix:
            p.setPen(QColor("#77777f"))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "画像をここにドロップ\nまたは ファイル → 開く")
            return
        p.save()
        p.translate(self._offset)
        p.scale(self._scale, self._scale)
        p.drawTiledPixmap(0, 0, self._pix.width(), self._pix.height(),
                          self._checker)
        p.setRenderHint(QPainter.SmoothPixmapTransform, self._scale < 1.0)
        p.drawPixmap(0, 0, self._pix)
        p.restore()

    def wheelEvent(self, ev):
        if not self._pix:
            return
        factor = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        new = min(20.0, max(0.02, self._scale * factor))
        mouse = ev.position()
        # カーソル位置を不動点にする
        self._offset = mouse - (mouse - self._offset) * (new / self._scale)
        self._scale = new
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MiddleButton or \
           (ev.button() == Qt.LeftButton and self._space):
            self._panning = True
            self._last = ev.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            return
        norm = self._widget_to_norm(ev.position())
        if norm is None:
            return
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(*norm)
        elif ev.button() == Qt.RightButton:
            self.right_clicked.emit(*norm)

    def mouseMoveEvent(self, ev):
        if self._panning:
            d = ev.position().toPoint() - self._last
            self._offset += QPointF(d)
            self._last = ev.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, _):
        self._panning = False
        self.setCursor(Qt.ArrowCursor)

    def mouseDoubleClickEvent(self, _):
        self.fit()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Space:
            self._space = True

    def keyReleaseEvent(self, ev):
        if ev.key() == Qt.Key_Space:
            self._space = False

    def resizeEvent(self, _):
        pass  # 現状維持(fitはユーザー操作で)
