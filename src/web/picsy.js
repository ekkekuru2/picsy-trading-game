/*
 * 伝播投資貨幣 PICSY の計算モデル(中央銀行法)と貿易ゲームの状態。
 * src/picsy.py, src/currency.py, src/game.py を JavaScript に移したもの。
 *
 * 『なめらかな社会とその敵』第4章 4.4節の式をそのまま実装している。
 *   E_ii = 0, E_0i = 1/N            (4.34, 4.35)  インデックス0が中央銀行
 *   取引     E_b0 -= α, E_bs += α   (4.36, 4.37)
 *   自然回収 E_bj *= (1-γ), E_b0 += γ(1-E_b0)  (4.38, 4.39)
 *   定価 δ = α c_b, 購買力 = E_b0 c_b          (4.40-4.43)
 */
(function (global) {
  'use strict';

  var CENTRAL_BANK = 0;
  var INITIAL_MONEY = 500;          // 表3.1 の初期所持金
  var PAPER = '紙';
  var TOOLS = ['はさみ', 'ものさし', '三角定規', 'コンパス', 'ペン'];

  // 図3.7 財の市場価格
  var PRODUCTS = [
    { name: '円', price: 80, tools: ['コンパス', 'ペン', 'はさみ'], paper: 1, note: '13cmの円' },
    { name: '三角形', price: 50, tools: ['三角定規', 'ペン', 'はさみ'], paper: 1, note: '9cmの三角形' },
    { name: '四角形', price: 40, tools: ['ものさし', 'ペン', 'はさみ'], paper: 1, note: '7×13cmの四角形' }
  ];

  // 表3.1 貿易ゲームにおける初期のアイテム
  var COUNTRY_TEMPLATES = [
    { name: 'A', kind: '先進国', items: { 'はさみ': 2, '紙': 1, 'ものさし': 1, '三角定規': 1, 'ペン': 2, 'コンパス': 2 } },
    { name: 'B', kind: '先進国', items: { 'はさみ': 2, '紙': 1, 'ものさし': 1, '三角定規': 1, 'ペン': 2, 'コンパス': 2 } },
    { name: 'C', kind: '途上国', items: { '紙': 20, 'ペン': 1, 'ものさし': 1 } },
    { name: 'D', kind: '途上国', items: { '紙': 20, 'ペン': 1, 'ものさし': 1 } },
    { name: 'E', kind: '最貧国', items: { '紙': 1, 'ペン': 1 } },
    { name: 'F', kind: '最貧国', items: { '紙': 1, 'ペン': 1 } }
  ];

  var MARKET_NAME = '市場';

  function productByName(name) {
    for (var i = 0; i < PRODUCTS.length; i++) {
      if (PRODUCTS[i].name === name) return PRODUCTS[i];
    }
    throw new Error('「' + name + '」という財はありません');
  }

  // ----------------------------------------------------------------
  // 評価行列と貢献度ベクトル
  // ----------------------------------------------------------------

  function initEvalMatrix(n) {
    var e = [];
    for (var i = 0; i <= n; i++) e.push(new Float64Array(n + 1));
    for (i = 0; i <= n; i++) { e[0][i] = 1 / n; e[i][0] = 1; }
    for (i = 0; i <= n; i++) e[i][i] = 0;
    return e;
  }

  /*
   * cE = c を満たす左固有ベクトルを冪乗法で求める (式4.3, 4.4)。
   *
   * 初期の評価行列は「中央銀行 → メンバー → 中央銀行」としか行き来しない
   * 周期2のマルコフ過程なので、素朴な冪乗法だと値が振動して収束しない。
   * そこで c <- (c + cE)/2 という「なまけた」反復にして周期性を消す。
   * 不動点は cE = c とまったく同じである。
   *
   * 最後に、メンバー(1番以降)の貢献度の和が N になるように正規化する(式4.6)。
   */
  function contributionVector(e) {
    var n = e.length - 1;
    var c = new Float64Array(n + 1);
    var next = new Float64Array(n + 1);
    var i, j;
    for (i = 0; i <= n; i++) c[i] = 1;

    for (var step = 0; step < 20000; step++) {
      next.fill(0);
      for (i = 0; i <= n; i++) {
        var ci = c[i];
        if (ci === 0) continue;
        var row = e[i];
        for (j = 0; j <= n; j++) next[j] += ci * row[j];
      }
      var diff = 0;
      for (j = 0; j <= n; j++) {
        var v = 0.5 * (c[j] + next[j]);
        var d = Math.abs(v - c[j]);
        if (d > diff) diff = d;
        c[j] = v;
      }
      if (diff < 1e-14) break;
    }

    var total = 0;
    for (i = 1; i <= n; i++) total += c[i];
    if (!(total > 0)) throw new Error('貢献度ベクトルを計算できませんでした');
    var scale = n / total;
    for (i = 0; i <= n; i++) c[i] *= scale;
    return c;
  }

  function PicsyLedger(n, gamma) {
    if (n < 2) throw new Error('人数は2人以上である必要があります');
    this.n = n;
    this.gamma = gamma;
    this.e = initEvalMatrix(n);
    this._c = null;
  }

  PicsyLedger.prototype = {
    get c() {
      if (!this._c) this._c = contributionVector(this.e);
      return this._c;
    },
    contribution: function (i) { return this.c[i]; },
    budget: function (i) { return this.e[i][CENTRAL_BANK]; },
    purchasingPower: function (i) { return this.budget(i) * this.contribution(i); },

    priceToAlpha: function (buyer, price) {
      var cb = this.contribution(buyer);
      if (cb <= 0) throw new Error('貢献度が0以下の人は取引できません');
      return price / cb;
    },

    canPay: function (buyer, price) {
      return this.priceToAlpha(buyer, price) <= this.budget(buyer) + 1e-12;
    },

    // 取引 (式4.36, 4.37)
    trade: function (buyer, seller, price) {
      if (buyer === seller) throw new Error('自分自身とは取引できません');
      if (!(price > 0)) throw new Error('価格は正の数を指定してください');
      var alpha = this.priceToAlpha(buyer, price);
      if (alpha > this.budget(buyer) + 1e-12) throw new Error('予算制約が足りません');
      alpha = Math.min(alpha, this.budget(buyer));
      this.e[buyer][CENTRAL_BANK] -= alpha;
      this.e[buyer][seller] += alpha;
      this._c = null;
      return alpha;
    },

    // 自然回収 (式4.38, 4.39)。中央銀行の行(0番)は操作しない。
    naturalRecovery: function (members, gamma) {
      var rate = (gamma == null) ? this.gamma : gamma;
      if (!(rate > 0)) return;
      var targets = members;
      if (!targets) {
        targets = [];
        for (var k = 1; k <= this.n; k++) targets.push(k);
      }
      for (var t = 0; t < targets.length; t++) {
        var row = this.e[targets[t]];
        var budget = row[CENTRAL_BANK];
        for (var j = 0; j <= this.n; j++) row[j] *= (1 - rate);
        row[CENTRAL_BANK] = budget + rate * (1 - budget);
      }
      this._c = null;
    }
  };

  // ----------------------------------------------------------------
  // 2つの貨幣システム
  // ----------------------------------------------------------------

  function SecsyCurrency(numPlayers, rich) {
    this.kind = 'secsy';
    this.numPlayers = numPlayers;
    this.balance = [];
    for (var i = 0; i < numPlayers; i++) this.balance.push(INITIAL_MONEY);
    if (rich) {
      for (var key in rich) this.balance[key] = rich[key];
    }
  }

  // 設定の既定値。表3.1 と図3.7 に合わせてある。
  function defaultSettings() {
    return {
      mode: 'picsy',
      gamma: 0.1,
      marketSeats: 10,            // 市場の初期資金 = 席数 × 500ドル
      marketUnlimited: true,
      recoveryEvery: 3,           // 取引何回ごとに自然回収するか(0 = 手動のみ)
      countries: COUNTRY_TEMPLATES.map(function (t) {
        return { name: t.name, kind: t.kind, items: Object.assign({}, t.items) };
      })
    };
  }

  SecsyCurrency.prototype = {
    label: 'SECSY(通常の決済貨幣)',
    describe: function () { return 'お金は残高として貯蔵され, 伝播しない'; },
    money: function (i) { return this.balance[i]; },
    canPay: function (buyer, price) { return this.balance[buyer] + 1e-9 >= price; },
    pay: function (buyer, seller, price, force) {
      if (!force && !this.canPay(buyer, price)) throw new Error('お金が足りません');
      this.balance[buyer] -= price;
      this.balance[seller] += price;
    },
    endOfDay: function () {}
  };

  /*
   * PICSY(中央銀行法)。
   *
   * 購買力は E_i0 c_i で、E_i0 は1を超えられない(行和が1だから)。
   * つまり1人分の席では、どう頑張っても初期の購買力は c_i 止まりになる。
   * 市場役は外の世界を代表していて1つの国より大きいので、行列の中では
   * 複数の「席」として扱う。各席がふつうのメンバーとして 1席=500ドル の
   * 購買力をもち、評価も自然回収も他のメンバーとまったく同じように働く。
   *
   * seatsOf[プレイヤー番号] = そのプレイヤーが占める行列のインデックスの配列。
   * 国は1席、市場は marketSeats 席。
   */
  function PicsyCurrency(seatsOf, gamma) {
    this.kind = 'picsy';
    this.seatsOf = seatsOf;
    this.numPlayers = seatsOf.length;
    this.scale = INITIAL_MONEY;   // 1席の購買力1を500ドルとして表示する
    var total = 0;
    for (var i = 0; i < seatsOf.length; i++) total += seatsOf[i].length;
    this.ledger = new PicsyLedger(total, gamma);
  }

  PicsyCurrency.prototype = {
    label: 'PICSY(伝播投資貨幣・中央銀行法)',
    describe: function () {
      return '自然回収率 γ=' + this.ledger.gamma + ' / 購買力1 = ' + this.scale + 'ドル';
    },

    money: function (i) {
      var seats = this.seatsOf[i], sum = 0;
      for (var k = 0; k < seats.length; k++) sum += this.ledger.purchasingPower(seats[k]);
      return sum * this.scale;
    },

    // プレイヤーの貢献度は、占めている席の貢献度の合計
    contribution: function (i) {
      var seats = this.seatsOf[i], sum = 0;
      for (var k = 0; k < seats.length; k++) sum += this.ledger.contribution(seats[k]);
      return sum;
    },

    // 予算制約は、貢献度のうちどれだけが手元に残っているかの割合
    budget: function (i) {
      var seats = this.seatsOf[i], liquid = 0, total = 0;
      for (var k = 0; k < seats.length; k++) {
        liquid += this.ledger.purchasingPower(seats[k]);
        total += this.ledger.contribution(seats[k]);
      }
      return total > 0 ? liquid / total : 0;
    },

    canPay: function (buyer, price) { return this.money(buyer) + 1e-6 >= price; },

    // 席をまたいで支払う。購買力の大きい席から順に出していく。
    pay: function (buyer, seller, price) {
      var target = this.seatsOf[seller][0];
      var remaining = price / this.scale;
      var seats = this.seatsOf[buyer].slice();
      var self = this;

      for (var pass = 0; pass < seats.length && remaining > 1e-12; pass++) {
        seats.sort(function (a, b) {
          return self.ledger.purchasingPower(b) - self.ledger.purchasingPower(a);
        });
        var seat = seats[pass];
        if (seat === target) continue;
        var available = this.ledger.purchasingPower(seat) * (1 - 1e-9);
        if (available <= 1e-12) continue;
        var take = Math.min(remaining, available);
        this.ledger.trade(seat, target, take);
        remaining -= take;
      }
      if (remaining > 1e-9) throw new Error('購買力が足りません');
    },

    endOfDay: function () { this.ledger.naturalRecovery(); },

    /*
     * 予算制約が足りないとき、自然回収を前倒しして補う。
     * 中身は通常の自然回収(式4.38, 4.39)とまったく同じ操作なので、
     * 行和は1のまま保たれ、過去の評価も比率を保って残る。
     * 市場の初期資金を十分とってあればふつうは出番がない。
     */
    ensureBudget: function (i, price) {
      if (this.canPay(i, price)) return false;
      var seats = this.seatsOf[i];
      for (var pass = 0; pass < 6; pass++) {
        for (var k = 0; k < seats.length; k++) {
          if (this.canPay(i, price)) return true;
          var seat = seats[k];
          var budget = this.ledger.budget(seat);
          if (budget >= 1 - 1e-9) continue;
          var shortfall = (price - this.money(i)) / this.scale;
          var need = shortfall / Math.max(this.ledger.contribution(seat), 1e-9);
          var rate = Math.min(1, need / (1 - budget) * 1.05 + 1e-6);
          this.ledger.naturalRecovery([seat], rate);
        }
      }
      if (this.canPay(i, price)) return true;
      throw new Error('市場の購買力が足りません。市場の初期資金を増やすか、次の日に進んでください');
    },

    /*
     * 表示用に、市場の席をひとつにまとめた評価行列を返す。
     * 行は貢献度で重みづけして平均するので、まとめた後も行和は1のまま。
     * 0番は中央銀行、1番以降がプレイヤー。
     */
    aggregateMatrix: function () {
      var groups = [[0]].concat(this.seatsOf);
      var size = groups.length;
      var c = this.ledger.c;
      var out = [];
      for (var gi = 0; gi < size; gi++) {
        var row = new Float64Array(size);
        var weight = 0;
        for (var a = 0; a < groups[gi].length; a++) {
          var from = groups[gi][a];
          var w = (gi === 0) ? 1 : Math.max(c[from], 1e-12);
          weight += w;
          for (var gj = 0; gj < size; gj++) {
            for (var b = 0; b < groups[gj].length; b++) {
              row[gj] += w * this.ledger.e[from][groups[gj][b]];
            }
          }
        }
        for (gj = 0; gj < size; gj++) row[gj] /= (weight || 1);
        out.push(row);
      }
      return out;
    },

    // まとめた行列に対応する貢献度ベクトル
    aggregateContribution: function () {
      var out = [this.ledger.c[0]];
      for (var i = 0; i < this.seatsOf.length; i++) out.push(this.contribution(i));
      return out;
    }
  };

  // ----------------------------------------------------------------
  // 貿易ゲーム
  // ----------------------------------------------------------------

  /*
   * 貿易ゲームの状態。
   *
   * このアプリが受けもつのはお金と評価行列だけである。紙もはさみも
   * ワークショップでは机の上に実物があるので、誰が何をもっているかは
   * 参加者が見ればわかる。ソフトが在庫を検査すると、机の実態とずれたときに
   * 現実のほうを邪魔することになる。だからここでは、
   *   ・誰が誰にいくら払ったか
   *   ・市場が何をいくらで買い取ったか
   * だけを記録し、配る物の一覧は準備のための参考として持っておくにとどめる。
   */
  function Game(options) {
    var base = defaultSettings();
    options = options || {};
    this.mode = options.mode || base.mode;
    this.gamma = (options.gamma == null) ? base.gamma : options.gamma;
    this.marketSeats = Math.max(1, Math.round(options.marketSeats || base.marketSeats));
    this.marketUnlimited = options.marketUnlimited !== false;
    this.recoveryEvery = (options.recoveryEvery == null)
      ? base.recoveryEvery : Math.max(0, Math.round(options.recoveryEvery));

    var templates = options.countries && options.countries.length
      ? options.countries : base.countries;
    // 配る物の一覧。ゲームの進行には使わず、準備と手元の参考にするだけ。
    this.countries = templates.map(function (t) {
      return { name: t.name, kind: t.kind, items: Object.assign({}, t.items) };
    });

    this.players = this.countries.map(function (t) {
      return { name: t.name, kind: t.kind, isMarket: false };
    });
    this.marketIndex = this.players.length;
    this.players.push({ name: MARKET_NAME, kind: 'ゲームマスター', isMarket: true });

    this.trades = 0;
    this.log = [];
    this.lastEffect = [];   // 直前の支払いが誰のお金をいくら動かしたか (図3.8)
    this.bought = {};       // 市場が買い取った財の数
    this.prices = {};
    for (var i = 0; i < PRODUCTS.length; i++) this.prices[PRODUCTS[i].name] = PRODUCTS[i].price;

    // 席割り: 国は1席ずつ、市場は marketSeats 席。
    // 市場の初期資金は席数 × 500ドルになる。
    var seatsOf = [], next = 1;
    for (i = 0; i < this.players.length; i++) {
      var count = this.players[i].isMarket ? this.marketSeats : 1;
      var seats = [];
      for (var k = 0; k < count; k++) seats.push(next++);
      seatsOf.push(seats);
    }
    this.seatsOf = seatsOf;
    this.marketMoney = this.marketSeats * INITIAL_MONEY;

    // SECSY でも市場の手持ちは PICSY と同額にして、比較が公平になるようにする
    var rich = {};
    rich[this.marketIndex] = this.marketMoney;
    var n = this.players.length;
    this.currency = (this.mode === 'picsy')
      ? new PicsyCurrency(seatsOf, this.gamma)
      : new SecsyCurrency(n, rich);
    // PICSY のときは、同じ取引を通常の決済貨幣でしたらどうなるかを影で記録する
    // (図3.9「PICSY効果なし」のランキング)
    this.shadow = (this.mode === 'picsy') ? new SecsyCurrency(n, rich) : null;
  }

  Game.prototype = {
    money: function (i) { return this.currency.money(i); },
    priceOf: function (name) { return this.prices[productByName(name).name]; },

    indexOf: function (name) {
      for (var i = 0; i < this.players.length; i++) {
        if (this.players[i].name === name) return i;
      }
      throw new Error('「' + name + '」という参加者はいません');
    },

    ranking: function (currency) {
      var source = currency || this.currency;
      var rows = [];
      for (var i = 0; i < this.players.length; i++) {
        if (!this.players[i].isMarket) rows.push({ player: this.players[i], money: source.money(i) });
      }
      rows.sort(function (a, b) { return b.money - a.money; });
      return rows;
    },

    setPrice: function (name, price) {
      if (!(price > 0)) throw new Error('価格は正の数を指定してください');
      var product = productByName(name);
      var before = this.prices[product.name];
      this.prices[product.name] = price;
      this.record('市場価格を変更: ' + product.name + ' ' + before + 'ドル → ' + price + 'ドル');
    },

    // 次の自然回収まであと何回の取引か(手動のみなら null)
    untilRecovery: function () {
      if (!this.recoveryEvery) return null;
      return this.recoveryEvery - (this.trades % this.recoveryEvery);
    },

    // ------------------------------------------------------------
    // 取引
    // ------------------------------------------------------------

    // 国どうしの支払い。何を売り買いしたかは memo に書くだけで、
    // 持ち物の検査はしない(モノは机の上にある)。
    trade: function (buyer, seller, price, memo) {
      if (buyer === seller) throw new Error('自分自身とは取引できません');
      if (!(price > 0)) throw new Error('金額は正の数を指定してください');
      if (!this.currency.canPay(buyer, price)) {
        throw new Error(this.players[buyer].name + 'のお金が足りません(いま '
          + Math.round(this.money(buyer)).toLocaleString('ja-JP') + 'ドル)');
      }

      var before = this.snapshotMoney();
      this.settle(buyer, seller, price);
      var text = this.players[buyer].name + ' が ' + this.players[seller].name
        + ' に ' + Math.round(price).toLocaleString('ja-JP') + 'ドル払った';
      if (memo) text += '(' + memo + ')';
      var recovered = this.finish(text);
      this.lastEffect = this.effectSince(before);
      return recovered;
    },

    // 市場が財を買い取る。価格は市場価格で決まっている。
    buyFromMarket: function (country, name, amount) {
      amount = Math.max(1, Math.round(amount || 1));
      var product = productByName(name);
      if (this.players[country].isMarket) throw new Error('市場は市場に売れません');

      var total = this.priceOf(product.name) * amount;
      if (this.marketUnlimited && this.currency.kind === 'picsy') {
        this.currency.ensureBudget(this.marketIndex, total);
      }
      if (!this.currency.canPay(this.marketIndex, total)) {
        throw new Error('市場の購買力が足りません。市場の初期資金を増やすか、自然回収を起こしてください');
      }

      var before = this.snapshotMoney();
      this.settle(this.marketIndex, country, total);
      this.bought[product.name] = (this.bought[product.name] || 0) + amount;
      var recovered = this.finish('市場 が ' + this.players[country].name + ' から '
        + product.name + '×' + amount + ' を '
        + Math.round(total).toLocaleString('ja-JP') + 'ドルで買い取った');
      this.lastEffect = this.effectSince(before);
      return { total: total, recovered: recovered };
    },

    // 手で自然回収を起こす(説明のとき用)
    runRecovery: function () {
      var before = this.snapshotMoney();
      this.currency.endOfDay();
      this.record('自然回収を起こした');
      this.lastEffect = this.effectSince(before);
    },

    // ------------------------------------------------------------
    // 内部
    // ------------------------------------------------------------
    settle: function (buyer, seller, price) {
      this.currency.pay(buyer, seller, price);
      if (this.shadow) this.shadow.pay(buyer, seller, price, true);
    },

    finish: function (text) {
      this.trades += 1;
      this.record(text);
      return this.maybeRecover();
    },

    // 本文では自然回収は「1日に1回とか1時間に1回といった頻度で自動的に
    // 行われる」(4.4.2項)。ワークショップに「日」はないので、
    // 取引の回数を時計のかわりにして自動で起こす。
    maybeRecover: function () {
      if (!this.recoveryEvery) return false;
      if (this.trades % this.recoveryEvery !== 0) return false;
      this.currency.endOfDay();
      this.record('自然回収(取引' + this.recoveryEvery + '回ごと)');
      return true;
    },

    snapshotMoney: function () {
      var before = [];
      for (var i = 0; i < this.players.length; i++) before.push(this.money(i));
      return before;
    },

    effectSince: function (before) {
      var effect = [];
      for (var i = 0; i < this.players.length; i++) {
        var delta = this.money(i) - before[i];
        if (Math.abs(delta) >= 0.5) effect.push({ index: i, name: this.players[i].name, delta: delta });
      }
      effect.sort(function (a, b) { return b.delta - a.delta; });
      return effect;
    },

    record: function (text) {
      this.log.push({ no: this.trades, text: text });
      if (this.log.length > 400) this.log.shift();
    },

    // ------------------------------------------------------------
    // 保存と復元
    // ------------------------------------------------------------
    settings: function () {
      return {
        mode: this.mode,
        gamma: this.gamma,
        marketSeats: this.marketSeats,
        marketUnlimited: this.marketUnlimited,
        recoveryEvery: this.recoveryEvery,
        countries: this.countries.map(function (t) {
          return { name: t.name, kind: t.kind, items: Object.assign({}, t.items) };
        })
      };
    },

    toJSON: function () {
      var data = {
        version: 3,
        settings: this.settings(),
        trades: this.trades,
        prices: this.prices,
        bought: this.bought,
        log: this.log,
        lastEffect: this.lastEffect
      };
      if (this.currency.kind === 'picsy') {
        data.matrix = this.currency.ledger.e.map(function (row) { return Array.prototype.slice.call(row); });
        data.shadow = this.shadow.balance.slice();
      } else {
        data.balance = this.currency.balance.slice();
      }
      return data;
    }
  };

  Game.fromJSON = function (data) {
    if (!data || data.version !== 3) return null;
    var game = new Game(data.settings);
    game.trades = data.trades || 0;
    game.prices = data.prices;
    game.bought = data.bought || {};
    game.log = data.log || [];
    game.lastEffect = data.lastEffect || [];
    if (game.currency.kind === 'picsy') {
      data.matrix.forEach(function (row, i) { game.currency.ledger.e[i] = Float64Array.from(row); });
      game.currency.ledger._c = null;
      game.shadow.balance = data.shadow.slice();
    } else {
      game.currency.balance = data.balance.slice();
    }
    return game;
  };

  global.PICSY = {
    CENTRAL_BANK: CENTRAL_BANK,
    INITIAL_MONEY: INITIAL_MONEY,
    PAPER: PAPER,
    TOOLS: TOOLS,
    PRODUCTS: PRODUCTS,
    COUNTRY_TEMPLATES: COUNTRY_TEMPLATES,
    defaultSettings: defaultSettings,
    initEvalMatrix: initEvalMatrix,
    contributionVector: contributionVector,
    PicsyLedger: PicsyLedger,
    PicsyCurrency: PicsyCurrency,
    SecsyCurrency: SecsyCurrency,
    Game: Game
  };
})(typeof window !== 'undefined' ? window : globalThis);
