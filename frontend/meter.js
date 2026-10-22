/* 抄表与采集 / 分时与需量 */

/* ---------- 抄表 ---------- */
App.page({
  id: 'reading', t: '抄表与采集',
  async render() {
    const p = App.S.period;
    const [rd, ck] = await Promise.all([
      App.GET('/readings', { period: p }),
      App.GET('/readings/check', { period: p }).catch(() => null),
    ]);
    window.__readings = rd.list;
    const canWrite = App.hasPerm('read.write');

    let h = '<div class="grid g4">'
      + `<div class="card kpi"><div class="k">本期抄表记录</div><div class="v">${rd.count}<small>条</small></div><div class="d">期间 ${p}</div></div>`
      + (ck ? `<div class="card kpi ${ck.coverage >= 1 ? 'o' : 'w'}"><div class="k">抄表覆盖率</div><div class="v">${App.pct(ck.coverage)}</div><div class="d">${ck.metersReported} / ${ck.metersTotal} 个计量点</div></div>
        <div class="card kpi ${ck.estimate.length ? 'w' : 'o'}"><div class="k">估算值</div><div class="v">${ck.estimate.length}<small>条</small></div><div class="d">缺口补值，需核实</div></div>
        <div class="card kpi ${ck.jump.length ? 'b' : 'o'}"><div class="k">量级跳变</div><div class="v">${ck.jump.length}<small>条</small></div><div class="d">环比超 3 倍</div></div>` : '')
      + '</div>';

    h += `<div class="bar-actions" style="margin-top:16px">
      ${canWrite ? '<button class="btn pri" onclick="Reading.add()">+ 手工抄表</button><button class="btn" onclick="Reading.batch()">批量抄表</button><button class="btn" onclick="Reading.report()">网关上报模拟</button>' : ''}
      <button class="btn" style="margin-left:auto" onclick="Reading.exportCsv()">导出 CSV</button>
    </div>`;

    if (ck && (ck.missing.length || ck.estimate.length || ck.jump.length)) {
      h += '<div class="ptitle"><span class="bar"></span>数据质量提示</div>';
      h += '<div class="grid g3">';
      if (ck.missing.length) h += `<div class="card"><div class="k" style="color:#6b8299;font-size:12.5px;margin-bottom:8px">未抄表 (${ck.missing.length})</div>${ck.missing.slice(0, 6).map(x => `<div style="font-size:12.5px;padding:3px 0">${x.meter} ${App.esc(x.name)}</div>`).join('')}</div>`;
      if (ck.estimate.length) h += `<div class="card"><div class="k" style="color:#6b8299;font-size:12.5px;margin-bottom:8px">估算值 (${ck.estimate.length})</div>${ck.estimate.slice(0, 6).map(x => `<div style="font-size:12.5px;padding:3px 0">${x.meter} ${App.esc(x.name)} · ${App.num(x.usage, 1)}</div>`).join('')}</div>`;
      if (ck.jump.length) h += `<div class="card"><div class="k" style="color:#6b8299;font-size:12.5px;margin-bottom:8px">量级跳变 (${ck.jump.length})</div>${ck.jump.slice(0, 6).map(x => `<div style="font-size:12.5px;padding:3px 0">${x.meter} ${App.esc(x.name)} · ${App.num(x.usage, 1)}</div>`).join('')}</div>`;
      h += '</div>';
    }

    h += '<div class="ptitle"><span class="bar"></span>抄表明细</div>';
    h += App.table([
      { t: '期间', k: 'period' },
      { t: '计量点', f: r => `<b>${r.meter_code}</b> ${App.esc(r.meterName || '')}` },
      { t: '介质', k: 'energyName' },
      { t: '中心', f: r => (r.center || '') + ' ' + (r.centerName || '') },
      { t: '抄表日期', k: 'date' },
      { t: '表底', r: 1, f: r => App.num(r.reading, 1) },
      { t: '用量', r: 1, f: r => App.num(r.usage, 1) },
      { t: '单位', k: 'unit' },
      { t: '质量', f: r => App.stTag(r.quality) },
      { t: '来源', f: r => App.tag(r.source, r.source === '网关' ? 't' : 'g') },
    ], rd.list, { scroll: true });

    h += `<div class="note"><b>校验规则</b>：表底小于上期 → 拒绝（409，表底倒走）；同计量点同期间已有读数 → 拒绝（409，区间重叠）；
      用量环比放大/缩小超 3 倍且绝对量过百 → 允许入库但标记「跳变」并自动生成告警。用量 =（本期表底 − 上期表底）× 倍率。</div>`;
    return h;
  }
});

const Reading = {
  add() {
    App.modal('手工抄表', `
      <div class="frow">
        <div class="f"><label>计量点 *</label><input id="r_meter" placeholder="如 EM101"></div>
        <div class="f"><label>期间</label><input id="r_period" value="${App.S.period}"></div>
        <div class="f"><label>抄表日期</label><input id="r_date" value="${App.S.period}-28"></div>
        <div class="f"><label>本期表底 *</label><input id="r_reading" type="number" step="0.1"></div>
        <div class="f"><label>是否估算</label><select id="r_est"><option value="">否</option><option value="1">是（缺口补值）</option></select></div>
      </div>
      <div class="note" style="margin-top:14px">提交后系统自动按「（本期 − 上期）× 倍率」计算用量，并做倒走与跳变校验。</div>`,
      `<button class="btn" onclick="App.closeModal()">取消</button>
       <button class="btn pri" onclick="Reading.save()">提交</button>`);
  },
  async save() {
    const b = {
      meter: document.getElementById('r_meter').value.trim().toUpperCase(),
      period: document.getElementById('r_period').value,
      date: document.getElementById('r_date').value,
      reading: Number(document.getElementById('r_reading').value),
      isEstimate: !!document.getElementById('r_est').value,
    };
    if (!b.meter) return App.err('请填写计量点');
    try {
      const r = await App.POST('/readings', b);
      App.closeModal();
      if (r.jump) App.err(`已入库但触发跳变告警 ${r.alarm}`);
      else App.ok(`抄表成功，用量 ${App.num(r.usage, 1)}`);
      App.route();
    } catch (e) { App.err(e.message); }
  },
  batch() {
    App.modal('批量抄表', `
      <div class="frow one">
        <div class="f"><label>期间</label><input id="b_period" value="${App.S.period}"></div>
        <div class="f"><label>录入格式：计量点,表底（每行一条）</label>
          <textarea id="b_items" rows="8" placeholder="EM101,158420.5&#10;EM102,162300.0&#10;WM101,3420.8"></textarea></div>
      </div>
      <div class="note">逐条独立校验，失败条目会返回具体原因，不影响其他条目入库。</div>`,
      `<button class="btn" onclick="App.closeModal()">取消</button>
       <button class="btn pri" onclick="Reading.doBatch()">提交</button>`);
  },
  async doBatch() {
    const period = document.getElementById('b_period').value;
    const lines = document.getElementById('b_items').value.split('\n').map(s => s.trim()).filter(Boolean);
    const items = lines.map(l => {
      const [m, v] = l.split(/[,，\t]/);
      return { meter: (m || '').trim().toUpperCase(), reading: Number(v) };
    }).filter(x => x.meter);
    if (!items.length) return App.err('请填写抄表数据');
    try {
      const r = await App.POST('/readings/batch', { period, items });
      const fails = r.items.filter(x => !x.ok);
      App.closeModal();
      if (fails.length) {
        App.modal('批量抄表结果', `<div class="note">成功 ${r.success} 条，失败 ${r.failed} 条</div>` +
          App.table([
            { t: '计量点', k: 'meter' },
            { t: '结果', f: x => x.ok ? App.tag('成功', 'ok') : App.tag('失败', 'b') },
            { t: '用量 / 原因', f: x => x.ok ? App.num(x.usage, 1) : App.esc(x.error) },
          ], r.items), null, true);
      } else {
        App.ok(`全部成功，共 ${r.success} 条`);
      }
      App.route();
    } catch (e) { App.err(e.message); }
  },
  report() {
    App.modal('采集网关上报模拟', `
      <div class="note">模拟采集网关调用 <code>POST /api/readings/report</code>，按时间戳自动推导期间。</div>
      <div class="frow">
        <div class="f"><label>计量点</label><input id="g_meter" value="EM101"></div>
        <div class="f"><label>时间戳</label><input id="g_ts" value="${App.S.period}-22 10:15:00"></div>
        <div class="f"><label>表底值</label><input id="g_value" type="number" step="0.1"></div>
        <div class="f"><label>质量标记</label><select id="g_q"><option value="">自动</option><option>正常</option><option>估算</option></select></div>
      </div>`,
      `<button class="btn" onclick="App.closeModal()">取消</button>
       <button class="btn pri" onclick="Reading.doReport()">上报</button>`);
  },
  async doReport() {
    const b = {
      meter: document.getElementById('g_meter').value.trim().toUpperCase(),
      ts: document.getElementById('g_ts').value,
      value: Number(document.getElementById('g_value').value),
      quality: document.getElementById('g_q').value || undefined,
    };
    try {
      const r = await App.POST('/readings/report', b);
      App.closeModal();
      App.ok(`上报成功，用量 ${App.num(r.usage, 1)}（质量 ${r.quality}）`);
      App.route();
    } catch (e) { App.err(e.message); }
  },
  exportCsv() { App.exportCsv('consumption'); },
};

/* ---------- 分时与需量 ---------- */
App.page({
  id: 'tou', t: '分时与需量',
  async render() {
    const p = App.S.period;
    const [tou, dm] = await Promise.all([
      App.GET('/tou-summary', {}),
      App.GET('/demands/summary', { period: p }),
    ]);
    const s = tou.summary;
    const k = ['尖峰', '峰', '平', '谷'];

    let h = `<div class="grid g4">
      <div class="card kpi"><div class="k">本期总电量</div><div class="v">${App.wan(s.kwhTotal)}<small>kWh</small></div><div class="d">${tou.from} ~ ${tou.to}</div></div>
      <div class="card kpi o"><div class="k">分时电费</div><div class="v">${App.wan(s.energyFee)}<small>元</small></div><div class="d">均价 ${App.num(s.avgPrice, 4)} 元/kWh</div></div>
      <div class="card kpi ${dm.status.status === '正常' ? 'o' : 'b'}"><div class="k">最大需量</div><div class="v">${App.num(dm.maxDemand.demandKw, 1)}<small>kW</small></div><div class="d">容量 ${App.num(dm.capacityKw)} kW · ${dm.status.status}</div></div>
      <div class="card kpi w"><div class="k">容量电费</div><div class="v">${App.wan(dm.capacityFee.chosen)}<small>元</small></div><div class="d">${dm.capacityFee.mode}计费 · 超容 ${dm.overCount} 次</div></div>
    </div>`;

    h += '<div class="ptitle"><span class="bar"></span>分时电量与电费</div>';
    h += `<div class="grid g2">
      <div class="card">${App.donut(k.map(x => ({ k: x + ' 时段', v: s.byPeriod[x].kwh, label: App.wan(s.byPeriod[x].kwh) + ' kWh' })))}</div>
      <div class="card">${App.table([
        { t: '时段', k: 'p' },
        { t: '电量(kWh)', r: 1, f: r => App.num(r.kwh, 1) },
        { t: '电价(元)', r: 1, f: r => App.num(r.price, 4) },
        { t: '电费(元)', r: 1, f: r => App.money(r.amount) },
        { t: '占比', r: 1, f: r => App.pct(r.kwh / (s.kwhTotal || 1)) },
      ], k.map(x => ({ p: x, ...s.byPeriod[x] })))}
      <div class="note" style="margin:10px 0 0">合计 ${App.money(s.energyFee)} 元，校验差 ${App.money(s.checkDiff)}（应为 0）。</div></div>
    </div>`;

    h += '<div class="ptitle"><span class="bar"></span>日电量与电费走势</div>';
    h += `<div class="card">${App.lineChart(tou.daily.slice(-30).map(x => ({ k: x.date.slice(5), v: x.kwh })), { labels: true, h: 44 })}
      <div class="lg"><span><i style="background:#1fa3a5"></i>日电量 kWh</span></div></div>`;

    h += '<div class="ptitle"><span class="bar"></span>24 小时需量曲线（取各小时峰值）</div>';
    h += `<div class="card">${App.lineChart(dm.curve.map(x => ({ k: x.hour + ':00', v: x.demandKw })), { labels: true, h: 44, color: dm.status.status === '正常' ? '#12787a' : '#dc2626' })}
      <div class="lg"><span><i style="background:#12787a"></i>需量 kW</span><span>容量 ${App.num(dm.capacityKw)} kW</span><span>峰值发生于 ${dm.maxDemand.ts || '—'}</span></div></div>`;

    h += `<div class="note"><b>需量口径</b>：15 分钟需量 = 15 分钟内电能增量 ÷ 0.25 h；仅有小时电量时按小时电量近似（标记为近似口径）。
      容量电费 = 最大需量 × 需量单价（当前规则 ${App.num(42)} 元/kW·月）。需量 ≥ 容量 85% 预警、≥95% 紧急、>100% 超容并自动生成告警。</div>`;
    return h;
  }
});
