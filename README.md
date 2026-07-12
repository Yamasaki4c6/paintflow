<<<<<<< HEAD
# paintflow
見ての通り、Claudeで作成したツールです。
画像をある程度手軽にエフェクトをかけるものが欲しくて試してみた次第です。
ちょっとずつAIとPythonのお勉強に弄っていきます。

## ★ GUI版 (Paintflow Studio) ができました

`run_studio.bat` をダブルクリックで起動、`build_exe.bat` で **PaintflowStudio.exe** を作成できます。
リアルタイムプレビュー / 領域クリックで色変更(バケツ) / タイムラインでアニメ書き出し。
**操作方法・exe化の手順は `README_STUDIO.md` を参照。**
以下はエンジン部(CLI / Pythonライブラリ)のドキュメントです。


線画抽出 → 自動彩色 → 水滴ひずみ を1本のパイプラインで処理する絵作り効率化ツール。

設計思想は3つ。**全ステージ決定論**(生成AI不使用・seed固定で完全再現、パイプラインツールとして信頼できる)、**全パラメータをPythonとJSONに露出**、**ステージ差し替え可能なアーキテクチャ**(3DCG背景合成・自作エフェクトを後から差し込める)。

## セットアップ (Windows)

```
pip install -r requirements.txt
```

必要なのは numpy / opencv-python / scipy / Pillow のみ。Python 3.10+ 推奨。
`io_utils.imread/imwrite` は `np.fromfile` + `imdecode` 経由なので**日本語パスでも安全**(素の `cv2.imread` は日本語パスで静かに失敗する)。

## 最短の使い方

```
# 静止画1枚
python cli.py ラフ.png -o out.png

# パラメータ単発上書き
python cli.py ラフ.png -o out.png --set drip.strength=28 --set flatting.seed=4

# タイムライン駆動で連番PNG + プレビューGIF
python cli.py ラフ.png -o renders/ --timeline timeline_example.json --gif

# レイヤー個別出力 + UE5用flow map
python cli.py ラフ.png -o out.png --save-layers --save-flow
```

Pythonから:

```python
from paintflow import Pipeline, PipelineParams

params = PipelineParams()
params.drip.melt = 0.7
Pipeline(params).run_file("rough.png", "out.png")
```

## パイプライン構成

```
input ─→ lineart ─→ flatting ─→ composite ─→ drip ─→ final (BGRA)
          │            │                       │
          line_alpha   labels(領域ID)          flow(dx,dy)
```

`ctx.images` に全中間レイヤーが残る(`input` / `line_mask` / `line_alpha` / `labels` / `flat` / `composed` / `final` / `flow`)。VATパイプラインのJSONマニフェストと同じで、各段の状態を検証しながら進められる。

## パラメータリファレンス

すべて `params.py` の dataclass。JSON(`--config`)、`--set`、Python、タイムラインの4経路から同じパスで触れる。

### lineart(線画抽出)
| パラメータ | 既定 | 説明 |
|---|---|---|
| `mode` | adaptive | `adaptive`=スキャン/ラフ向け、`xdog`=グレー諧調から漫画線、`canny`=3DCGレンダの輪郭化 |
| `denoise` | 5 | bilateral前処理。紙ノイズ除去 |
| `block_size` / `c` | 15 / 7.0 | adaptiveの窓サイズと閾値バイアス。cを上げると線が減る |
| `sigma` `k` `p` `phi` `epsilon` | — | XDoG係数。pを上げるとコントラスト強調 |
| `thickness` | 0 | 線の太らせ(px) |
| `despeckle` | 6 | 孤立ドット除去の面積閾値 |

### flatting(自動彩色)
| パラメータ | 既定 | 説明 |
|---|---|---|
| `gap_close` | 3 | 線の隙間をどれだけ塞いで領域を閉じるか。ラフは4〜6 |
| `min_region` | 48 | 微小領域は隣に吸収 |
| `color_source` | auto | `palette`=指定色を循環割当、`reference`=参照画像の領域平均色(ラフ塗り→クリーンフラット化に便利)、`auto`=決定論パステル |
| `palette` | — | HEX配列 |
| `seed` | 0 | 色割り当てのシャッフル。気に入らなければ変えるだけ |

### composite(合成)
`line_over` / `line_color` / `line_opacity` / `knockout_bg`(画面端に接する最大領域を透明化。**3DCG合成用の前景素材出し**)

### drip(水滴ひずみ)
| パラメータ | 既定 | 説明 |
|---|---|---|
| `melt` | 1.0 | **0..1の全体進行度。タイムラインで駆動する主対象** |
| `strength` | 18.0 | 垂れの最大変位(px) |
| `drip_density` | 1.6 | 幅100pxあたりの雫の本数 |
| `drip_length` | 0.35 | 雫の長さ(画像高さ比) |
| `drip_width` | 5.0 | 雫の太さσ |
| `wobble` | 5.0 | 横揺れ(px) |
| `ambient_warp` | 0.12 | 画面全体の「湿った紙」歪み |
| `noise_scale` | 0.015 | ノイズ粗さ。小さいほど大きなうねり |
| `seed` | 7 | 雫の配置。固定で完全再現 |

### output
`save_layers`(lines/flat個別PNG) / `save_flow`(flow map) / `flow_max_px`(エンコード上限。UE5側と合わせる)

## タイムライン

任意のパラメータをドットパスでキーフレーム駆動。Houdiniのchannel、UE5のSequencerと同じモデル。

```python
from paintflow import Timeline

tl = Timeline(fps=24, duration=2.0)
tl.add("drip.melt",   [(0.0, 0.0), (1.6, 1.0, "ease_in_out"), (2.0, 1.0)])
tl.add("drip.wobble", [(0.0, 1.0), (2.0, 8.0, "ease_in")])
tl.add("composite.line_opacity", [(0.0, 1.0), (2.0, 0.5)])  # 何でも動かせる

pipe.render_sequence(img, tl, "renders/", gif_path="renders/preview.gif")
```

イージング: `linear` `hold` `ease_in` `ease_out` `ease_in_out` `smootherstep`。
`@register_easing("名前")` で自作を登録すればJSONからも使える(`examples/03`参照)。

`t` 時点の値だけ欲しいときは `tl.evaluate(t)` → `{"drip.melt": 0.42, ...}`。外部ツール(Houdini/UE5)側から同じカーブを参照するのにも使える。

## Pythonでの改造(拡張ポイント)

ステージは「`Context` を読み書きする関数」。これだけ守れば何でも差し込める:

```python
def stage_myfx(ctx):
    img = ctx.images["composed"]          # 読む
    ctx.images["composed"] = process(img) # 書く

pipe.insert_after("composite", "myfx", stage_myfx)
pipe.remove("drip")            # ひずみ無し構成
pipe.replace("lineart", my_fn) # 線画抽出を丸ごと差し替え
```

改造の定番パターン:
- **領域単位のエフェクト**: `ctx.images["labels"]` が領域IDマップなので、「この領域だけ色変更/この領域だけ歪ませない」が `mask = labels == n` で書ける
- **ひずみの別実装**: `distortion.get_displacement()` を参考に、渦・熱揺らぎ・磁力線など任意の変位フィールドを作って `cv2.remap` するステージに置換
- **3DCG背景合成**: `examples/03` の `stage_comp_over_bg` が雛形。`ctx.meta["bg_image"]` に背景を渡して final の後段でover合成

## 3DCG(UE5)との連携

**A. 素材として持ち込む**: `knockout_bg=True` で背景抜きのストレートアルファPNG連番を出力 → UE5のFlipbook / Image Plate / Composure、AEでもそのまま使える。テクスチャとして使うなら解像度は2のべき乗にリサイズ推奨。

**B. ひずみをリアルタイム再現する(推奨)**: `save_flow=True` で変位フィールドをflow map PNG(R=dx, G=dy, 0.5=変位ゼロ, B=magnitude)として出力。UE5のpost-process materialで

```
offset_uv = (Texture2DSample(FlowMap, UV).rg - 0.5) * 2.0 * MaxPx / ScreenSize
color = SceneTexture(UV + offset_uv)
```

と復元すれば、**歪んでいない絵をUE5に置いて、歪みだけシェーダで掛ける**構成にできる。melt相当のスカラーをMaterial Parameterにすれば、Sequencerからこのツールと同じカーブで駆動できる。flow mapのTexture設定は **sRGB=OFF(Linear)**、`flow_max_px` はマテリアル側の `MaxPx` と一致させること。ポスプロHLSLでやってたVoronoi crystallizeと同じSceneTexture UVオフセットの応用なので、そのまま流用できるはず。

**C. 逆方向**: UE5/Blenderのレンダ画像を入力にして `lineart.mode="canny"` + `color_source="reference"` を通すと、3DCGレンダのイラスト化(NPR後処理)にも使える。

## ファイル構成

```
paintflow/
├── cli.py                  # CLI
├── requirements.txt
├── timeline_example.json   # タイムラインJSONの雛形
├── paintflow/
│   ├── params.py           # ★全パラメータ定義(まずここを読む)
│   ├── lineart.py          # 線画抽出
│   ├── flatting.py         # 自動彩色
│   ├── distortion.py       # 水滴ひずみ + flow mapエンコード
│   ├── timeline.py         # キーフレーム/イージング
│   ├── pipeline.py         # ステージ管理・連番レンダ
│   └── io_utils.py         # 日本語パス対応IO
└── examples/
    ├── 01_still.py         # 静止画+パラメータ調整
    ├── 02_animate_drip.py  # タイムライン駆動アニメ
    └── 03_custom_stage.py  # 自作ステージ/イージング/3DCG合成雛形
```
=======
# paintflow
>>>>>>> 08fb802a92d055114ab5a7dfa4d09027b61f8cce
