"""ヘッドレスGUIスモークテスト(QT_QPA_PLATFORM=offscreenで実行)"""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from studio import theme
from studio.main_window import MainWindow
from studio.render_worker import StageCache, render_stages
from studio.timeline_widget import Key

app = QApplication([])
theme.apply(app)
win = MainWindow()
win.show()

# 1. 画像読込 → プレビュー構築
win.load_image("test_input.png")
assert win.preview_bgr is not None
print("1. load OK  preview:", win.preview_bgr.shape)

# 2. ワーカースレッド経由のレンダ(シグナル待ち)
loop = QEventLoop()
win.worker.rendered.connect(lambda *_: loop.quit())
QTimer.singleShot(8000, loop.quit)  # タイムアウト保険
loop.exec()
assert win.last_images, "worker render failed"
print("2. worker render OK  layers:", sorted(win.last_images.keys()))

# 3. キャッシュ効果: drip.melt変更だけなら軽い
import time
p2 = win.params.clone(); p2.drip.melt = 0.3
t0 = time.perf_counter()
render_stages(win.worker.cache, win.img_token, win.preview_bgr, p2)
dt_drip = (time.perf_counter() - t0) * 1000
p3 = p2.clone(); p3.lineart.c = 9.0
t0 = time.perf_counter()
render_stages(win.worker.cache, win.img_token, win.preview_bgr, p3)
dt_full = (time.perf_counter() - t0) * 1000
print(f"3. cache OK  drip-only {dt_drip:.0f}ms vs full {dt_full:.0f}ms")
assert dt_drip < dt_full

# 4. バケツ上書き → flatが変わる
before = win.last_images["flat"].copy()
win.on_bucket(0.5, 0.3)  # 頭のあたり
loop2 = QEventLoop(); win.worker.rendered.connect(lambda *_: loop2.quit())
QTimer.singleShot(8000, loop2.quit); loop2.exec()
after = win.last_images["flat"]
assert (before != after).any(), "bucket override had no effect"
print("4. bucket OK  overrides:", win.params.flatting.color_overrides)

# 5. 右クリック解除
win.on_unbucket(0.5, 0.3)
assert not win.params.flatting.color_overrides
print("5. unbucket OK")

# 6. タイムライン: トラック追加→キー→エンジン変換→スクラブ
win.timeline.tracks["drip.melt"] = [Key(0.0, 0.0, "linear"),
                                    Key(1.6, 1.0, "ease_in_out")]
win.timeline.area.sizeHintRows()
tl = win.timeline.build_engine_timeline()
assert abs(tl.tracks["drip.melt"].evaluate(0.8) - 0.5) < 0.05
win.timeline.set_time(1.0)
loop3 = QEventLoop(); win.worker.rendered.connect(lambda *_: loop3.quit())
QTimer.singleShot(8000, loop3.quit); loop3.exec()
print("6. timeline OK  eval(0.8) =", round(tl.tracks["drip.melt"].evaluate(0.8), 3))

# 7. プリセット往復
data = {"version": 1, "params": win.params.to_dict(),
        "timeline": win.timeline.to_dict(), "bucket_color": win.bucket_color}
with open("_preset_test.json", "w", encoding="utf-8") as f:
    json.dump(data, f)
from paintflow.params import PipelineParams
p = PipelineParams()
p.override_from_dict(json.load(open("_preset_test.json"))["params"])
assert p.drip.strength == win.params.drip.strength
print("7. preset roundtrip OK")

# 8. エクスポート経路(ダイアログなしで直接): 6フレーム連番+GIF
from paintflow import io_utils
cache = StageCache()
os.makedirs("_export_test", exist_ok=True)
frames = []
import cv2
for i, t in tl.frame_times():
    if i >= 6:
        break
    pp = tl.apply(win.params, t)
    images = render_stages(cache, "exp", win.full_bgr, pp)
    io_utils.imwrite(f"_export_test/f_{i:04d}.png", images["final"])
    f = cv2.cvtColor(images["final"], cv2.COLOR_BGRA2BGR)
    frames.append(f)
io_utils.save_gif(frames, "_export_test/prev.gif", fps=12)
print("8. export path OK")

# 9. レイヤー切替+スクリーンショット
for row in range(6):
    win.layer_panel.setCurrentRow(row)
win.layer_panel.setCurrentRow(0)
win.resize(1380, 860)
app.processEvents()
win.grab().save("_screenshot.png")
print("9. screenshot saved")

win.worker.stop()
print("ALL OK")
