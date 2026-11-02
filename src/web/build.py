"""公開用の1枚ものHTMLを組み立てる

    python src/web/build.py

リポジトリではモデル(picsy.js)と画面(index.html)を分けておきたいが,
公開したページでは外部ファイルの読み込みに失敗すると画面がまるごと
動かなくなってしまう. そこで picsy.js を index.html に埋め込んだ
dist/index.html を作り, そちらを公開する.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
TAG = '<script src="picsy.js"></script>'


def build() -> Path:
    page = (HERE / "index.html").read_text(encoding="utf-8")
    model = (HERE / "picsy.js").read_text(encoding="utf-8")

    if TAG not in page:
        raise SystemExit(f"index.html に {TAG} が見つかりません")
    # </script> が JS の文字列中にあると早期に閉じてしまうので念のため確認する
    if "</script" in model:
        raise SystemExit("picsy.js に </script> を含めないでください")

    inlined = page.replace(
        TAG,
        "<script>\n/* src/web/picsy.js を埋め込んだもの。"
        "編集は src/web/picsy.js のほうで行い、python src/web/build.py で作りなおす。 */\n"
        + model.rstrip()
        + "\n</script>",
    )

    out = HERE / "dist" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(inlined, encoding="utf-8")
    return out


if __name__ == "__main__":
    path = build()
    print(f"{path} を書き出しました ({path.stat().st_size:,} バイト)")
