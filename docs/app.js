/* DeadlineBot 交互演示
 * 用 JavaScript 复刻 Python 版的核心逻辑（日期解析 / 内容排序 / 进度），
 * 便于在浏览器里直接体验。完整实现见仓库 deadline_bot/ 目录。
 */

const STORAGE_KEY = 'deadlinebot.tasks.v1';
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
  s = s.replace(/^[\u4e00-\u9fa5A-Za-z]{2,10}(通知|提醒|公告)\s*[:：]\s*/, '');
  s = s.replace(/^(各位同学|同学们|大家好|各位同事|【[^】]*】)/, ' ');
  s = s.replace(/^\s*(前|之前|截止前)\s*/, ' ');
  s = s.replace(/(上午|下午|晚上|中午)?\s*\d{1,2}\s*[:点时]\s*\d{0,2}\s*分?(前|之前)?/g, ' ');
  s = s.replace(/\s+/g, ' ').replace(/^[ ，。；;：:、]+|[ ，。；;：:、]+$/g, '');
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
    created: Date.now()
  };
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

function load() {
  try { tasks = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }
  catch (e) { tasks = []; }
}
function save() { localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks)); }
function fmt(ts) {
  if (ts === null) return '无明确截止日';
  const d = new Date(ts);
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function daysLeft(t) { return t.due === null ? null : (t.due - Date.now()) / 86400000; }
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

function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg; el.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove('show'), 1800);
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
  const chips = [];
  chips.push(`<span class="chip">${t.category}</span>`);
  chips.push(`<span class="chip">${t.source}</span>`);
  if (t.priority === 'high') chips.push('<span class="chip high">加急</span>');
  if (t.status === 'in_progress') chips.push('<span class="chip doing">进行中</span>');
  if (t.status !== 'done' && r !== null && r < 0) chips.push('<span class="chip overdue">已逾期</span>');
  else if (t.status !== 'done' && r !== null && r <= 1) chips.push('<span class="chip soon">今天到期</span>');
  let detail;
  if (r === null) detail = '无明确截止日';
  else if (r < 0) detail = `已逾期 ${Math.abs(r).toFixed(1)} 天`;
  else if (r < 1) detail = `还剩 ${(r * 24).toFixed(1)} 小时`;
  else detail = `还剩 ${r.toFixed(1)} 天`;
  chips.push(`<span class="chip">${fmt(t.due)}</span>`);
  chips.push(`<span class="chip">${detail}</span>`);

  const bar = `<div class="progress-line"><div class="bar"><i style="width:${t.progress}%"></i></div><span class="pct">${t.progress}%</span></div>`;
  const actions = `
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
    </div>`;
  const noteHtml = t.notes ? `<div class="reason">备注：${escapeHtml(t.notes.split('\n').pop())}</div>` : '';
  return `<div class="task ${t.status === 'done' ? 'done' : ''}">
    <div class="rank">${index}</div>
    <div class="task-body">
      <div class="task-title">${escapeHtml(t.title)}</div>
      <div class="task-meta">${chips.join('')}</div>
      ${bar}
      ${showReason ? `<div class="reason">排序分数 ${score} · 理由：${reason}</div>` : ''}
      ${noteHtml}
    </div>
    ${actions}
  </div>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function render() {
  renderSummary();
  const area = document.getElementById('taskArea');
  const active = tasks.filter(t => t.status !== 'done' && t.status !== 'cancelled');
  const done = tasks.filter(t => t.status === 'done');

  if (!tasks.length) {
    area.innerHTML = '<div class="empty">还没有任务。粘贴一条通知，或点「加载 8 条示例通知」开始体验。</div>';
    return;
  }

  let html = '';
  if (view === 'plan') {
    const ranked = active.slice().sort((a, b) => workScore(b, Date.now()).score - workScore(a, Date.now()).score || (a.due ?? Infinity) - (b.due ?? Infinity));
    html += '<div class="group-title">今日执行顺序 · 综合优先级 / 类别提前量 / 紧迫度 / 进行中状态</div>';
    html += ranked.map((t, i) => taskCard(t, i + 1, true)).join('') || '<div class="empty">没有待办任务了。</div>';
    if (done.length) html += `<div class="group-title">已完成（${done.length}）</div>` + done.map((t, i) => taskCard(t, i + 1, false)).join('');
  } else if (view === 'daily') {
    const doing = active.filter(t => t.status === 'in_progress');
    const pending = active.filter(t => t.status === 'pending');
    if (doing.length) html += `<div class="group-title">正在进行（${doing.length}）</div>` + doing.map((t, i) => taskCard(t, i + 1, false)).join('');
    const focus = doing.concat(pending).sort((a, b) => workScore(b, Date.now()).score - workScore(a, Date.now()).score).slice(0, 5);
    html += '<div class="group-title">今日建议先做 · Top 5</div>' + focus.map((t, i) => taskCard(t, i + 1, true)).join('');
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
  const t = parseNotice(text.trim());
  const dup = tasks.some(x => x.title === t.title && x.due === t.due);
  if (dup) return { ok: false, msg: '已存在相同任务，未重复添加' };
  tasks.push(t); save(); render();
  return { ok: true, msg: `已添加：${t.title} · 截止 ${fmt(t.due)} · 来源 ${t.source}`, task: t };
}

document.getElementById('addBtn').addEventListener('click', () => {
  const el = document.getElementById('noticeInput');
  const fb = document.getElementById('parseFeedback');
  if (!el.value.trim()) { fb.className = 'feedback err'; fb.textContent = '请先输入一条通知'; return; }
  const res = addNotice(el.value);
  fb.className = 'feedback ' + (res.ok ? 'ok' : 'err');
  fb.textContent = res.msg;
  if (res.ok) { el.value = ''; toast('任务已添加'); }
});

document.getElementById('noticeInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) document.getElementById('addBtn').click();
});

document.getElementById('sampleBtn').addEventListener('click', () => {
  let added = 0;
  SAMPLES.forEach(s => { if (addNotice(s).ok) added++; });
  const fb = document.getElementById('parseFeedback');
  fb.className = 'feedback ok';
  fb.textContent = `已加载 ${added} 条示例通知（重复项自动跳过）`;
  toast(`加载了 ${added} 条`);
});

document.getElementById('clearBtn').addEventListener('click', () => {
  if (!confirm('确定清空全部任务吗？')) return;
  tasks = []; save(); render();
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
  if (act === 'start') { t.status = 'in_progress'; t.progress = Math.max(t.progress, 5); toast('已开始'); }
  else if (act === 'progress') { t.progress = Math.min(100, t.progress + 20); if (t.progress === 100) t.status = 'done'; else t.status = 'in_progress'; toast(`进度 ${t.progress}%`); }
  else if (act === 'finish') { t.status = 'done'; t.progress = 100; toast('已完成'); }
  else if (act === 'priority') {
    const order = ['normal', 'high', 'low'];
    t.priority = order[(order.indexOf(t.priority) + 1) % order.length];
    toast('优先级改为 ' + t.priority);
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
    toast('已删除');
  }
  save(); render();
});

load(); render();
