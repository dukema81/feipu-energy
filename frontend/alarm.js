/* 告警中心 */
App.page({
  id: 'alarm', t: '告警中心',
  async render() {
    const d = await App.GET('/alarms', { period: '' });
    const sum = await App.GET('/alarms/summary');
    const canWrite = App.hasPerm('alarm.write');
    window.__alarms = d.list;
    const s = sum.summary;

    let h = `<div class="grid g5">
      <div class="card kpi b"><div class="k">紧急</div><div class="v">${s['紧急']}</div></div>
      <div class="card kpi w"><div class="k">严重</div><div class="v">${s['严重']}</div></div>
      <div class="card kpi i"><div class="k">警告</div><div class="v">${s['警告']}</div></div>
      <div class="card kpi"><div class="k">提示</div><div class="v">${s['提示']}</div></div>
      <div class="card kpi ${s['未处置'] ? 'w' : 'o'}"><div class="k">待处置</div><div class="v">${s['未处置']}<small>/ ${s['合计']}</small></div></div>
    </div>`;

    h += `<div class="bar-actions" style="margin-top:16px">
      <select id="fLevel" onchange="Alarm.filter()"><option value="">全部级别</option><option>紧急</option><option>严重</option><option>警告</option><option>提示</option></select>
      <select id="fStatus" onchange="Alarm.filter()"><option value="">全部状态</option><option>待处置</option><option>已处置</option></select>
      <select id="fType" onchange="Alarm.filter()"><option value="">全部类型</option>${sum.byType.map(x => `<option>${App.esc(x.type)}</option>`).join('')}</select>
      <span style="margin-left:auto;font-size:12.5px;color:#6b8299">按级别与时间排序，紧急在前</span>
    </div>`;

    h += '<div id="alarmTable">' + Alarm.table(d.list) + '</div>';

    h += '<div class="ptitle"><span class="bar"></span>告警类型分布</div>';
    h += `<div class="grid g2">
      <div class="card">${App.bars(sum.byType.map(x => ({ k: x.type, v: x.count, label: x.count + ' 条' })))}</div>
      <div class="card">${App.table([
        { t: '期间', k: 'period' },
        { t: '告警数', r: 1, f: r => r.c },
        { t: '趋势', f: r => `<div class="pbar" style="width:120px"><i style="width:${Math.max(4, Math.min(r.c / 12 * 100, 100))}%"></i></div>` },
      ], sum.byPeriod)}</div></div>`;

    h += `<div class="note"><b>分级与触发</b>：需量 ≥ 容量 95% 或单耗超基线 30% → 紧急；需量 ≥ 85% 或单耗超 15% → 严重；
      单耗超 8% 或抄表跳变 → 警告；抄表逾期、能效劣化 → 提示。同一告警不可重复处置（409），处置留痕到审计日志。</div>`;
    return h;
  }
});

const Alarm = {
  table(rows) {
    const canWrite = App.hasPerm('alarm.write');
    return App.table([
      { t: '告警号', k: 'no' },
      { t: '级别', f: r => App.stTag(r.level) },
      { t: '类型', f: r => App.tag(r.atype, 't') },
      { t: '对象', k: 'target' },
      { t: '内容', f: r => App.esc(r.message) },
      { t: '当前值', r: 1, f: r => App.num(r.value, 2) },
      { t: '阈值', r: 1, f: r => App.num(r.threshold, 2) },
      { t: '期间', k: 'period' },
      { t: '状态', f: r => App.stTag(r.status) },
      { t: '处置人', f: r => r.handled_by || '—' },
      ...(canWrite ? [{ t: '操作', c: 1, f: r => r.status === '已处置' ? '—' : `<button class="btn sm pri" onclick="Alarm.handle('${r.no}')">处置</button>` }] : []),
    ], rows, { scroll: true });
  },
  filter() {
    const lv = document.getElementById('fLevel').value;
    const st = document.getElementById('fStatus').value;
    const tp = document.getElementById('fType').value;
    const rows = (window.__alarms || []).filter(x =>
      (!lv || x.level === lv) && (!st || x.status === st) && (!tp || x.atype === tp));
    document.getElementById('alarmTable').innerHTML = Alarm.table(rows);
  },
  handle(no) {
    App.modal('处置告警 · ' + no, `
      <div class="frow one"><div class="f"><label>处置说明</label>
        <textarea id="h_remark" placeholder="填写原因分析、处理措施与验证结果"></textarea></div></div>
      <div class="note">处置后状态变为「已处置」，处置人与时间写入审计日志，不可撤销。</div>`,
      `<button class="btn" onclick="App.closeModal()">取消</button>
       <button class="btn pri" onclick="Alarm.doHandle('${no}')">确认处置</button>`);
  },
  async doHandle(no) {
    const remark = document.getElementById('h_remark').value;
    if (!remark.trim()) return App.err('请填写处置说明');
    try {
      await App.POST('/alarms/' + no + '/handle', { remark });
      App.closeModal(); App.ok('已处置'); App.route();
    } catch (e) { App.err(e.message); }
  },
};
