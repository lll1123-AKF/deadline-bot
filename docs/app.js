/* DeadlineBot 交互演示
 * 用 JavaScript 复刻 Python 版的核心逻辑（多任务拆分 / 日期解析 / 内容排序 / 进度），
 * 便于在浏览器里直接体验。完整实现见仓库 deadline_bot/ 目录。
 */

const STORAGE_KEY = 'deadlinebot.tasks.v2';
const WEEKDAYS = { '一': 0, '二': 1, '三': 2, '四': 3, '五': 4, '六': 5, '日': 6, '天': 6 };
const CATEGORY_LEAD = { '考试': 3, '作业': 1.5, '资料提交': 1, '审批': 1, '汇报': .5, '会议': 0, '其他': .5 };
const PRIORITY_W = { high: 3, normal: 1.5, low: 0 };

const SAMPLES = [
  '教务处通知：2026年11月30日前提交本学期选课确认表，逾期视为放弃。',
  '班主任通知：本周五下午5点前交社会实践报告，请班长统一收齐。',
  '学院通知：下周一上午9点在报告厅参加AI创新讲座，全体同学务必到场。',
  '学生处提醒：12月5日前完成宿舍安全承诺书签订。',
  'HR通知：明天下午6点前提交本月工作总结，邮件发送至hr@company.com。',
  '财务部通知：3天内报销本季度差旅费用，逾期不予受理。',
  '项目组通知：下周三前完成需求评审文档的填写和提交。',
  '行政部提醒：12月10日前完成年度体检预约，可选就近网点。'
];

const CATEGORY_KW = [
  ['作业', ['作业', '习题', '论文', '小测']],
  ['考试', ['考试', '测验', '月考', '期末', 'quiz']],
  ['资料提交', ['提交', '上交', '材料', '资料', '表格', '申请表', '报名', '登记表', '报告']],
  ['会议', ['会议', '开会', '例会', '培训', '讲座', '班会']],
  ['审批', ['审批', '报销', '申请', '盖章', '签字']],
  ['汇报', ['周报', '日报', '月报', '报表', '汇报', '总结']]
];

/* ---------- 多任务拆分 ---------- */

function splitNotices(text) {
  const cleaned = (text || '').trim();
  if (!cleaned) return [];
  // 与 Python 端 _ITEM_MARKER 保持一致：编号可跟在行首 / 分号 / 逗号 / 顿号 / 冒号后。
  // (?!\d) 防止把「12:30」误认成编号。
  const re = /(?:^|[\n;；，,、:：])\s*(?:\d{1,2}\s*[.、．)）:：](?!\d)|[一二三四五六七八九十]{1,3}\s*[、.．]|[（(]\s*\d{1,2}\s*[)）])\s*/g;
  const markers = [];
  let m;
  while ((m = re.exec(cleaned))) markers.push({ start: m.index, end: m.index + m[0].length });
  if (markers.length >= 2) {
    const items = [];
    for (let i = 0; i < markers.length; i++) {
      const end = i + 1 < markers.length ? markers[i + 1].start : cleaned.length;
      const chunk = cleaned.slice(markers[i].end, end).replace(/^[ \n\t;；，,]+|[ \n\t;；，,]+$/g, '');
      if (chunk) items.push(chunk);
    }
    if (items.length) return items;
  }
  const lines = cleaned.split('\n')
    .map(s => s.replace(/^[ \t;；，,]+|[ \t;；，,]+$/g, '')).filter(Boolean);
  const hint = /交|提交|完成|参加|报销|填写|截止|前|月|日|周/;
  if (lines.length >= 2 && lines.filter(s => hint.test(s)).length >= 2) {
    if (lines[0].length <= 8 && /^(注意|通知|提醒|各位同学|各位同事)[：:]?$/.test(lines[0])) lines.shift();
    return lines.length ? lines : [cleaned];
  }
  return [cleaned];
}

/* ---------- 日期解析 ---------- */

function parseDue(text, now) {
  const candidates = [];
  const push = (date, raw, p) => { if (date && !isNaN(date.getTime())) candidates.push({ date, raw, p }); };
  const at = (d, h, m) => new Date(d.getFullYear(), d.getMonth(), d.getDate(), h, m, 0, 0);

  function clock(day, tail, defHour = 23, defMinute = 59) {
    let h = defHour, m = defMinute;
    if (/下班前/.test(tail)) { h = 18; m = 0; }
    else if (/中午/.test(tail)) { h = 12; m = 0; }
    let cm = tail.match(/(\d{1,2})\s*[:：]\s*(\d{2})/);
    if (cm) { h = +cm[1]; m = +cm[2]; }
    else {
      cm = tail.match(/(\d{1,2})\s*[点时]/);
      if (cm) { h = +cm[1]; m = 0; const mm = tail.match(/[点时]\s*(\d{1,2})\s*分/); if (mm) m = +mm[1]; }
    }
    if (/下午|晚上|傍晚/.test(tail) && h < 12) h += 12;
    return at(day, Math.min(h, 23), Math.min(m, 59));
  }

  let m;
  const reFull = /(20\d{2})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*日?/g;
  while ((m = reFull.exec(text))) {
    const d = new Date(+m[1], +m[2] - 1, +m[3]);
    push(clock(d, text.slice(m.index, m.index + m[0].length + 12)), m[0], 100);
  }
  const reMD = /(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日?(?!\d)/g;
  while ((m = reMD.exec(text))) {
    let d = new Date(now.getFullYear(), +m[1] - 1, +m[2]);
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    if (d < today) d = new Date(d.getFullYear() + 1, d.getMonth(), d.getDate());
    push(clock(d, text.slice(m.index, m.index + m[0].length + 12)), m[0], 90);
  }
  const rel = { '今天': 0, '当日': 0, '明天': 1, '明日': 1, '后天': 2, '大后天': 3 };
  for (const [w, off] of Object.entries(rel)) {
    let i = text.indexOf(w);
    while (i !== -1) {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + off);
      push(clock(d, text.slice(i, i + 18), 18, 0), w, 80);
      i = text.indexOf(w, i + 1);
    }
  }
  const reWeek = /(本|下|下下)?\s*(周|星期|礼拜)\s*([一二三四五六日天])/g;
  while ((m = reWeek.exec(text))) {
    const target = WEEKDAYS[m[3]];
    const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - ((now.getDay() + 6) % 7));
    const off = m[1] === '下下' ? 14 : m[1] === '下' ? 7 : 0;
    const d = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + target + off);
    push(clock(d, text.slice(m.index, m.index + m[0].length + 12), 18, 0), m[0], 70);
  }
  const reRel = /(\d+|[一二三四五六七八九十两])\s*(天|周|个?星期)\s*(内|后|之前?)/g;
  const cnNum = { '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10 };
  while ((m = reRel.exec(text))) {
    const n = /^\d+$/.test(m[1]) ? +m[1] : (cnNum[m[1]] || 1);
    const days = /周|星期/.test(m[2]) ? n * 7 : n;
    push(new Date(now.getTime() + days * 86400000), m[0], 60);
  }
  let i = text.search(/本?月底|月末/);
  if (i !== -1) {
    const d = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    push(clock(d, text.slice(i, i + 8)), text.slice(i, i + 2), 50);
  }

  if (!candidates.length) return { due: null, raw: '' };
  candidates.sort((a, b) => b.p - a.p || text.indexOf(a.raw) - text.indexOf(b.raw));
  return { due: candidates[0].date, raw: candidates[0].raw };
}

function cleanTitle(text, raw) {
  let s = raw ? text.replace(raw, ' ') : text;
  s = s.replace(/^\s*\d{1,2}\s*[.、．)）]\s*/, '');
  s = s.replace(/^[\u4e00-\u9fa5A-Za-z]{2,10}(通知|提醒|公告)\s*[:：]\s*/, '');
  s = s.replace(/^(各位同学|同学们|大家好|各位同事|【[^】]*】|注意)\s*[:：]?\s*/, ' ');
  s = s.replace(/(上午|下午|晚上|中午)?\s*\d{1,2}\s*[:点时]\s*\d{0,2}\s*分?(前|之前)?/g, ' ');
  s = s.replace(/第?\s*\d{1,2}\s*周(?:次)?/g, ' ');
  s = s.replace(/[（(]\s*[)）]/g, ' ');
  s = s.replace(/(?:截止)?\s*前\s*(?:交|提交|完成|上交|报送|上传|寄出)?\s*[;；，,。]?\s*$/, ' ');
  s = s.replace(/(?:交|提交|完成)\s*[;；，,。]?\s*$/, ' ');
  s = s.replace(/^\s*(交|提交|完成|上交)\s*/, '');
  s = s.replace(/\s+/g, ' ').replace(/^[ ，。；;：:、（）()]+|[ ，。；;：:、（）()]+$/g, '');
  return s.slice(0, 80) || '待处理通知';
}

function detectSource(t) {
  const m = t.match(/(教务处|学生处|班主任|辅导员|学院|学校|系里|班委|人力资源部|HR|人事部|行政部|财务部|部门|主管|领导|项目组)/);
  return m ? m[1] : '未知来源';
}
function detectCategory(t) {
  const s = t.replace('报告厅', '');
  for (const [cat, kws] of CATEGORY_KW) if (kws.some(k => s.includes(k))) return cat;
  return '其他';
}
function detectPriority(t) {
  if (/紧急|务必|重要|加急|立即/.test(t)) return 'high';
  if (/可选|自愿|建议/.test(t)) return 'low';
  return 'normal';
}

function parseNotice(text) {
  const { due, raw } = parseDue(text, new Date());
  return {
    id: 't_' + Math.random().toString(36).slice(2, 10),
    title: cleanTitle(text, raw),
    due: due ? due.getTime() : null,
    source: detectSource(text),
    category: detectCategory(text),
    priority: detectPriority(text),
    status: 'pending',
    progress: 0,
    notes: '',
    raw,
    rawNotice: text.trim(),
    created: Date.now()
  };
}

function parseNotices(text) {
  return splitNotices(text).map(parseNotice);
}

/* ---------- 排序打分 ---------- */

function workScore(t, now) {
  const remaining = t.due === null ? null : (t.due - now) / 86400000;
  const pw = PRIORITY_W[t.priority] ?? 1.5;
  const lead = CATEGORY_LEAD[t.category] ?? .5;
  let uw = 0;
  if (remaining !== null) {
    if (remaining < 0) uw = 10 + Math.min(-remaining, 10) * .1;
    else if (remaining < 1) uw = 8 - remaining * 2;
    else if (remaining < 3) uw = 6 - (remaining - 1);
    else if (remaining < 7) uw = 4 - (remaining - 3) * .5;
    else uw = Math.max(0, 2 - (remaining - 7) * .2);
  }
  const leadBonus = (remaining !== null && remaining >= 0 && remaining <= lead && lead > 0)
    ? (lead - remaining) / Math.max(lead, 1) : 0;
  const doing = t.status === 'in_progress' ? .5 : 0;
  const parts = ['优先级' + t.priority];
  if (lead > 0) parts.push(`${t.category}需提前${lead}天`);
  if (remaining !== null) parts.push('剩余' + remaining.toFixed(1) + '天');
  if (doing) parts.push('已开始');
  return { score: Math.round((pw + uw + leadBonus + doing) * 100) / 100, reason: parts.join('、') };
}

/* ---------- 状态 ---------- */

let tasks = [];
let view = 'plan';
let expanded = new Set();

function load() {
  try { tasks = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }
  catch (e) { tasks = []; }
}
function save() { localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks)); }
function fmt(ts) {
  if (ts === null || ts === undefined) return '无截止日';
  const d = new Date(ts);
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function daysLeft(t) { return t.due === null || t.due === undefined ? null : (t.due - Date.now()) / 86400000; }
function urgency(t) {
  const r = daysLeft(t);
  if (r === null) return 5;
  if (r < 0) return 0;
  if (r <= 1) return 1;
  if (r <= 3) return 2;
  if (r <= 7) return 3;
  return 4;
}
const LEVELS = [
  ['已逾期', 'overdue'], ['24 小时内', 'soon'], ['3 天内', 'soon'],
  ['7 天内', ''], ['7 天以上', ''], ['无截止日', '']
];
const STATUS_TEXT = { pending: '待开始', in_progress: '进行中', done: '已完成', cancelled: '已取消' };
const PRIORITY_TEXT = { high: '高', normal: '普通', low: '低' };

function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg; el.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove('show'), 1800);
}
function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* ---------- 渲染 ---------- */

function renderSummary() {
  const done = tasks.filter(t => t.status === 'done').length;
  const doing = tasks.filter(t => t.status === 'in_progress').length;
  const pending = tasks.filter(t => t.status === 'pending').length;
  const overdue = tasks.filter(t => t.status !== 'done' && (daysLeft(t) ?? 1) < 0).length;
  const rate = tasks.length ? Math.round(done / tasks.length * 100) : 0;
  document.getElementById('summaryBar').innerHTML = `
    <div class="stat"><div class="label">全部任务</div><div class="value">${tasks.length}</div></div>
    <div class="stat"><div class="label">已完成</div><div class="value">${done}</div></div>
    <div class="stat"><div class="label">进行中</div><div class="value">${doing}</div></div>
    <div class="stat"><div class="label">待开始</div><div class="value">${pending}</div></div>
    <div class="stat ${overdue ? 'alert' : ''}"><div class="label">已逾期</div><div class="value">${overdue}</div></div>
    <div class="stat"><div class="label">完成率</div><div class="value">${rate}%</div></div>`;
  document.getElementById('countLabel').textContent = `${tasks.length} 条任务`;
}

function taskCard(t, index, showReason) {
  const r = daysLeft(t);
  const { score, reason } = workScore(t, Date.now());
  const open = expanded.has(t.id);

  let dueClass = '', remainText;
  if (r === null) remainText = '无截止日';
  else if (r < 0) { dueClass = 'overdue'; remainText = `已逾期 ${Math.abs(r).toFixed(1)} 天`; }
  else if (r < 1) { dueClass = 'soon'; remainText = `还剩 ${(r * 24).toFixed(1)} 小时`; }
  else remainText = `还剩 ${r.toFixed(1)} 天`;

  const badge = t.status === 'done' ? '<span class="badge-done">已完成</span>'
    : t.status === 'in_progress' ? '<span class="badge-doing">进行中</span>' : '';
  const progressText = t.progress ? ` · 进度 ${t.progress}%` : '';

  const detail = open ? `
    <div class="task-detail">
      <div class="detail-grid">
        <div><span>来源</span>${escapeHtml(t.source)}</div>
        <div><span>类别</span>${escapeHtml(t.category)}</div>
        <div><span>优先级</span>${escapeHtml(PRIORITY_TEXT[t.priority] || t.priority)}</div>
        <div><span>状态</span>${escapeHtml(STATUS_TEXT[t.status] || t.status)}</div>
      </div>
      <div class="progress-line"><div class="bar"><i style="width:${t.progress}%"></i></div><span class="pct">${t.progress}%</span></div>
      ${showReason ? `<div class="reason">排序 ${score} · ${escapeHtml(reason)}</div>` : ''}
      <div class="raw-notice"><span>通知原文</span>${escapeHtml(t.rawNotice || t.title)}</div>
      ${t.notes ? `<div class="reason">备注：${escapeHtml(t.notes)}</div>` : ''}
      <div class="task-actions">
        <div class="mini-row">
          <button class="mini" data-act="start" data-id="${t.id}">开始</button>
          <button class="mini" data-act="progress" data-id="${t.id}">+20%</button>
          <button class="mini" data-act="finish" data-id="${t.id}">完成</button>
        </div>
        <div class="mini-row">
          <button class="mini" data-act="priority" data-id="${t.id}">改优先级</button>
          <button class="mini" data-act="due" data-id="${t.id}">改截止日</button>
          <button class="mini" data-act="note" data-id="${t.id}">备注</button>
          <button class="mini danger" data-act="delete" data-id="${t.id}">删除</button>
        </div>
      </div>
    </div>` : '';

  return `<div class="task ${t.status === 'done' ? 'done' : ''}">
    <div class="rank">${index}</div>
    <div class="task-main">
      <div class="task-headline">
        <div class="task-title">${escapeHtml(t.title)}</div>
        <div class="task-due ${dueClass}">${fmt(t.due)}</div>
        <button class="detail-toggle" data-act="toggle" data-id="${t.id}">${open ? '收起' : '详情'}</button>
      </div>
      <div class="task-sub">${remainText}${badge ? ' · ' + badge : ''}${progressText}</div>
      ${detail}
    </div>
  </div>`;
}

function render() {
  renderSummary();
  const area = document.getElementById('taskArea');
  const active = tasks.filter(t => t.status !== 'done' && t.status !== 'cancelled');
  const done = tasks.filter(t => t.status === 'done');

  if (!tasks.length) {
    area.innerHTML = '<div class="empty">还没有任务。粘贴一条通知开始。</div>';
    return;
  }

  let html = '';
  if (view === 'plan') {
    const ranked = active.slice().sort((a, b) => workScore(b, Date.now()).score - workScore(a, Date.now()).score || (a.due ?? Infinity) - (b.due ?? Infinity));
    html += '<div class="group-title">执行顺序</div>';
    html += ranked.map((t, i) => taskCard(t, i + 1, true)).join('') || '<div class="empty">没有待办任务了。</div>';
    if (done.length) html += `<div class="group-title">已完成（${done.length}）</div>` + done.map((t, i) => taskCard(t, i + 1, false)).join('');
  } else if (view === 'daily') {
    const doing = active.filter(t => t.status === 'in_progress');
    const pending = active.filter(t => t.status === 'pending');
    if (doing.length) html += `<div class="group-title">进行中（${doing.length}）</div>` + doing.map((t, i) => taskCard(t, i + 1, false)).join('');
    const focus = doing.concat(pending).sort((a, b) => workScore(b, Date.now()).score - workScore(a, Date.now()).score).slice(0, 5);
    html += '<div class="group-title">建议先做</div>' + focus.map((t, i) => taskCard(t, i + 1, true)).join('');
    if (done.length) html += `<div class="group-title">已完成（${done.length}）</div>` + done.map((t, i) => taskCard(t, i + 1, false)).join('');
  } else {
    const buckets = [[], [], [], [], [], []];
    active.forEach(t => buckets[urgency(t)].push(t));
    LEVELS.forEach(([label], i) => {
      if (!buckets[i].length) return;
      const sorted = buckets[i].sort((a, b) => (a.due ?? Infinity) - (b.due ?? Infinity));
      html += `<div class="group-title">${label}（${sorted.length}）</div>` + sorted.map((t, j) => taskCard(t, j + 1, false)).join('');
    });
    if (done.length) html += `<div class="group-title">已完成（${done.length}）</div>` + done.map((t, i) => taskCard(t, i + 1, false)).join('');
  }
  area.innerHTML = html;
}

/* ---------- 交互 ---------- */

function addNotice(text) {
  const parsed = parseNotices(text.trim());
  if (!parsed.length) return { ok: false, msg: '通知内容为空' };
  let added = 0, skipped = 0;
  parsed.forEach(t => {
    const dup = tasks.some(x => x.title === t.title && x.due === t.due);
    if (dup) { skipped++; return; }
    tasks.push(t); added++;
  });
  save(); render();
  // 反馈只报数量，长标题已显示在任务卡片里
  if (!added) return { ok: false, msg: '已存在相同任务，未重复添加' };
  return {
    ok: true,
    count: added,
    msg: parsed.length > 1
      ? `拆出 ${parsed.length} 项 · 新增 ${added}${skipped ? ` · 重复 ${skipped}` : ''}`
      : `已添加 · 截止 ${fmt(parsed[0].due)}`
  };
}

document.getElementById('addBtn').addEventListener('click', () => {
  const el = document.getElementById('noticeInput');
  const fb = document.getElementById('parseFeedback');
  if (!el.value.trim()) { fb.className = 'feedback err'; fb.textContent = '请先输入一条通知'; return; }
  const res = addNotice(el.value);
  fb.className = 'feedback ' + (res.ok ? 'ok' : 'err');
  fb.textContent = res.msg;
  if (res.ok) { el.value = ''; toast(res.count > 1 ? `添加了 ${res.count} 条任务` : '任务已添加'); }
});

document.getElementById('noticeInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) document.getElementById('addBtn').click();
});

document.getElementById('sampleBtn').addEventListener('click', () => {
  let added = 0;
  SAMPLES.forEach(s => { if (addNotice(s).ok) added++; });
  const fb = document.getElementById('parseFeedback');
  fb.className = 'feedback ok';
  fb.textContent = `已加载 ${added} 条示例`;
  toast(`加载了 ${added} 条`);
});

document.getElementById('clearBtn').addEventListener('click', () => {
  if (!confirm('确定清空全部任务吗？')) return;
  tasks = []; expanded.clear(); save(); render();
  document.getElementById('parseFeedback').textContent = '';
  toast('已清空');
});

document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    view = btn.dataset.view;
    render();
  });
});

document.getElementById('taskArea').addEventListener('click', e => {
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  const t = tasks.find(x => x.id === btn.dataset.id);
  if (!t) return;
  const act = btn.dataset.act;
  if (act === 'toggle') {
    if (expanded.has(t.id)) expanded.delete(t.id); else expanded.add(t.id);
    render();
    return;
  }
  if (act === 'start') { t.status = 'in_progress'; t.progress = Math.max(t.progress, 5); toast('已开始'); }
  else if (act === 'progress') { t.progress = Math.min(100, t.progress + 20); if (t.progress === 100) t.status = 'done'; else t.status = 'in_progress'; toast(`进度 ${t.progress}%`); }
  else if (act === 'finish') { t.status = 'done'; t.progress = 100; toast('已完成'); }
  else if (act === 'priority') {
    const order = ['normal', 'high', 'low'];
    t.priority = order[(order.indexOf(t.priority) + 1) % order.length];
    toast('优先级改为 ' + (PRIORITY_TEXT[t.priority] || t.priority));
  }
  else if (act === 'due') {
    const input = prompt('输入新的截止日（支持自然语言）：\n例如：下周三下午5点 / 12月5日 / 3天内', '');
    if (input === null) return;
    const res = parseDue(input, new Date());
    if (!res.due) { alert('没识别出日期，请换一种写法'); return; }
    t.due = res.due.getTime();
    toast('截止日改为 ' + fmt(t.due));
  }
  else if (act === 'note') {
    const input = prompt('追加一条备注：', '');
    if (!input) return;
    t.notes = (t.notes ? t.notes + '\n' : '') + input;
    toast('备注已保存');
  }
  else if (act === 'delete') {
    if (!confirm('删除这条任务？')) return;
    tasks = tasks.filter(x => x.id !== t.id);
    expanded.delete(t.id);
    toast('已删除');
  }
  save(); render();
});

const startBtn = document.getElementById('startBtn');
if (startBtn) startBtn.addEventListener('click', () => {
  const el = document.getElementById('noticeInput');
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.focus();
});

load(); render();

/* ---------- Agent Runtime 连接（可选 Python 后端） ----------
   同一份前端代码有两种运行方式：
   1) 公网静态托管：没有 /api/*，自动降级为上面的浏览器本地演示；
   2) python server.py：探测到 /api/health 后，对话走真实内核并回显 trace。
   这样面试官点开在线链接能看 UI，本地起服务能看到完整 Agent 行为。   */
(function () {
  const statusEl = document.getElementById('runtimeStatus');
  const input = document.getElementById('chatInput');
  const btn = document.getElementById('chatBtn');
  const reply = document.getElementById('chatReply');
  const traceBox = document.getElementById('traceBox');
  const traceEl = document.getElementById('chatTrace');
  if (!statusEl || !btn) return;
  let online = false;

  function setStatus(text, ok) {
    statusEl.textContent = text;
    statusEl.className = 'runtime-status ' + (ok ? 'online' : 'offline');
    btn.disabled = !ok;
    input.disabled = !ok;
    document.querySelectorAll('[data-chat]').forEach(b => { b.disabled = !ok; });
    if (!ok) reply.textContent = '未连接内核 · 任务演示照常可用';
  }

  async function probe() {
    try {
      const res = await fetch('api/health', { headers: { Accept: 'application/json' } });
      if (!res.ok) throw new Error('no api');
      const data = await res.json();
      if (!data.ok || !data.runtime) throw new Error('bad payload');
      online = true;
      setStatus('已连接 · ' + data.runtime.llm + ' · ' + data.runtime.tools.length + ' 工具', true);
      reply.textContent = '已连接，输入一句话试试。';
    } catch (e) {
      setStatus('浏览器模式 · 未连接内核', false);
    }
  }

  async function send(text) {
    if (!online || !text || !text.trim()) return;
    btn.disabled = true;
    reply.textContent = '思考中…';
    try {
      const res = await fetch('api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text, chat_id: 'web', channel: 'http' })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '请求失败');
      reply.textContent = data.reply || '（无回复）';
      traceBox.hidden = false;
      traceEl.textContent = (data.trace || []).map(e =>
        '[' + e.step + '] ' + e.kind + (e.name ? ' · ' + e.name : '') + '  ' + (e.payload || '')
      ).join('\n');
    } catch (e) {
      reply.textContent = '请求失败：' + e.message;
    } finally {
      btn.disabled = false;
    }
  }

  btn.addEventListener('click', () => send(input.value));
  input.addEventListener('keydown', e => { if (e.key === 'Enter') send(input.value); });
  document.querySelectorAll('[data-chat]').forEach(b => {
    b.addEventListener('click', () => { input.value = b.dataset.chat; send(b.dataset.chat); });
  });
  probe();
})();
