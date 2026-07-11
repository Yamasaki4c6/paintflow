"""
cli.py — コマンドライン実行

静止画1枚:
    python cli.py input.png -o out.png

タイムラインで連番+GIFプレビュー:
    python cli.py input.png -o renders/ --timeline timeline.json --gif

パラメータをJSONで上書き:
    python cli.py input.png -o out.png --config my_params.json

flow map(UE5再現用)も出力:
    python cli.py input.png -o out.png --save-flow
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from paintflow import Pipeline, PipelineParams, Timeline, io_utils


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="paintflow: 線画抽出 / 自動彩色 / 水滴ひずみ")
    ap.add_argument("input", help="入力画像パス(日本語パス可)")
    ap.add_argument("-o", "--out", default="out.png",
                    help="出力パス。--timeline指定時はディレクトリ")
    ap.add_argument("--config", help="パラメータ上書きJSON")
    ap.add_argument("--timeline", help="タイムラインJSON(指定で連番モード)")
    ap.add_argument("--reference", help="彩色reference画像")
    ap.add_argument("--gif", action="store_true",
                    help="連番モード時にpreview.gifも出力")
    ap.add_argument("--save-layers", action="store_true",
                    help="lines/flatレイヤーも個別保存")
    ap.add_argument("--save-flow", action="store_true",
                    help="変位flow map PNGも保存(UE5用)")
    ap.add_argument("--set", action="append", default=[], metavar="PATH=VAL",
                    help="単発上書き 例: --set drip.strength=24")
    ap.add_argument("-v", "--verbose", action="store_true")
    return ap


def parse_set_overrides(params: PipelineParams, pairs: list[str]) -> None:
    for pair in pairs:
        path, _, raw = pair.partition("=")
        cur = params.get_path(path)
        if isinstance(cur, bool):
            val = raw.lower() in ("1", "true", "yes")
        elif isinstance(cur, int):
            val = int(float(raw))
        elif isinstance(cur, float):
            val = float(raw)
        else:
            val = raw
        params.set_path(path, val)


def main(argv=None) -> int:
    args = build_argparser().parse_args(argv)

    params = (PipelineParams.from_json(args.config)
              if args.config else PipelineParams())
    parse_set_overrides(params, args.set)
    params.output.save_layers |= args.save_layers
    params.output.save_flow |= args.save_flow

    pipe = Pipeline(params, verbose=args.verbose)
    ref = io_utils.imread(args.reference) if args.reference else None

    if args.timeline:
        tl = Timeline.from_json(args.timeline)
        img = io_utils.imread(args.input)
        gif = os.path.join(args.out, "preview.gif") if args.gif else None
        paths = pipe.render_sequence(img, tl, args.out, reference=ref,
                                     gif_path=gif)
        print(f"{len(paths)} frames -> {args.out}")
    else:
        img = io_utils.imread(args.input)
        ctx = pipe.run(img, reference=ref)
        io_utils.imwrite(args.out, ctx.images["final"])
        pipe._save_extras(ctx, args.out)
        print(f"saved -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
