"""貿易ゲームの進行を管理する

『なめらかな社会とその敵』3.3.2項で紹介されている貿易ゲームを再現する.

各国は紙から三角形・四角形・円といった財を生産して市場に売る. 財を
生産するには道具(はさみ, ものさし, 三角定規, コンパス, ペン)と資源(紙)の
両方が必要だが, ひとつの国が両方をもっているわけではないので, 国同士の
貿易が必要不可欠になる.

ただし, このソフトが受けもつのは**お金と評価行列だけ**である. 紙もはさみも
ワークショップでは机の上に実物があるので, 誰が何をもっているかは参加者が
見ればわかる. ソフトが在庫を検査すると, 机の実態とずれたときに現実のほうを
邪魔することになる. だからここでは

  * 誰が誰にいくら払ったか
  * 市場が何をいくらで買い取ったか

だけを記録し, 配る物の一覧は準備のための参考として持っておくにとどめる.
"""

from dataclasses import dataclass, field

from currency import INITIAL_MONEY, Currency, PicsyCurrency, SecsyCurrency

# 道具は使っても減らない. 紙は財を生産すると減る資源である.
TOOLS = ("はさみ", "ものさし", "三角定規", "コンパス", "ペン")
PAPER = "紙"

# 市場役が占める席の数. 市場の初期資金 = 席数 × INITIAL_MONEY になる.
# 市場は外の世界を代表していて, ひとつの国より大きいので複数席を占める.
MARKET_SEATS = 10

# 取引何回ごとに自然回収するか. 本文では自然回収は「1日に1回とか1時間に
# 1回といった頻度で自動的に行われる」(4.4.2項)とあるが, 90分のワークショップに
# 「日」はないので, 取引の回数を時計のかわりにする.
RECOVERY_EVERY = 3


@dataclass(frozen=True)
class Product:
    """市場が買い取ってくれる財(図3.7 財の市場価格)"""

    name: str
    price: float
    tools: tuple[str, ...]
    paper: int = 1
    note: str = ""


PRODUCTS: dict[str, Product] = {
    "円": Product("円", 80.0, ("コンパス", "ペン", "はさみ"), note="13cmの円"),
    "三角形": Product("三角形", 50.0, ("三角定規", "ペン", "はさみ"),
                      note="9cmの三角形"),
    "四角形": Product("四角形", 40.0, ("ものさし", "ペン", "はさみ"),
                      note="7×13cmの四角形"),
}

# 表3.1 貿易ゲームにおける初期のアイテム
COUNTRY_TEMPLATES: list[tuple[str, str, dict[str, int]]] = [
    ("A", "先進国", {"はさみ": 2, PAPER: 1, "ものさし": 1, "三角定規": 1,
                     "ペン": 2, "コンパス": 2}),
    ("B", "先進国", {"はさみ": 2, PAPER: 1, "ものさし": 1, "三角定規": 1,
                     "ペン": 2, "コンパス": 2}),
    ("C", "途上国", {PAPER: 20, "ペン": 1, "ものさし": 1}),
    ("D", "途上国", {PAPER: 20, "ペン": 1, "ものさし": 1}),
    ("E", "最貧国", {PAPER: 1, "ペン": 1}),
    ("F", "最貧国", {PAPER: 1, "ペン": 1}),
]

MARKET_NAME = "市場"


@dataclass
class Player:
    """参加者(国, または市場役のゲームマスター)"""

    name: str
    kind: str
    is_market: bool = False


@dataclass
class Country:
    """国の設定と, その国に配る物の一覧

    items はゲームの進行には使わない. 準備のための参考である.
    """

    name: str
    kind: str
    items: dict[str, int] = field(default_factory=dict)

    def items_text(self) -> str:
        if not self.items:
            return "(なし)"
        return ", ".join(f"{k}{v}" for k, v in sorted(self.items.items()))


def default_countries() -> list[Country]:
    """表3.1 貿易ゲームにおける初期のアイテム"""
    return [Country(name, kind, dict(items))
            for name, kind, items in COUNTRY_TEMPLATES]


class TradeGame:
    """貿易ゲームの状態"""

    def __init__(self, currency_kind: str = "picsy", gamma: float = 0.1,
                 num_countries: int = len(COUNTRY_TEMPLATES),
                 market_seats: int = MARKET_SEATS,
                 recovery_every: int = RECOVERY_EVERY,
                 market_unlimited: bool = True):
        if not 2 <= num_countries <= len(COUNTRY_TEMPLATES):
            raise ValueError(
                f"国の数は2以上{len(COUNTRY_TEMPLATES)}以下にしてください")
        if market_seats < 1:
            raise ValueError("市場の席数は1以上にしてください")
        if recovery_every < 0:
            raise ValueError("自然回収の間隔は0以上にしてください")

        self.countries = default_countries()[:num_countries]
        self.players: list[Player] = [
            Player(c.name, c.kind) for c in self.countries]
        self.market_index = len(self.players)
        self.players.append(Player(MARKET_NAME, "ゲームマスター",
                                   is_market=True))

        # 席割り: 国は1席ずつ, 市場は market_seats 席
        self.market_seats = market_seats
        self.seats_of: list[list[int]] = []
        next_seat = 1
        for player in self.players:
            count = market_seats if player.is_market else 1
            self.seats_of.append(list(range(next_seat, next_seat + count)))
            next_seat += count
        self.market_money = market_seats * INITIAL_MONEY

        self.trades = 0
        self.recovery_every = recovery_every
        self.log: list[str] = []
        # 直前の支払いが誰のお金をいくら動かしたか (図3.8 の伝播フロー)
        self.last_effect: list[tuple[str, float]] = []
        self.bought: dict[str, int] = {}   # 市場が買い取った財の数
        self.prices = {name: product.price for name, product in PRODUCTS.items()}
        self.market_unlimited = market_unlimited
        self.currency: Currency = self._make_currency(currency_kind, gamma)
        # PICSY のときは, 同じ取引を通常の決済貨幣で行ったらどうなるかを
        # 影で記録しておく(図3.9「PICSY効果なし」のランキング)
        self.shadow: SecsyCurrency | None = (
            self._make_secsy() if isinstance(self.currency, PicsyCurrency)
            else None)

    # ------------------------------------------------------------------
    # 初期化
    # ------------------------------------------------------------------
    def _make_secsy(self) -> SecsyCurrency:
        # 市場の手持ちは PICSY と同額にして, 2つの貨幣システムを公平に比べる
        return SecsyCurrency(len(self.players), initial_money=INITIAL_MONEY,
                             rich={self.market_index: self.market_money})

    def _make_currency(self, kind: str, gamma: float) -> Currency:
        kind = kind.lower()
        if kind == "picsy":
            return PicsyCurrency(self.seats_of, gamma=gamma)
        if kind == "secsy":
            return self._make_secsy()
        raise ValueError("貨幣システムは picsy か secsy を指定してください")

    # ------------------------------------------------------------------
    # 参照
    # ------------------------------------------------------------------
    @property
    def market(self) -> Player:
        return self.players[self.market_index]

    def index_of(self, name: str) -> int:
        """名前から参加者のインデックスを引く(大文字小文字は区別しない)"""
        for i, player in enumerate(self.players):
            if player.name.lower() == name.lower():
                return i
        raise ValueError(f"「{name}」という参加者はいません")

    def money(self, i: int) -> float:
        return self.currency.money(i)

    def price_of(self, product_name: str) -> float:
        """いまの市場価格(ゲームマスターが変更できる)"""
        return self.prices[self._product(product_name).name]

    def ranking(self, currency: Currency | None = None
                ) -> list[tuple[Player, float]]:
        """国をお金の多い順に並べる(市場役は含めない)"""
        source = currency or self.currency
        rows = [(p, source.money(i)) for i, p in enumerate(self.players)
                if not p.is_market]
        return sorted(rows, key=lambda row: row[1], reverse=True)

    def until_recovery(self) -> int | None:
        """次の自然回収まであと何回の取引か(手動のみなら None)"""
        if not self.recovery_every:
            return None
        return self.recovery_every - (self.trades % self.recovery_every)

    def set_price(self, product_name: str, price: float) -> None:
        """市場価格を変更する

        本文にあるとおり, 価格はゲームマスターによって逐次変更される.
        """
        if price <= 0:
            raise ValueError("価格は正の数を指定してください")
        name = self._product(product_name).name
        before = self.prices[name]
        self.prices[name] = price
        self._record(f"市場価格を変更: {name} {before:.0f}ドル → {price:.0f}ドル")

    # ------------------------------------------------------------------
    # 取引
    # ------------------------------------------------------------------
    def trade(self, buyer: int, seller: int, price: float,
              memo: str = "") -> bool:
        """国どうしの支払いを記録する

        何を売り買いしたかは memo に書くだけで, 持ち物の検査はしない
        (モノは机の上にある). 戻り値は自然回収が起きたかどうか.
        """
        if buyer == seller:
            raise ValueError("自分自身とは取引できません")
        if price <= 0:
            raise ValueError("金額は正の数を指定してください")
        if not self.currency.can_pay(buyer, price):
            raise ValueError(
                f"{self.players[buyer].name}のお金が足りません"
                f"(いま {self.money(buyer):,.0f}ドル)")

        before = self._snapshot()
        self._settle(buyer, seller, price)
        text = (f"{self.players[buyer].name} が {self.players[seller].name} に "
                f"{price:,.0f}ドル払った")
        if memo:
            text += f"({memo})"
        recovered = self._finish(text)
        self.last_effect = self._effect_since(before)
        return recovered

    def buy_from_market(self, country: int, product_name: str,
                        amount: int = 1) -> tuple[float, bool]:
        """市場が財を買い取る. 価格は市場価格(図3.7)で決まっている."""
        product = self._product(product_name)
        player = self.players[country]
        if player.is_market:
            raise ValueError("市場は市場に売れません")
        if amount < 1:
            raise ValueError("個数は1以上を指定してください")

        total = self.price_of(product.name) * amount
        if self.market_unlimited and isinstance(self.currency, PicsyCurrency):
            self.currency.ensure_budget(self.market_index, total)
        if not self.currency.can_pay(self.market_index, total):
            raise ValueError(
                f"市場の購買力が足りません"
                f"(いま {self.money(self.market_index):,.0f}ドル). "
                "市場の初期資金を増やすか, 自然回収を起こしてください")

        before = self._snapshot()
        self._settle(self.market_index, country, total)
        self.bought[product.name] = self.bought.get(product.name, 0) + amount
        recovered = self._finish(
            f"市場 が {player.name} から {product.name}×{amount} を "
            f"{total:,.0f}ドルで買い取った")
        self.last_effect = self._effect_since(before)
        return total, recovered

    def run_recovery(self) -> None:
        """手で自然回収を起こす(説明のとき用)"""
        before = self._snapshot()
        self.currency.end_of_day()
        self._record("自然回収を起こした")
        self.last_effect = self._effect_since(before)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _settle(self, buyer: int, seller: int, price: float) -> None:
        """支払いを本番の貨幣と, 比較用の影の SECSY の両方に記録する"""
        self.currency.pay(buyer, seller, price)
        if self.shadow is not None:
            self.shadow.pay(buyer, seller, price, force=True)

    def _finish(self, text: str) -> bool:
        self.trades += 1
        self._record(text)
        return self._maybe_recover()

    def _maybe_recover(self) -> bool:
        if not self.recovery_every:
            return False
        if self.trades % self.recovery_every:
            return False
        self.currency.end_of_day()
        self._record(f"自然回収(取引{self.recovery_every}回ごと)")
        return True

    def _snapshot(self) -> list[float]:
        return [self.money(i) for i in range(len(self.players))]

    def _effect_since(self, before: list[float]) -> list[tuple[str, float]]:
        effect = [(p.name, self.money(i) - before[i])
                  for i, p in enumerate(self.players)
                  if abs(self.money(i) - before[i]) > 0.5]
        effect.sort(key=lambda row: row[1], reverse=True)
        return effect

    def _product(self, name: str) -> Product:
        if name not in PRODUCTS:
            raise ValueError(
                f"「{name}」という財はありません"
                f"(ある財: {', '.join(PRODUCTS)})")
        return PRODUCTS[name]

    def _record(self, text: str) -> None:
        self.log.append(f"[#{self.trades}] {text}")
