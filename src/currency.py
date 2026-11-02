"""貿易ゲームで使う2つの貨幣システム

『なめらかな社会とその敵』3.3.2項のワークショップでは, 同じ貿易ゲームを
通常の決済貨幣 SECSY と伝播投資貨幣 PICSY の2つのセッションで行い,
最後に結果を比較している. ここではその2つを同じインターフェイスで扱う.
"""

from abc import ABC, abstractmethod

from picsy import PicsyLedger

# 初期の所持金(ドル). 表3.1 ではどの国も500ドルから始める.
INITIAL_MONEY = 500.0


class Currency(ABC):
    """貨幣システムの共通インターフェイス

    参加者は 0..(num_players-1) の整数で指定する.
    金額の単位はドルで, 画面表示もドルで行う.
    """

    name = "貨幣"

    def __init__(self, num_players: int):
        self.num_players = num_players

    @abstractmethod
    def money(self, i: int) -> float:
        """人iがいま使えるお金(ドル)"""

    @abstractmethod
    def can_pay(self, buyer: int, price: float) -> bool:
        """買い手が price ドルを支払えるか"""

    @abstractmethod
    def pay(self, buyer: int, seller: int, price: float) -> None:
        """買い手から売り手へ price ドルを支払う"""

    def end_of_day(self) -> None:
        """1日の終わりに行う処理(PICSY では自然回収)"""

    def columns(self) -> list[str]:
        """一覧表示に追加する列の見出し"""
        return []

    def values(self, i: int) -> list[str]:
        """一覧表示に追加する列の値"""
        return []

    def describe(self) -> str:
        """貨幣システムの設定を1行で説明する"""
        return self.name


class SecsyCurrency(Currency):
    """通常の決済貨幣 SECSY

    お金は単なる残高で, 払えば減り, 受け取れば増える. それだけである.
    """

    name = "SECSY(通常の決済貨幣)"

    def __init__(self, num_players: int, initial_money: float = INITIAL_MONEY,
                 rich: dict[int, float] | None = None):
        super().__init__(num_players)
        self.balance = [initial_money] * num_players
        for i, amount in (rich or {}).items():
            self.balance[i] = amount

    def money(self, i: int) -> float:
        return self.balance[i]

    def can_pay(self, buyer: int, price: float) -> bool:
        return self.balance[buyer] + 1e-9 >= price

    def pay(self, buyer: int, seller: int, price: float,
            force: bool = False) -> None:
        """
        force=True のときは残高が足りなくても支払う.
        PICSY のゲームの影で SECSY の収支を記録しておく
        (図3.9「PICSY効果なし」のランキング)ために使う.
        """
        if not force and not self.can_pay(buyer, price):
            raise ValueError("お金が足りません")
        self.balance[buyer] -= price
        self.balance[seller] += price

    def describe(self) -> str:
        return f"{self.name}: お金は残高として貯蔵され, 伝播しない"


class PicsyCurrency(Currency):
    """伝播投資貨幣 PICSY(中央銀行法)

    お金は購買力 E_i0 * c_i として表され, 購買力1単位を
    INITIAL_MONEY ドルとして表示する. 初期状態では E_i0 = 1, c_i = 1
    なので, 1席ぶんがちょうど INITIAL_MONEY ドルになる.

    ここで厄介なのが, E_i0 は行和が1である以上1を超えられないことである.
    つまり1人分の席では, 初期の購買力はどうやっても c_i 止まりになる.
    市場役は外の世界を代表していてひとつの国より大きいので, 行列の中では
    複数の「席」として扱う. 各席はふつうのメンバーとして 1席=500ドル の
    購買力をもち, 評価も自然回収も他のメンバーとまったく同じように働く.
    こうすると市場は最初から 席数×500ドル をもてるし, 表3.1 の
    「どの国も500ドル」もそのまま保てる.

    seats_of[参加者の番号] = その参加者が占める行列のインデックスの一覧.
    """

    name = "PICSY(伝播投資貨幣・中央銀行法)"

    def __init__(self, seats_of: list[list[int]], gamma: float = 0.1,
                 scale: float = INITIAL_MONEY):
        """
        Parameters
        ----------
        seats_of : list[list[int]]
            参加者ごとの席(評価行列のインデックス). 国は1席, 市場は複数席.
        gamma : float
            自然回収率 γ
        scale : float
            1席の購買力1単位を何ドルとして表示するか
        """
        super().__init__(len(seats_of))
        self.seats_of = seats_of
        self.scale = scale
        self.ledger = PicsyLedger(sum(len(s) for s in seats_of), gamma)

    def money(self, i: int) -> float:
        return sum(self.ledger.purchasing_power(s)
                   for s in self.seats_of[i]) * self.scale

    def contribution(self, i: int) -> float:
        """参加者の貢献度は, 占めている席の貢献度の合計"""
        return sum(self.ledger.contribution(s) for s in self.seats_of[i])

    def budget(self, i: int) -> float:
        """貢献度のうち, どれだけが予算制約として手元に残っているかの割合"""
        total = self.contribution(i)
        if total <= 0:
            return 0.0
        liquid = sum(self.ledger.purchasing_power(s) for s in self.seats_of[i])
        return liquid / total

    def can_pay(self, buyer: int, price: float) -> bool:
        return self.money(buyer) + 1e-6 >= price

    def pay(self, buyer: int, seller: int, price: float) -> None:
        """席をまたいで支払う. 購買力の大きい席から順に出していく."""
        target = self.seats_of[seller][0]
        remaining = price / self.scale
        seats = [s for s in self.seats_of[buyer] if s != target]

        while remaining > 1e-12 and seats:
            seats.sort(key=self.ledger.purchasing_power, reverse=True)
            seat = seats.pop(0)
            available = self.ledger.purchasing_power(seat) * (1 - 1e-9)
            if available <= 1e-12:
                break
            take = min(remaining, available)
            self.ledger.trade(seat, target, take)
            remaining -= take

        if remaining > 1e-9:
            raise ValueError("購買力が足りません")

    def ensure_budget(self, i: int, price: float) -> bool:
        """予算制約が足りないとき, 自然回収を前倒しして補う

        中身は通常の自然回収(式4.38, 4.39)とまったく同じなので,
        行和は1のまま保たれ, 過去の評価も比率を保ったまま残る.
        市場の初期資金を十分にとってあればふつうは出番がない.

        Returns
        -------
        bool
            実際に補充したかどうか
        """
        if self.can_pay(i, price):
            return False

        for _ in range(6):
            for seat in self.seats_of[i]:
                if self.can_pay(i, price):
                    return True
                budget = self.ledger.budget(seat)
                if budget >= 1 - 1e-9:
                    continue
                shortfall = (price - self.money(i)) / self.scale
                need = shortfall / max(self.ledger.contribution(seat), 1e-9)
                rate = min(1.0, need / (1 - budget) * 1.05 + 1e-6)
                self.ledger.natural_recovery(members=[seat], gamma=rate)

        if self.can_pay(i, price):
            return True
        raise ValueError("市場の購買力が足りません"
                         "(市場の初期資金を増やすか, 次の日に進んでください)")

    def end_of_day(self) -> None:
        self.ledger.natural_recovery()

    def aggregate_matrix(self) -> list[list[float]]:
        """表示用に, 市場の席をひとつにまとめた評価行列を返す

        行は貢献度で重みづけして平均するので, まとめた後も行和は1のまま.
        0番は中央銀行, 1番以降が参加者.
        """
        groups = [[0]] + self.seats_of
        c = self.ledger.c
        matrix = []
        for gi, group in enumerate(groups):
            row = [0.0] * len(groups)
            weight = 0.0
            for src in group:
                w = 1.0 if gi == 0 else max(float(c[src]), 1e-12)
                weight += w
                for gj, other in enumerate(groups):
                    row[gj] += w * sum(self.ledger.e[src][dst] for dst in other)
            matrix.append([v / (weight or 1.0) for v in row])
        return matrix

    def aggregate_contribution(self) -> list[float]:
        """まとめた行列に対応する貢献度ベクトル"""
        return [float(self.ledger.c[0])] + [
            self.contribution(i) for i in range(self.num_players)]

    def columns(self) -> list[str]:
        return ["貢献度", "予算制約"]

    def values(self, i: int) -> list[str]:
        return [f"{self.contribution(i):.3f}", f"{self.budget(i):.3f}"]

    def describe(self) -> str:
        return (f"{self.name}: 自然回収率 γ={self.ledger.gamma}, "
                f"購買力1 = {self.scale:.0f}ドル")
