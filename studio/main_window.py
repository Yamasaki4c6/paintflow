"""
main_window.py — Paintflow Studio メインウィンドウ

レイアウト:
  左ドック   パラメータパネル(スクロール)
  中央       キャンバス(ズーム/パン/バケツ塗り)
  右ドック   レイヤー表示切替
  下ドック   タイムライン
"""
from __future__ import annotations

import json
import os

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDockWidget,
                               QFileDialog, QLabel, QMainWindow, QMessageBox,
                               QProgressDialog, QPushButton, QScrollArea,
                               QApplication)

from paintflow import io_utils
from paintflow.params import PipelineParams
from studio.canvas import Canvas
from studio.panels import LayerPanel, ParamBinder, build_param_panel
from studio.render_worker import (RenderWorker, StageCache, labels_preview,
                                  render_stages)
from studio.timeline_widget import TimelinePanel

IMG_FILTER = "画像 (*.png *.jpg *.jpeg *.bmp *.webp);;すべて (*.*)"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Paintflow Studio")
        self.resize(1380, 860)
        self.setAcceptDrops(True)

        # ---- 状態
        self.params = PipelineParams()
        self.full_bgr: np.ndarray | None = None      # フル解像度入力
        self.preview_bgr: np.ndarray | None = None   # プレビュー解像度入力
        self.reference_full: np.ndarray | None = None
        self.reference_preview: np.ndarray | None = None
        self.img_token = "none"
        self.last_images: dict = {}
        self.bucket_color = "#e56a54"
        self._req_id = 0
        self.source_path = ""

        # ---- 中央キャンバス
        self.canvas = Canvas()
        self.canvas.clicked.connect(self.on_bucket)
        self.canvas.right_clicked.connect(self.on_unbucket)
        self.setCentralWidget(self.canvas)

        # ---- 左: パラメータ
        self.binder = ParamBinder(lambda: self.params)
        self.param_panel = build_param_panel(self.binder, lambda: self.params)
        self.param_panel._palette_editor.changed.connect(
            lambda: self.schedule_render())
        scroll = QScrollArea()
        scroll.setWidget(self.param_panel)
        scroll.setWidgetResizable(True)
        dock = QDockWidget("パラメータ", self)
        dock.setWidget(scroll)
        dock.setMinimumWidth(310)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.binder.changed.connect(self._on_param_changed)

        # ---- 右: レイヤー
        self.layer_panel = LayerPanel()
        self.layer_panel.layer_changed.connect(lambda _: self.refresh_canvas())
        dock = QDockWidget("レイヤー表示", self)
        dock.setWidget(self.layer_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        # ---- 下: タイムライン
        self.timeline = TimelinePanel(lambda: self.params)
        self.timeline.time_changed.connect(
            lambda _: self.schedule_render(immediate=True))
        self.timeline.keys_changed.connect(
            lambda: self.schedule_render(immediate=True))
        dock = QDockWidget("タイムライン", self)
        dock.setWidget(self.timeline)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

        # ---- レンダワーカー + デバウンス
        self.worker = RenderWorker()
        self.worker.rendered.connect(self.on_rendered)
        self.worker.start()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self.request_render)

        self._build_toolbar()
        self._build_menu()
        self.status = self.statusBar()
        self.status.showMessage("画像を開いてください(ドラッグ&ドロップ可)")

    # ================================================== toolbar / menu
    def _build_toolbar(self):
        tb = self.addToolBar("メイン")
        tb.setMovable(False)

        a = QAction("📂 開く", self)
        a.triggered.connect(self.open_image)
        tb.addAction(a)

        a = QAction("⛶ フィット", self)
        a.triggered.connect(self.canvas.fit)
        tb.addAction(a)

        tb.addSeparator()
        tb.addWidget(QLabel(" プレビュー解像度 "))
        self.res_combo = QComboBox()
        for v in (512, 800, 1200, 0):
            self.res_combo.addItem("フル" if v == 0 else f"{v}px", v)
        self.res_combo.setCurrentIndex(1)
        self.res_combo.currentIndexChanged.connect(self._rebuild_preview)
        tb.addWidget(self.res_combo)

        tb.addSeparator()
        tb.addWidget(QLabel(" バケツ色 "))
        self.bucket_btn = QPushButton()
        self.bucket_btn.setFixedSize(40, 22)
        self.bucket_btn.setToolTip("キャンバス左クリックで領域をこの色に\n右クリックで上書き解除")
        self.bucket_btn.clicked.connect(self.pick_bucket_color)
        self._paint_bucket_btn()
        tb.addWidget(self.bucket_btn)

        a = QAction("上書きクリア", self)
        a.triggered.connect(self.clear_overrides)
        tb.addAction(a)

        tb.addSeparator()
        a = QAction("🖼 PNG書き出し", self)
        a.triggered.connect(self.export_png)
        tb.addAction(a)
        a = QAction("🎞 アニメ書き出し", self)
        a.triggered.connect(self.export_sequence)
        tb.addAction(a)

    def _build_menu(self):
        m = self.menuBar().addMenu("ファイル")
        for text, fn, key in [
                ("開く...", self.open_image, "Ctrl+O"),
                ("参照画像を開く(reference塗り用)...", self.open_reference, None),
                ("PNG書き出し...", self.export_png, "Ctrl+E"),
                ("アニメ書き出し...", self.export_sequence, "Ctrl+Shift+E"),
                ("プリセット保存...", self.save_preset, "Ctrl+S"),
                ("プリセット読込...", self.load_preset, None)]:
            a = QAction(text, self)
            if key:
                a.setShortcut(key)
            a.triggered.connect(fn)
            m.addAction(a)

        m = self.menuBar().addMenu("出力オプション")
        self.act_layers = QAction("レイヤー個別PNGも保存", self, checkable=True)
        self.act_flow = QAction("flow map(UE5用)も保存", self, checkable=True)
        m.addAction(self.act_layers)
        m.addAction(self.act_flow)

    # ================================================== image io
    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "画像を開く", "", IMG_FILTER)
        if path:
            self.load_image(path)

    def load_image(self, path: str):
        try:
            self.full_bgr = io_utils.imread(path)
        except Exception as e:
            QMessageBox.warning(self, "読み込み失敗", str(e))
            return
        self.source_path = path
        self.params.flatting.color_overrides.clear()
        self._rebuild_preview()
        self.status.showMessage(
            f"{os.path.basename(path)}  {self.full_bgr.shape[1]}x{self.full_bgr.shape[0]}")

    def open_reference(self):
        path, _ = QFileDialog.getOpenFileName(self, "参照画像", "", IMG_FILTER)
        if not path:
            return
        self.reference_full = io_utils.imread(path)
        self.params.flatting.color_source = "reference"
        self.binder.refresh()
        self._rebuild_preview()

    def _rebuild_preview(self):
        if self.full_bgr is None:
            return
        long_edge = self.res_combo.currentData()
        self.preview_bgr = self._scaled(self.full_bgr, long_edge)
        self.reference_preview = (
            self._scaled_to(self.reference_full, self.preview_bgr.shape)
            if self.reference_full is not None else None)
        self.img_token = f"{self.source_path}|{long_edge}|{id(self.full_bgr)}"
        self.schedule_render(immediate=True)

    @staticmethod
    def _scaled(img: np.ndarray, long_edge: int) -> np.ndarray:
        if not long_edge:
            return img
        h, w = img.shape[:2]
        s = long_edge / max(h, w)
        if s >= 1.0:
            return img
        return cv2.resize(img, (int(w * s), int(h * s)),
                          interpolation=cv2.INTER_AREA)

    @staticmethod
    def _scaled_to(img: np.ndarray, shape) -> np.ndarray:
        return cv2.resize(img, (shape[1], shape[0]),
                          interpolation=cv2.INTER_AREA)

    # ================================================== rendering
    def _params_at_current_time(self, base_res_params=None) -> PipelineParams:
        p = (base_res_params or self.params)
        if self.timeline.has_tracks():
            return self.timeline.build_engine_timeline().apply(
                p, self.timeline.t)
        return p.clone()

    def _on_param_changed(self, _path: str):
        self.schedule_render()

    def schedule_render(self, immediate: bool = False):
        if self.preview_bgr is None:
            return
        if immediate:
            self._debounce.stop()
            self.request_render()
        else:
            self._debounce.start()

    def request_render(self):
        if self.preview_bgr is None:
            return
        self._req_id += 1
        self.worker.submit(self._req_id, self.img_token, self.preview_bgr,
                           self._params_at_current_time(),
                           self.reference_preview)

    def on_rendered(self, req_id: int, images: dict, ms: float):
        if req_id != self._req_id:
            return  # 古い結果は捨てる
        self.last_images = images
        self.refresh_canvas()
        n = int(images["labels"].max())
        self.status.showMessage(f"領域数 {n}   render {ms:.0f} ms")

    def refresh_canvas(self):
        if not self.last_images:
            return
        key = self.layer_panel.current_layer()
        im = self.last_images
        if key == "lines":
            img = (255 - im["line_alpha"] * 255).astype(np.uint8)
        elif key == "labels":
            img = labels_preview(im["labels"])
        else:
            img = im[key]
        self.canvas.set_image(img)

    # ================================================== bucket tool
    def on_bucket(self, x: float, y: float):
        if not self.last_images or self.layer_panel.current_layer() not in (
                "final", "composed", "flat", "labels"):
            return
        self.params.flatting.color_overrides.append(
            {"x": round(x, 5), "y": round(y, 5), "color": self.bucket_color})
        self.schedule_render(immediate=True)

    def on_unbucket(self, x: float, y: float):
        if not self.last_images:
            return
        labels = self.last_images["labels"]
        h, w = labels.shape
        target = labels[int(y * (h - 1)), int(x * (w - 1))]
        ovs = self.params.flatting.color_overrides
        kept = [o for o in ovs
                if labels[int(o["y"] * (h - 1)), int(o["x"] * (w - 1))] != target]
        if len(kept) != len(ovs):
            self.params.flatting.color_overrides[:] = kept
            self.schedule_render(immediate=True)

    def pick_bucket_color(self):
        col = QColorDialog.getColor(QColor(self.bucket_color), self, "バケツ色")
        if col.isValid():
            self.bucket_color = col.name()
            self._paint_bucket_btn()

    def _paint_bucket_btn(self):
        self.bucket_btn.setStyleSheet(
            f"background:{self.bucket_color};border:1px solid #666;"
            "border-radius:4px;")

    def clear_overrides(self):
        self.params.flatting.color_overrides.clear()
        self.schedule_render(immediate=True)

    # ================================================== export
    def _export_params_output(self):
        self.params.output.save_layers = self.act_layers.isChecked()
        self.params.output.save_flow = self.act_flow.isChecked()

    def export_png(self):
        if self.full_bgr is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "PNG書き出し",
                                              "paintflow_out.png", "PNG (*.png)")
        if not path:
            return
        self._export_params_output()
        p = self._params_at_current_time()
        ref = self.reference_full
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            cache = StageCache()
            images = render_stages(cache, "export", self.full_bgr, p, ref)
            io_utils.imwrite(path, images["final"])
            self._save_extras(images, path, p)
        finally:
            QApplication.restoreOverrideCursor()
        self.status.showMessage(f"書き出し完了: {path}")

    def export_sequence(self):
        if self.full_bgr is None:
            return
        if not self.timeline.has_tracks():
            QMessageBox.information(
                self, "アニメ書き出し",
                "タイムラインにトラックがありません。\n"
                "[トラック追加] → [◆ +キー] でキーを打ってから書き出してください。")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "書き出し先フォルダ")
        if not out_dir:
            return
        self._export_params_output()

        full = QMessageBox.question(
            self, "解像度", "フル解像度で書き出しますか?\n(いいえ = プレビュー解像度)",
            QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes
        src = self.full_bgr if full else self.preview_bgr
        ref = self.reference_full if full else self.reference_preview
        if ref is not None:
            ref = self._scaled_to(ref, src.shape)

        tl = self.timeline.build_engine_timeline()
        n = tl.frame_count
        prog = QProgressDialog("レンダリング中...", "キャンセル", 0, n, self)
        prog.setWindowModality(Qt.WindowModal)

        cache = StageCache()
        gif_frames = []
        for i, t in tl.frame_times():
            if prog.wasCanceled():
                break
            prog.setValue(i)
            QApplication.processEvents()
            p = tl.apply(self.params, t)
            images = render_stages(cache, "export", src, p, ref)
            fpath = os.path.join(out_dir, f"frame_{i:04d}.png")
            io_utils.imwrite(fpath, images["final"])
            self._save_extras(images, fpath, p)
            f = images["final"]
            f = cv2.cvtColor(f, cv2.COLOR_BGRA2BGR) if f.shape[2] == 4 else f
            gif_frames.append(self._scaled(f, 960))
        prog.setValue(n)

        if gif_frames and not prog.wasCanceled():
            io_utils.save_gif(gif_frames,
                              os.path.join(out_dir, "preview.gif"), fps=tl.fps)
            self.status.showMessage(
                f"{len(gif_frames)}フレーム書き出し完了: {out_dir}")

    def _save_extras(self, images: dict, main_path: str, p: PipelineParams):
        stem = main_path.rsplit(".", 1)[0]
        if p.output.save_layers:
            io_utils.imwrite(stem + "_lines.png",
                             (images["line_alpha"] * 255).astype(np.uint8))
            io_utils.imwrite(stem + "_flat.png", images["flat"])
        if p.output.save_flow:
            from paintflow.distortion import encode_flow_map
            dx, dy = images["flow"]
            io_utils.imwrite(stem + "_flow.png",
                             encode_flow_map(dx, dy, p.output.flow_max_px))

    # ================================================== preset
    def save_preset(self):
        path, _ = QFileDialog.getSaveFileName(self, "プリセット保存",
                                              "preset.json", "JSON (*.json)")
        if not path:
            return
        data = {"version": 1, "params": self.params.to_dict(),
                "timeline": self.timeline.to_dict(),
                "bucket_color": self.bucket_color}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.status.showMessage(f"プリセット保存: {path}")

    def load_preset(self):
        path, _ = QFileDialog.getOpenFileName(self, "プリセット読込", "",
                                              "JSON (*.json)")
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        p = PipelineParams()
        p.override_from_dict(data.get("params", {}))
        self.params = p
        self.bucket_color = data.get("bucket_color", self.bucket_color)
        self._paint_bucket_btn()
        self.binder.refresh()
        self.param_panel._palette_editor.refresh()
        self.timeline.load_dict(data.get("timeline", {}))
        self.schedule_render(immediate=True)

    # ================================================== dnd / close
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        urls = ev.mimeData().urls()
        if urls:
            self.load_image(urls[0].toLocalFile())

    def closeEvent(self, ev):
        self.worker.stop()
        super().closeEvent(ev)
