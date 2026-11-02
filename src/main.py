"""PICSY 貿易ゲーム

『なめらかな社会とその敵』第3章で紹介されている貿易ゲームを,
伝播投資貨幣 PICSY(と比較用の通常の決済貨幣 SECSY)の上で遊ぶための
コマンドラインツール.

    python src/main.py                # 対話的に設定を聞く
    python src/main.py --picsy        # PICSY ですぐ始める
    python src/main.py --secsy        # SECSY ですぐ始める

    --gamma=0.2            自然回収率 γ を指定する
    --market-money=5000    市場の初期資金(500ドル刻み)
    --recovery-every=3     取引何回ごとに自然回収するか(0 = 手動のみ)
    --strict-market        市場役にも購買力の制約をかける
"""

import sys
import unicodedata

from currency import INITIAL_MONEY, PicsyCurrency
from game import (COUNTRY_TEMPLATES, MARKET_SEATS, PAPER, PRODUCTS,
                  RECOVERY_EVERY, TOOLS, TradeGame)

# 自然回収率 γ のきめうちの初期値
DEFAULT_GAMMA = 0.1

HELP = """\
このソフトが追うのはお金と評価行列だけ。紙やはさみの受け渡しは机の上で。

コマンド一覧
  状態                                   参加者の一覧とランキングを表示する
  買取 <国> <財> [個数]                  市場が財を買い取る(金額は市場価格)
  取引 <払う国> <受け取る国> <金額> [メモ]  国どうしの支払いを記録する
  自然回収                               自然回収を手で起こす
  価格                                   財と市場価格を表示する
  価格 <財> <新価格>                     市場価格を変更する(ゲームマスター)
  配布物                                 各国に配る物の一覧を表示する
  行列                                   評価行列と貢献度ベクトルを表示する
  比較                                   PICSYの効果あり/なしのランキング(図3.9)
  履歴                                   これまでの取引を表示する
  ヘルプ                                 この一覧を表示する
  終了                                   ゲームを終わる

例:
  買取 C 四角形 3            市場が C から四角形3つを買い取る
  取引 A C 300 紙5枚とはさみ  A が C に300ドル払う(メモつき)
"""

ALIASES = {
    "s": "状態", "status": "状態",
    "p": "価格", "price": "価格",
    "b": "買取", "buy": "買取", "sell": "買取", "売却": "買取",
    "trade": "取引", "t": "取引",
    "r": "自然回収", "recover": "自然回収", "回収": "自然回収",
    "items": "配布物", "配る物": "配布物",
    "m": "行列", "matrix": "行列",
    "c": "比較", "compare": "比較",
    "log": "履歴", "l": "履歴",
    "h": "ヘルプ", "help": "ヘルプ", "?": "ヘルプ",
    "q": "終了", "quit": "終了", "exit": "終了",
}


# ----------------------------------------------------------------------
# 表示まわり
# ----------------------------------------------------------------------
def width(text: str) -> int:
    """全角文字を2文字分として数えた表示幅"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1
               for ch in text)


def pad(text: str, size: int, align: str = "left") -> str:
    space = " " * max(0, size - width(text))
    return space + text if align == "right" else text + space


def show_table(headers: list[str], rows: list[list[str]],
               aligns: list[str] | None = None) -> None:
    aligns = aligns or ["left"] * len(headers)
    sizes = [max(width(headers[i]), *(width(r[i]) for r in rows)) if rows
             else width(headers[i]) for i in range(len(headers))]
    line = "  ".join(pad(h, sizes[i], aligns[i]) for i, h in enumerate(headers))
    print(line)
    print("-" * width(line))
    for row in rows:
        print("  ".join(pad(c, sizes[i], aligns[i]) for i, c in enumerate(row)))


def show_status(game: TradeGame) -> None:
    extra = game.currency.columns()
    headers = ["国", "タイプ", "お金(ドル)", *extra]
    aligns = ["left", "left", "right", *["right"] * len(extra)]
    rows = [[player.name, player.kind, f"{game.money(i):,.0f}",
             *game.currency.values(i)]
            for i, player in enumerate(game.players)]
    until = game.until_recovery()
    clock = "自然回収は手動のみ" if until is None else f"次の自然回収まであと{until}回"
    print(f"\n=== 取引{game.trades}回 / {clock} ===")
    print(game.currency.describe())
    show_table(headers, rows, aligns)


def show_prices(game: TradeGame) -> None:
    print("\n【市場価格(図3.7)】")
    show_table(
        ["財", "市場価格", "必要な道具", "資源"],
        [[f"{p.name}({p.note})", f"${game.price_of(p.name):,.0f}",
          ", ".join(p.tools), f"{PAPER}{p.paper}枚"]
         for p in PRODUCTS.values()],
        ["left", "right", "left", "left"],
    )
    print(f"\n道具: {', '.join(TOOLS)} / 資源: {PAPER}"
          "(受け渡しは机の上で。ソフトは追跡しない)")


def show_handouts(game: TradeGame) -> None:
    """各国に配る物の一覧(準備のための参考。ソフトは追跡しない)"""
    print("\n【各国に配る物】ソフトはこれを追跡しないので, 受け渡しは机の上で自由に")
    items = [*TOOLS, PAPER]
    rows = []
    for country in game.countries:
        rows.append([country.name, country.kind,
                     *[str(country.items.get(item, "")) or "·" for item in items]])
    show_table(["国", "タイプ", *items], rows,
               ["left", "left", *["right"] * len(items)])
    if game.bought:
        tally = ", ".join(f"{k}×{v}" for k, v in sorted(game.bought.items()))
        print(f"\n市場がこれまでに買い取った財: {tally}")


def show_matrix(game: TradeGame) -> None:
    currency = game.currency
    if not isinstance(currency, PicsyCurrency):
        print("評価行列は PICSY のときだけ表示できます")
        return
    names = ["中央銀行"] + [p.name for p in game.players]
    matrix = currency.aggregate_matrix()
    contribution = currency.aggregate_contribution()
    headers = ["評価者\\評価先", *names]
    rows = []
    for i, name in enumerate(names):
        rows.append([name, *[f"{v:.3f}" for v in matrix[i]]])
    print("\n【評価行列 E】(行=評価する人, 列=評価される人, 列「中央銀行」が予算制約)")
    if game.market_seats > 1:
        print(f"市場は行列のなかでは{game.market_seats}席ぶんあるので, "
              "貢献度で重みづけして1行にまとめて表示している(行和は1のまま)")
    show_table(headers, rows, ["left", *["right"] * len(names)])

    print("\n【貢献度ベクトル c】")
    show_table(
        ["参加者", "貢献度"],
        [[name, f"{contribution[i]:.4f}"] for i, name in enumerate(names)],
        ["left", "right"],
    )


def show_ranking(game: TradeGame) -> None:
    print("\n【ランキング】")
    show_table(
        ["順位", "国", "お金(ドル)"],
        [[f"{rank}", player.name, f"{money:,.0f}"]
         for rank, (player, money) in enumerate(game.ranking(), start=1)],
        ["right", "left", "right"],
    )


def show_effect(game: TradeGame) -> None:
    """図3.8 のように, 1回の支払いが誰のお金をどう動かしたかを見せる"""
    if not isinstance(game.currency, PicsyCurrency) or not game.last_effect:
        return
    parts = [f"{name} {delta:+,.0f}" for name, delta in game.last_effect]
    print("  伝播: " + ", ".join(parts))


def show_comparison(game: TradeGame) -> None:
    """図3.9 と同じ, PICSY の効果があるときとないときのランキングの比較"""
    if game.shadow is None:
        print("この比較は PICSY のときだけ表示できます")
        return

    picsy = game.ranking()
    secsy = game.ranking(game.shadow)
    rows = []
    for rank, ((p1, m1), (p2, m2)) in enumerate(zip(picsy, secsy), start=1):
        rows.append([f"{rank}", p1.name, f"{m1:,.0f}", "│",
                     p2.name, f"{m2:,.0f}"])
    print("\n【ランキングの比較(図3.9)】"
          "同じ取引をしても, 伝播があると順位が変わる")
    show_table(
        ["順位", "国", "PICSY効果あり", "│", "国", "PICSY効果なし"],
        rows,
        ["right", "left", "right", "left", "left", "right"],
    )


# ----------------------------------------------------------------------
# コマンド処理
# ----------------------------------------------------------------------
def handle(game: TradeGame, parts: list[str]) -> bool:
    """1つのコマンドを処理する. ゲームを続けるなら True を返す."""
    command = ALIASES.get(parts[0].lower(), parts[0])
    args = parts[1:]

    if command == "終了":
        show_ranking(game)
        if game.shadow is not None:
            show_comparison(game)
        print("\nおつかれさまでした.")
        return False

    if command == "ヘルプ":
        print(HELP)
    elif command == "状態":
        show_status(game)
        show_ranking(game)
    elif command == "価格":
        if len(args) == 2:
            game.set_price(args[0], float(args[1]))
            print(f"{args[0]} の市場価格を {float(args[1]):,.0f}ドルに変更した")
        elif args:
            raise ValueError("使い方: 価格 / 価格 <財> <新価格>")
        show_prices(game)
    elif command == "配布物":
        show_handouts(game)
    elif command == "買取":
        if len(args) not in (2, 3):
            raise ValueError("使い方: 買取 <国> <財> [個数]")
        index = game.index_of(args[0])
        amount = int(args[2]) if len(args) == 3 else 1
        total, recovered = game.buy_from_market(index, args[1], amount)
        print(f"市場が {args[0]} から {args[1]}×{amount} を "
              f"{total:,.0f}ドルで買い取った"
              f"(お金: {game.money(index):,.0f}ドル)")
        show_effect(game)
        if recovered:
            print("  取引の区切りなので自然回収も起きた")
    elif command == "取引":
        if len(args) < 3:
            raise ValueError("使い方: 取引 <払う国> <受け取る国> <金額> [メモ]")
        buyer, seller, price = args[0], args[1], float(args[2])
        memo = " ".join(args[3:])
        recovered = game.trade(game.index_of(buyer), game.index_of(seller),
                               price, memo)
        print(f"{buyer} が {seller} に {price:,.0f}ドル払った"
              + (f"({memo})" if memo else "")
              + f"(残り {game.money(game.index_of(buyer)):,.0f}ドル)")
        show_effect(game)
        if recovered:
            print("  取引の区切りなので自然回収も起きた")
    elif command == "自然回収":
        game.run_recovery()
        print("自然回収が起きた。使った評価が予算制約に戻る")
        show_effect(game)
        show_status(game)
    elif command == "比較":
        show_comparison(game)
    elif command == "行列":
        show_matrix(game)
    elif command == "履歴":
        print("\n【履歴】")
        for line in game.log or ["(まだ何も起きていません)"]:
            print("  " + line)
    else:
        print(f"「{command}」は知らないコマンドです. 「ヘルプ」と入力してください.")
    return True


# ----------------------------------------------------------------------
# 起動
# ----------------------------------------------------------------------
def ask_settings(argv: list[str]) -> tuple[str, float, int, int, int]:
    """起動時の設定を決める"""
    most = len(COUNTRY_TEMPLATES)
    if "--picsy" in argv:
        return "picsy", DEFAULT_GAMMA, most, MARKET_SEATS, RECOVERY_EVERY
    if "--secsy" in argv:
        return "secsy", 0.0, most, MARKET_SEATS, RECOVERY_EVERY

    answer = input("貨幣システムを選んでください (1: PICSY, 2: SECSY) [1]: ")
    kind = "secsy" if answer.strip() in ("2", "secsy", "SECSY") else "picsy"

    gamma = DEFAULT_GAMMA
    if kind == "picsy":
        text = input(f"自然回収率を設定してください [{DEFAULT_GAMMA}]: ").strip()
        if text:
            gamma = float(text)

    text = input(f"国の数を入力してください (2〜{most}) [{most}]: ").strip()
    countries = int(text) if text else most

    default_money = MARKET_SEATS * INITIAL_MONEY
    text = input("市場の初期資金を入力してください "
                 f"(500ドル刻み) [{default_money:,.0f}]: ").strip()
    money = float(text) if text else default_money
    seats = max(1, round(money / INITIAL_MONEY))

    every = RECOVERY_EVERY
    if kind == "picsy":
        text = input("取引何回ごとに自然回収しますか "
                     f"(0で手動のみ) [{RECOVERY_EVERY}]: ").strip()
        if text:
            every = int(text)
    return kind, gamma, countries, seats, every


def option(argv: list[str], name: str, default: float) -> float:
    """--name=値 の形のオプションを読む"""
    for arg in argv:
        if arg.startswith(f"{name}="):
            return float(arg.split("=", 1)[1])
    return default


def main() -> None:
    argv = sys.argv[1:]
    kind, gamma, countries, seats, every = ask_settings(argv)
    gamma = option(argv, "--gamma", gamma)
    seats = max(1, round(option(argv, "--market-money",
                                seats * INITIAL_MONEY) / INITIAL_MONEY))
    every = int(option(argv, "--recovery-every", every))
    # 市場役も購買力の制約を受けるようにしたいときは --strict-market
    game = TradeGame(kind, gamma, countries, seats, every,
                     market_unlimited="--strict-market" not in argv)

    print("\n" + "=" * 60)
    print("  PICSY 貿易ゲーム")
    print("  『なめらかな社会とその敵』第3章 貿易ゲームのシミュレータ")
    print("=" * 60)
    print(f"貨幣システム: {game.currency.describe()}")
    print(f"市場の初期資金: {game.market_money:,.0f}ドル"
          f"({game.market_seats}席ぶん) / 各国: {INITIAL_MONEY:,.0f}ドル")
    if game.recovery_every:
        print(f"自然回収: 取引{game.recovery_every}回ごとに自動")
    else:
        print("自然回収: 手動のみ")
    show_prices(game)
    show_status(game)
    show_handouts(game)
    print("\n道具をもつ国と紙をもつ国は別々なので, 貿易をしないと財はつくれません.")
    print("「ヘルプ」でコマンド一覧を表示します.\n")

    while True:
        try:
            line = input(f"[取引{game.trades}回] > ").strip()
        except EOFError:
            print()
            break
        if not line:
            continue
        try:
            if not handle(game, line.split()):
                break
        except ValueError as error:
            print(f"エラー: {error}")


if __name__ == "__main__":
    main()
