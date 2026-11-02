"""PICSY のモデルが『なめらかな社会とその敵』第4章の性質を満たすか確かめる

    python tests/test_model.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from game import TradeGame  # noqa: E402
from picsy import PicsyLedger, contribution_vector  # noqa: E402


def check_quiet(condition: object) -> None:
    if not condition:
        raise AssertionError("自動の自然回収が起きてしまった")


def check(label: str, condition: object) -> None:
    print(f"  {'OK  ' if condition else 'NG  '}{label}")
    if not condition:
        raise AssertionError(label)


def test_initial_state() -> None:
    print("初期状態 (式4.34, 4.35)")
    ledger = PicsyLedger(6)
    check("行和はすべて1", np.allclose(ledger.e.sum(axis=1), 1.0))
    check("自己評価はゼロ E_ii = 0", np.allclose(np.diag(ledger.e), 0.0))
    check("中央銀行の分配は 1/N",
          np.allclose(ledger.e[0][1:], 1 / 6))
    check("予算制約は E_i0 = 1",
          np.allclose([ledger.budget(i) for i in range(1, 7)], 1.0))
    check("メンバーの貢献度は1", np.allclose(ledger.c[1:], 1.0))
    check("中央銀行の貢献度は N", np.isclose(ledger.c[0], 6.0))
    check("購買力は E_i0 * c_i = 1",
          np.allclose([ledger.purchasing_power(i) for i in range(1, 7)], 1.0))


def test_eigenvector() -> None:
    print("貢献度ベクトル (式4.3, 4.4, 4.6)")
    rng = np.random.default_rng(0)
    e = rng.random((5, 5))
    np.fill_diagonal(e, 0.0)
    e /= e.sum(axis=1, keepdims=True)

    c = contribution_vector(e)
    check("cE = c を満たす", np.allclose(c @ e, c))
    check("すべて正", bool((c > 0).all()))
    # この行列には中央銀行がないので, 正規化の確認は先頭を除いた和で行う
    check("先頭を除いた和が n", np.isclose(c[1:].sum(), 4.0))


def test_row_sum_is_kept() -> None:
    print("取引と自然回収 (式4.36-4.39)")
    ledger = PicsyLedger(5, gamma=0.2)
    ledger.trade(buyer=1, seller=3, price=0.3)
    check("取引のあとも行和は1", np.allclose(ledger.e.sum(axis=1), 1.0))
    check("予算制約が α だけ減った", np.isclose(ledger.budget(1), 0.7))
    check("売り手への評価が α だけ増えた", np.isclose(ledger.e[1][3], 0.3))

    ledger.natural_recovery()
    check("自然回収のあとも行和は1", np.allclose(ledger.e.sum(axis=1), 1.0))
    check("予算制約が γ(1-E_i0) だけ回復した",
          np.isclose(ledger.budget(1), 0.7 + 0.2 * 0.3))
    check("ほかの評価は (1-γ) 倍になった",
          np.isclose(ledger.e[1][3], 0.3 * 0.8))
    check("中央銀行の行は変わらない", np.allclose(ledger.e[0][1:], 1 / 5))


def buyer_contribution_error(n: int) -> float:
    """取引によって買い手の貢献度が何%変わるかを測る"""
    ledger = PicsyLedger(n, gamma=0.1)
    ledger.trade(buyer=1, seller=2, price=0.2)
    before = ledger.contribution(1)
    ledger.trade(buyer=1, seller=3, price=0.1)
    return abs(before - ledger.contribution(1)) / before


def test_buyer_contribution_is_kept() -> None:
    # 表4.2「中央銀行法のほうがよい点: 取引の前後で買い手の貢献度が変わらない」.
    # ただしこれは式(4.43)の c_b^{t+1} ≒ c_b^t という仮定の上での話で,
    # 厳密には買い手の貢献度もわずかに動く. そのずれは N に反比例して
    # 小さくなる.
    print("中央銀行法の性質 (表4.2, 式4.43の仮定)")
    errors = [buyer_contribution_error(n) for n in (5, 20, 100)]
    check(f"取引の前後で買い手の貢献度はほぼ変わらない (N=5 で {errors[0]:.1%})",
          errors[0] < 0.05)
    check("人数が増えるほど厳密に変わらなくなる",
          errors[0] > errors[1] > errors[2])
    check("N=100 ではずれは0.2%未満", errors[2] < 0.002)

    ledger = PicsyLedger(5, gamma=0.1)
    ledger.trade(buyer=1, seller=2, price=0.2)
    ledger.trade(buyer=3, seller=4, price=0.4)
    check("メンバーの貢献度の和は N", np.isclose(ledger.c[1:].sum(), 5.0))


def purchasing_power_drop(n: int, price: float) -> tuple[float, float]:
    """定価 price の買い物で, 買い手の購買力と売り手の貢献度がどれだけ動くか"""
    ledger = PicsyLedger(n, gamma=0.1)
    ledger.trade(buyer=1, seller=2, price=0.5)

    buyer, seller = 3, 1
    seller_before = ledger.contribution(seller)
    before = ledger.purchasing_power(buyer)
    ledger.trade(buyer, seller, price)
    return (before - ledger.purchasing_power(buyer),
            ledger.contribution(seller) - seller_before)


def test_price_and_purchasing_power() -> None:
    # 定価 δ = α c_b, 購買力 = E_b0 c_b (式4.40-4.43).
    # ここも c_b^{t+1} ≒ c_b^t の仮定の上に成り立つ近似なので,
    # 人数が増えるほど誤差が小さくなることを確かめる.
    print("定価と購買力 (式4.40-4.43)")
    ledger = PicsyLedger(50, gamma=0.1)
    price = 0.2
    alpha = ledger.price_to_alpha(buyer=3, price=price)
    check("α = δ / c_b", np.isclose(alpha * ledger.contribution(3), price))

    drops = [purchasing_power_drop(n, price)[0] for n in (20, 50, 200)]
    errors = [abs(drop - price) / price for drop in drops]
    check(f"買い手の購買力は定価のぶん減る (N=50 で {drops[1]:.4f} ≒ {price})",
          errors[1] < 0.05)
    check("人数が増えるほど定価どおりになる", errors[0] > errors[1] > errors[2])

    # 式(4.40) c_s^{t+1} = c_s^t + δ: 増えるのは売り手の貢献度である.
    # 売り手の購買力 E_s0 c_s は, 売り手の予算制約 E_s0 の分だけ増える.
    gain = purchasing_power_drop(50, price)[1]
    check(f"売り手の貢献度は定価のぶん増える ({gain:.4f} ≒ {price})",
          abs(gain - price) < 0.05 * price)


def test_value_propagates() -> None:
    # 第3章の中心的な主張: 取引の影響はサプライチェーンを遡って伝播する
    print("価値の伝播 (3.2.1項)")
    # 自然回収がまぎれこまないよう, ここでは手動のみにする
    game = TradeGame("picsy", gamma=0.1, recovery_every=0)
    a, c = game.index_of("A"), game.index_of("C")
    d, market = game.index_of("D"), game.index_of("市場")

    # 先進国Aが途上国Cに紙代100ドルを払い, つくった円3つを市場が
    # 240ドルで買い取る. 取引に加わっていないDとの差を見る.
    game.trade(a, c, price=100.0, memo="紙5枚")
    # 貢献度は総和が N になるように正規化されているので, 伝播の効果は
    # 「取引に関わっていない国に対してどれだけ差がついたか」に表れる.
    before = game.money(c) / game.money(d)
    game.buy_from_market(a, "円", amount=3)
    after = game.money(c) / game.money(d)

    check(f"市場がAから買うと, Aに紙を売ったCと無関係なDの差が開く "
          f"({before:.3f} → {after:.3f})", after > before)
    check("Cは取引に関わっていない国より豊か", game.money(c) > game.money(d))
    check("お金を出した市場は貧しくなる", game.money(market) < game.market_money)

    assert game.shadow is not None
    check(f"SECSY なら市場に売ったAが一番豊か "
          f"(A={game.shadow.money(a):.0f} > C={game.shadow.money(c):.0f})",
          game.shadow.money(a) > game.shadow.money(c))
    check(f"PICSY では紙を供給したCまで価値が伝播して逆転する "
          f"(C={game.money(c):.0f} > A={game.money(a):.0f})",
          game.money(c) > game.money(a))


def test_market_seats() -> None:
    # 購買力は E_i0 c_i で E_i0 <= 1 なので, 1席では500ドルが上限になる.
    # 市場は外の世界を代表するので複数席を占め, 席数 × 500ドル から始める.
    print("市場の初期資金 (席による拡張)")
    game = TradeGame("picsy", gamma=0.1, market_seats=10)
    market = game.index_of("市場")
    check("市場の初期資金は 席数 × 500ドル",
          np.isclose(game.money(market), 5000.0))
    check("国は表3.1どおり500ドルのまま",
          np.isclose(game.money(game.index_of("A")), 500.0))
    check("市場の貢献度は席数ぶん",
          np.isclose(game.currency.contribution(market), 10.0))

    assert game.shadow is not None
    check("SECSY の市場も同額で, 比較が公平になる",
          np.isclose(game.shadow.money(market), 5000.0))

    matrix = game.currency.aggregate_matrix()
    check("まとめた行列は 中央銀行+参加者 の大きさ",
          len(matrix) == len(game.players) + 1)
    check("まとめても行和は1",
          all(np.isclose(sum(row), 1.0) for row in matrix))

    # 席があるので, 補充なしでも市場は何度も買い取れる
    strict = TradeGame("picsy", gamma=0.1, market_seats=10,
                       recovery_every=0, market_unlimited=False)
    a = strict.index_of("A")
    spent = 0.0
    for _ in range(10):
        spent += strict.buy_from_market(a, "円")[0]
    check(f"補充なしで {spent:,.0f}ドル ぶん買い取れる", spent >= 800)


def test_secsy() -> None:
    print("SECSY")
    game = TradeGame("secsy")
    a, c = game.index_of("A"), game.index_of("C")
    game.trade(a, c, price=100.0)
    check("払った国の残高が減る", np.isclose(game.money(a), 400.0))
    check("受け取った国の残高が増える", np.isclose(game.money(c), 600.0))
    game.run_recovery()
    check("自然回収はない", np.isclose(game.money(a), 400.0))


def test_recovery_timing() -> None:
    # 本文では自然回収は「1日に1回とか1時間に1回といった頻度で自動的に
    # 行われる」(4.4.2項). ワークショップに「日」はないので, 取引の回数で
    # 自動的に起こす.
    print("自然回収のタイミング (4.4.2項)")
    game = TradeGame("picsy", gamma=0.2, recovery_every=3)
    a, c = game.index_of("A"), game.index_of("C")

    check("最初は次の回収まで3回", game.until_recovery() == 3)
    check("1回目の取引では起きない", game.trade(a, c, 100.0) is False)
    check("2回目でも起きない", game.trade(c, a, 50.0) is False)
    # Cは2回目で支払って予算制約が減っている。3回目は受け取る側なので、
    # 回収が起きたぶんだけ予算制約が戻るはず。
    budget_before = game.currency.budget(c)
    check("3回目で起きる", game.trade(a, c, 50.0) is True)
    check("払って減っていた予算制約が回復した",
          game.currency.budget(c) > budget_before)
    check("数えなおされる", game.until_recovery() == 3)

    manual = TradeGame("picsy", gamma=0.2, recovery_every=0)
    for _ in range(4):
        check_quiet(manual.trade(a, c, 50.0) is False)
    check("0を指定すると何回取引しても自動では起きない", True)
    check("そのときは次の回収の予定もない", manual.until_recovery() is None)
    budget_before = manual.currency.budget(a)
    manual.run_recovery()
    check("手で起こせる", manual.currency.budget(a) > budget_before)


def test_handouts_only() -> None:
    # 配る物は準備のための一覧でしかなく, ソフトは在庫を検査しない.
    # 紙もはさみも机の上に実物があるので, 現実のほうが正しい.
    print("配る物は追跡しない (表3.1)")
    game = TradeGame("picsy")
    names = [c.name for c in game.countries]
    check("表3.1の6か国", names == ["A", "B", "C", "D", "E", "F"])
    check("先進国ははさみをもつ", game.countries[0].items["はさみ"] == 2)
    check("途上国ははさみをもたない", "はさみ" not in game.countries[2].items)
    check("途上国は紙を20枚もつ", game.countries[2].items["紙"] == 20)

    # 持ち物に関係なく, 市場はどの国からでも買い取れる(机の上で何が
    # 起きたかはソフトにはわからないし, わかる必要もない)
    poorest = game.index_of("F")
    total, _ = game.buy_from_market(poorest, "円", 2)
    check("最貧国からでも買い取れる", np.isclose(total, 160.0))
    check("お金は増えた", game.money(poorest) > 500.0)


def main() -> None:
    for test in (test_initial_state, test_eigenvector, test_row_sum_is_kept,
                 test_buyer_contribution_is_kept, test_price_and_purchasing_power,
                 test_value_propagates, test_market_seats, test_secsy,
                 test_recovery_timing, test_handouts_only):
        test()
    print("\nすべて通りました")


if __name__ == "__main__":
    main()
