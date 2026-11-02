"""伝播投資貨幣 PICSY の計算モデル(中央銀行法)

『なめらかな社会とその敵』第4章 4.4節「中央銀行法」の数式をそのまま実装する.

評価行列 E は (N+1)×(N+1) で, インデックス 0 を中央銀行に割り当てる
(式 4.34, 4.35). 1..N がコミュニティのメンバーである.

    E_ii = 0            for all i          (4.34)
    E_0i = 1/N          for all i > 0      (4.35)
    予算制約は E_i0     (自己評価法の E_ii のかわり)

取引 (買い手 b が売り手 s から財を買う):

    E_b0 <- E_b0 - α                       (4.36)
    E_bs <- E_bs + α                       (4.37)

自然回収 (自然回収率 γ):

    E_bj <- (1-γ) E_bj   for all j != 0    (4.38)
    E_b0 <- E_b0 + γ (1 - E_b0)            (4.39)

定価と購買力:

    定価   δ = α c_b                       (4.40-4.43)
    購買力 = E_b0 c_b
"""

import numpy as np
import numpy.typing as npt

# 中央銀行に割り当てる行列のインデックス
CENTRAL_BANK = 0


def initialize_eval_matrix(n: int) -> npt.NDArray:
    """評価行列を初期化する

    中央銀行法に従い, (N+1)×(N+1) の行列をつくる.
    インデックス0が中央銀行で, 中央銀行はすべてのメンバーに 1/N を等分配する
    (ソーシャルミニマム). メンバーは最初, 評価をすべて予算制約 E_i0 として
    もっている.

    Parameters
    ----------
    n : int
        コミュニティの構成人数

    Returns
    -------
    numpy.typing.NDArray
        行和がすべて1になる (n+1)×(n+1) の評価行列
    """
    e = np.zeros((n + 1, n + 1))
    for i in range(n + 1):
        e[0][i] = 1 / n
        e[i][0] = 1

    for i in range(n + 1):
        e[i][i] = 0

    return e


def contribution_vector(e: npt.NDArray) -> npt.NDArray:
    """評価行列から貢献度ベクトルを計算する

    sum_{j} E_ij = 1 for all i を満たしているとき,
    つまり人iによる他のメンバーへの評価の総和が1であるとき,
    ペロン・フロベニウスの定理より固有値が1の固有ベクトルが存在する.

    貢献度ベクトル c は cE = c を満たす「左」固有ベクトルなので,
    転置行列 E^T の固有ベクトルとして求める (式 4.3, 4.4).
    メンバー (インデックス1以降) の貢献度の和が N になるように
    正規化する (式 4.6). 初期状態では c = (N, 1, 1, ..., 1) になる.

    Parameters
    ----------
    e : numpy.typing.NDArray
        評価行列

    Returns
    -------
    numpy.typing.NDArray
        長さ (n+1) の貢献度ベクトル. 先頭要素は中央銀行の貢献度.
    """
    n = e.shape[0] - 1

    eigenvalues, eigenvectors = np.linalg.eig(e.T)
    # 固有値1に最も近い固有値に対応する固有ベクトルを選ぶ
    index = int(np.argmin(np.abs(eigenvalues - 1.0)))
    c = np.real(eigenvectors[:, index])

    # 固有ベクトルは符号とスケールが不定なので, 正の向きにそろえてから
    # メンバーの貢献度の和が n になるように正規化する
    if c.sum() < 0:
        c = -c
    c = np.clip(c, 0.0, None)

    total = c[1:].sum()
    if total <= 0:
        raise ValueError("貢献度ベクトルを計算できませんでした")

    return c * (n / total)


class PicsyLedger:
    """PICSY(中央銀行法)の台帳

    評価行列と貢献度ベクトルを保持し, 取引と自然回収を適用する.
    メンバーは 1..n の整数で指定する.
    """

    def __init__(self, n: int, gamma: float = 0.1):
        """
        Parameters
        ----------
        n : int
            コミュニティの構成人数
        gamma : float
            自然回収率 γ
        """
        if n < 2:
            raise ValueError("人数は2人以上である必要があります")
        if not 0.0 <= gamma <= 1.0:
            raise ValueError("自然回収率は0以上1以下である必要があります")

        self.n = n
        self.gamma = gamma
        self.e = initialize_eval_matrix(n)
        self._c: npt.NDArray | None = None

    # ------------------------------------------------------------------
    # 参照
    # ------------------------------------------------------------------
    @property
    def c(self) -> npt.NDArray:
        """貢献度ベクトル(評価行列が変わるたびに計算しなおす)"""
        if self._c is None:
            self._c = contribution_vector(self.e)
        return self._c

    def contribution(self, i: int) -> float:
        """人iの貢献度 c_i"""
        return float(self.c[i])

    def budget(self, i: int) -> float:
        """人iの予算制約 E_i0"""
        return float(self.e[i][CENTRAL_BANK])

    def purchasing_power(self, i: int) -> float:
        """人iの購買力 E_i0 * c_i"""
        return self.budget(i) * self.contribution(i)

    def price_to_alpha(self, buyer: int, price: float) -> float:
        """定価 δ を評価の増加量 α に変換する (δ = α c_b より α = δ / c_b)"""
        c_b = self.contribution(buyer)
        if c_b <= 0:
            raise ValueError("貢献度が0以下の人は取引できません")
        return price / c_b

    def can_pay(self, buyer: int, price: float) -> bool:
        """買い手が定価 δ を支払えるか(予算制約の範囲内か)"""
        return self.price_to_alpha(buyer, price) <= self.budget(buyer) + 1e-12

    # ------------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------------
    def trade(self, buyer: int, seller: int, price: float) -> float:
        """取引を評価行列に反映する (式 4.36, 4.37)

        Parameters
        ----------
        buyer, seller : int
            買い手と売り手のインデックス
        price : float
            定価 δ(貢献度と同じ単位)

        Returns
        -------
        float
            実際に移動した評価の量 α
        """
        if buyer == seller:
            raise ValueError("自分自身とは取引できません")
        if price <= 0:
            raise ValueError("価格は正の数である必要があります")

        alpha = self.price_to_alpha(buyer, price)
        if alpha > self.budget(buyer) + 1e-12:
            raise ValueError("予算制約が足りません")
        alpha = min(alpha, self.budget(buyer))

        self.e[buyer][CENTRAL_BANK] -= alpha
        self.e[buyer][seller] += alpha
        self._c = None
        return alpha

    def natural_recovery(self, members: list[int] | None = None,
                         gamma: float | None = None) -> None:
        """自然回収を行う (式 4.38, 4.39)

        買い手から売り手へ移った評価を少しずつ予算制約に戻す操作.
        中央銀行の行(インデックス0)は操作しない.
        """
        rate = self.gamma if gamma is None else gamma
        if rate <= 0:
            return
        targets = range(1, self.n + 1) if members is None else members

        for b in targets:
            budget = self.e[b][CENTRAL_BANK]
            self.e[b] *= (1 - rate)
            self.e[b][CENTRAL_BANK] = budget + rate * (1 - budget)
        self._c = None
