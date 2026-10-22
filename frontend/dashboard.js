/* 仪表盘 */
App.page({
  id: 'dashboard', t: '仪表盘',
  async render() {
    const p = App.S.period;
    const d = await App.GET('/board', { period: p });
    const k = d.kpi;
    const n = App.num, m = App.money;

    const kpis = [
      ['综合能耗', n(k.tce, 2), 'tce', '', k.tceRate == null ? '—' : `环比 ${App.pct(k.tceRate)}`,
        k.tceRate > 0 ? 'w' : 'o'],
      ['碳排放', n(k.co2, 2), 'tCO₂', 'p', `范围一 ${n(k.scope1, 2)} · 范围二 ${n(k.scope2, 2)}`, 'p'],
      ['单位产品能耗', App.q6(k.unitEnergy), 'tce/单位', 'i', `产量 ${n(k.qty)}`, 'i'],
      ['单位产值能耗', App.q6(k.valueEnergy), 'tce/万元', '', `产值 ${n(k.valueWan, 2)} 万元`, ''],
      ['最大需量', n(k.maxDemand, 1), 'kW', (k.maxDemand / (k.capacityKw || 1)) > 0.9 ? 'b' : 'w',
        `容量 ${n(k.capacityKw)} kW · 负荷率 ${App.pct(k.maxDemand / (k.capacityKw || 1))}`, 'w'],
      ['本期电量', App.wan(k.elecQty), 'kWh', 'i', `折标煤 ${n(k.elecTce, 2)} tce`, 'i'],
      ['待处置告警', n(k.alarms['未处置']), '条', 'b',
        `紧急 ${k.alarms['紧急']} · 严重 ${k.alarms['严重']} · 警告 ${k.alarms['警告']}`, 'b'],
      ['预算执行率', App.pct(k.budget.rate), '', k.budget.status === '正常' ? 'o' : 'w',
        `预算 ${App.wan(k.budget.budget)} 元 · ${k.budget.status}`, k.budget.status === '正常' ? 'o' : 'w'],
    ];

    let h = '<div class="grid g4">' + kpis.map(x => `
      <div class="card kpi ${x[5]}">
        <div class="k">${x[0]}</div>
        <div class="v">${x[1]}<small>${x[2]}</small></div>
        <div class="d">${x[4]}</div>
      </div>`).join('') + '</div>';

    /* 趋势 */
    const yoy = await App.GET('/analysis/yoy', { period: p, months: 6 });
    h += '<div class="ptitle"><span class="bar"></span>近 6 期能耗趋势<span class="r">单位：tce</span></div>';
    h += `<div class="grid g2">
      <div class="card">${App.lineChart(yoy.list.map(x => ({ k: x.period, v: x.tce })), { labels: true, h: 46 })}
        <div class="lg"><span><i style="background:#1fa3a5"></i>综合能耗</span></div></div>
      <div class="card">
        ${App.table([
          { t: '期间', k: 'period' },
          { t: '综合能耗(tce)', r: 1, f: r => App.num(r.tce, 2) },
          { t: '环比', r: 1, f: r => r.mom == null ? '—' : `<span class="${r.mom > 0 ? 'up' : 'down'}">${App.pct(r.mom)}</span>` },
          { t: '单位产品能耗', r: 1, f: r => App.q6(r.unitEnergy) },
          { t: '碳排(tCO₂)', r: 1, f: r => App.num(r.co2, 2) },
        ], yoy.list.slice().reverse())}
      </div></div>`;

    /* 能源结构 + 中心排名 */
    const rank = await App.GET('/analysis/rank', { period: p });
    h += '<div class="ptitle"><span class="bar"></span>能源结构与中心排名</div>';
    h += `<div class="grid g2">
      <div class="card"><div class="k" style="margin-bottom:14px;color:#6b8299;font-size:12.5px">能源介质折标煤构成</div>
        ${App.donut(d.byEnergy.map(x => ({ k: x.name, v: x.tce, label: App.num(x.tce, 1) + ' tce' })))}
      </div>
      <div class="card"><div class="k" style="margin-bottom:14px;color:#6b8299;font-size:12.5px">成本中心能耗排名（tce）</div>
        ${App.bars(rank.list.slice(0, 8).map(x => ({ k: x.centerName, v: x.tce, label: App.num(x.tce, 1) })))}
      </div></div>`;

    /* 单耗超标 */
    h += '<div class="ptitle"><span class="bar"></span>单耗偏离基线（超 8% 重点提示）</div>';
    if (d.overLines.length) {
      h += App.table([
        { t: '产线', k: 'line' },
        { t: '本期单耗(tce/单位)', r: 1, f: r => App.q6(r.unitEnergy) },
        { t: '基线', r: 1, f: r => App.q6(r.base) },
        { t: '偏差', r: 1, f: r => `<span class="up">${App.dev(r.dev)}</span>` },
        { t: '级别', f: r => App.stTag(r.level) },
      ], d.overLines);
    } else {
      h += '<div class="note">本期各产线单耗均在基线 8% 以内，运行平稳。</div>';
    }

    h += `<div class="note"><b>口径</b>：综合能耗按介质折标煤系数汇总；单位产品能耗 = 综合能耗 ÷ 合格产量；单位产值能耗 = 综合能耗 ÷ 工业总产值（万元）。本期数据来源 ${App.num(d.kpi.qty)} 单位产出、${App.wan(d.kpi.elecQty)} kWh 电量。</div>`;
    return h;
  }
});
