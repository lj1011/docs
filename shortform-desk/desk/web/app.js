const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const BEATS = [["hook", "钩子", "0-3 秒抓住人"], ["turn", "转折", "反差 / 冲突 / 原来如此"], ["payoff", "兑现", "给出干货或结果"], ["cta", "收尾 CTA", "自然的互动引导"]];
const STEPS = [["brief", "1 简报"], ["ideas", "2 点子"], ["story", "3 故事"], ["approve", "4 批准"]];

let P = null; // current project
let ui = { tab: "all", remix: false, sel: [], editing: null, rejecting: null, cmp: null, noteFor: null };
let pollTimer = null;
let STATUS = { data: "data/projects" };

async function api(method, url, body) {
  const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

async function act(label, fn) {
  $("#busy-text").textContent = label;
  $("#busy").classList.remove("hidden");
  try { const res = await fn(); if (res && res.id) P = res; render(); return res; }
  catch (e) { toast(e.message, true); }
  finally { $("#busy").classList.add("hidden"); }
}

function toast(msg, err) {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast" + (err ? " err" : "");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), 3500);
}

const go = (step) => { location.hash = P ? `#/p/${P.id}/${step}` : "#/"; };
const pid = () => P.id;
const ideaById = (id) => P.ideas.find((i) => i.id === id);
const activeVersion = () => P.story.versions.find((v) => v.id === P.story.active);

function reachable(step) {
  if (!P) return step === "brief";
  if (step === "brief" || step === "ideas") return true;
  if (step === "story") return !!P.picked;
  if (step === "approve") return !!(activeVersion() && activeVersion().script);
}

function renderSteps(cur) {
  const order = STEPS.map((s) => s[0]);
  $("#steps").innerHTML = STEPS.map(([k, l]) => {
    const cls = k === cur ? "on" : !reachable(k) ? "off" : order.indexOf(k) < order.indexOf(cur) ? "done" : "";
    return `<a class="step ${cls}" href="${P ? `#/p/${P.id}/${k}` : "#/"}">${l}</a>`;
  }).join("");
}

function actionbar(html) { return `<div class="actionbar"><div class="inner">${html}</div></div>`; }

// ---------- home + brief ----------

async function viewHome() {
  P = null;
  renderSteps("brief");
  const { projects } = await api("GET", "/api/projects");
  $("#app").innerHTML = `
    <h1>新的创意</h1><p class="sub">先填一张简报，系统出 10 个点子，你来挑。</p>
    ${briefForm({ duration_sec: 30, refs: [] })}
    ${projects.length ? `<div class="section"><h2>之前的项目</h2><div class="card projects" style="padding:0">
      ${projects.map((p) => `<a href="#/p/${p.id}/${p.step}"><span>${esc(p.topic)}</span><span class="hint">${stepName(p.step)}</span></a>`).join("")}
    </div></div>` : ""}
    ${actionbar(`<span class="hint grow">只有「产品/主题」必填，其余可空。</span><button class="pri big" onclick="createProject()">保存并出 10 个点子 →</button>`)}`;
}

const stepName = (s) => (STEPS.find((x) => x[0] === s) || [, s])[1];

function briefForm(b) {
  const refs = [0, 1, 2].map((i) => `<input id="ref${i}" placeholder="参考 ${i + 1}：链接或一句备注（可空）" value="${esc((b.refs || [])[i] || "")}" style="margin-bottom:8px">`).join("");
  return `<div class="card">
    <label>产品 / 主题 <small>必填</small></label><input id="topic" value="${esc(b.topic)}" placeholder="例：早上不赖床 / 某款保温杯 / 新手理财第一课">
    <div class="row"><div class="grow"><label>目标受众</label><input id="audience" value="${esc(b.audience)}" placeholder="例：25-35 岁上班族"></div>
      <div class="grow"><label>语气</label><input id="tone" value="${esc(b.tone)}" placeholder="例：轻松、像朋友聊天"></div></div>
    <div class="row"><div class="grow"><label>禁区 <small>不许碰的话题/说法</small></label><input id="taboo" value="${esc(b.taboo)}" placeholder="例：医疗建议、夸大功效"></div>
      <div style="width:160px"><label>时长（秒）</label><input id="duration" type="number" min="10" max="90" value="${esc(b.duration_sec)}"></div></div>
    <label>参考 <small>最多 3 条</small></label>${refs}
  </div>`;
}

function readBrief() {
  return {
    topic: $("#topic").value, audience: $("#audience").value, tone: $("#tone").value, taboo: $("#taboo").value,
    duration_sec: $("#duration").value, refs: [0, 1, 2].map((i) => $(`#ref${i}`).value),
  };
}

async function createProject() {
  const res = await act("创建项目…", () => api("POST", "/api/projects", readBrief()));
  if (!res) return;
  location.hash = `#/p/${res.id}/ideas`;
  await act("正在发散 10 个点子…", () => api("POST", `/api/projects/${res.id}/ideas`, { count: 10 }));
}

function viewBrief() {
  $("#app").innerHTML = `<h1>简报</h1><p class="sub">改完保存，下一轮点子会按新简报出。</p>${briefForm(P.brief)}
    ${actionbar(`<span class="grow"></span><button onclick="saveBrief(false)">保存</button><button class="pri big" onclick="saveBrief(true)">保存并再出 10 个点子 →</button>`)}`;
}

async function saveBrief(more) {
  await act("保存…", () => api("PUT", `/api/projects/${pid()}/brief`, readBrief()));
  if (more) { go("ideas"); await act("正在发散 10 个点子…", () => api("POST", `/api/projects/${pid()}/ideas`, { count: 10 })); }
}

// ---------- ideas ----------

function viewIdeas() {
  const all = P.ideas;
  const live = all.filter((i) => i.status !== "rejected");
  const shown = ui.tab === "star" ? all.filter((i) => i.starred) : ui.tab === "rejected" ? all.filter((i) => i.status === "rejected") : live;
  const picked = P.picked && ideaById(P.picked);
  const nStar = all.filter((i) => i.starred).length, nRej = all.length - live.length;
  $("#app").innerHTML = `
    <h1>选 1 个点子</h1>
    <p class="sub">加星 = 多来这种；拒绝要写原因 = 下一轮避开。共 ${all.length} 条，第 ${P.rounds} 轮。</p>
    <div class="row" style="margin-bottom:14px">
      <div class="tabs" style="margin:0">
        <button class="${ui.tab === "all" ? "on" : ""}" onclick="setTab('all')">候选 ${live.length}</button>
        <button class="${ui.tab === "star" ? "on" : ""}" onclick="setTab('star')">已加星 ${nStar}</button>
        <button class="${ui.tab === "rejected" ? "on" : ""}" onclick="setTab('rejected')">已拒绝 ${nRej}</button>
      </div>
      <span class="grow"></span>
      <button onclick="toggleRemix()">${ui.remix ? "取消混搭" : "混搭两条"}</button>
      <button onclick="moreIdeas()">再来 10 条</button>
    </div>
    ${ui.remix ? `<div class="card" style="margin-bottom:14px;border-color:#2f6fed">点两张卡片选中（已选 ${ui.sel.length}/2），然后
      <button class="pri" ${ui.sel.length === 2 ? "" : "disabled"} onclick="doRemix()">混搭成新点子</button></div>` : ""}
    <div class="grid">${shown.slice().reverse().map(ideaCard).join("") || `<p class="hint">这里还没有内容。</p>`}</div>
    ${actionbar(picked
      ? `<span class="grow">已选：<b>${esc(picked.hook)}</b></span><button class="pri big" onclick="go('story')">去写故事 →</button>`
      : `<span class="hint grow">在卡片上点「选这条」，才能进入下一步。</span><button class="pri big" disabled>去写故事 →</button>`)}`;
}

function ideaCard(i) {
  const cls = ["card", "idea", i.status === "picked" && "picked", i.starred && "starred", i.status === "rejected" && "rejected", ui.sel.includes(i.id) && "sel"].filter(Boolean).join(" ");
  const origin = i.origin.startsWith("more_like") ? "类似延伸" : i.origin.startsWith("remix") ? "混搭" : `第 ${i.round} 轮`;
  const tags = `<div class="tags"><span class="tag fmt">${esc(i.format)}</span><span class="tag">${origin}</span>
    ${i.edited ? `<span class="tag">已改</span>` : ""}${i.starred ? `<span class="tag star">★ 加星</span>` : ""}${i.status === "picked" ? `<span class="tag pick">✓ 已选</span>` : ""}</div>`;
  if (ui.editing === i.id) {
    return `<div class="${cls}">${tags}
      <label>钩子</label><textarea id="e-hook">${esc(i.hook)}</textarea>
      <label>角度</label><input id="e-angle" value="${esc(i.angle)}">
      <label>形式</label><input id="e-format" value="${esc(i.format)}">
      <label>为什么能火</label><input id="e-why" value="${esc(i.why)}">
      <div class="acts"><button class="pri" onclick="saveEdit('${i.id}')">保存</button><button class="ghost" onclick="ui.editing=null;render()">取消</button></div></div>`;
  }
  const onclick = ui.remix && i.status !== "rejected" ? `onclick="toggleSel('${i.id}')"` : "";
  let acts;
  if (i.status === "rejected") {
    acts = `<div class="reason">拒绝原因：${esc(i.reject_reason)}</div><div class="acts"><button onclick="ideaAct('${i.id}','restore')">恢复</button></div>`;
  } else if (ui.rejecting === i.id) {
    acts = `<input id="reason" placeholder="一句话说为什么不要（会影响下一轮）" autofocus>
      <div class="acts"><button class="danger" onclick="doReject('${i.id}')">确认拒绝</button><button class="ghost" onclick="ui.rejecting=null;render()">取消</button></div>`;
  } else if (!ui.remix) {
    acts = `<div class="acts">
      <button class="${i.status === "picked" ? "ok" : "pri"}" onclick="ideaAct('${i.id}','pick')">${i.status === "picked" ? "✓ 已选" : "选这条"}</button>
      <button onclick="ideaAct('${i.id}','star')">${i.starred ? "★ 取消星" : "☆ 加星"}</button>
      <button onclick="moreLike('${i.id}')">更多类似</button>
      <button onclick="ui.editing='${i.id}';render()">编辑</button>
      <button class="danger" onclick="ui.rejecting='${i.id}';render()">拒绝</button></div>`;
  } else acts = "";
  return `<div class="${cls}" ${onclick}>${tags}<div class="hook">${esc(i.hook)}</div>
    <div class="meta"><b>角度</b> ${esc(i.angle)}</div><div class="meta"><b>为什么能火</b> ${esc(i.why)}</div>${acts}</div>`;
}

function setTab(t) { ui.tab = t; render(); }
function toggleRemix() { ui.remix = !ui.remix; ui.sel = []; render(); }
function toggleSel(id) { ui.sel = ui.sel.includes(id) ? ui.sel.filter((x) => x !== id) : [...ui.sel, id].slice(-2); render(); }
const ideaAct = (id, a, body) => act("保存…", () => api("POST", `/api/projects/${pid()}/ideas/${id}/${a}`, body || {}));
async function doReject(id) { const reason = $("#reason").value; const r = await ideaAct(id, "reject", { reason }); if (r) ui.rejecting = null; render(); }
async function saveEdit(id) {
  const body = { hook: $("#e-hook").value, angle: $("#e-angle").value, format: $("#e-format").value, why: $("#e-why").value };
  ui.editing = null; await ideaAct(id, "edit", body);
}
const moreIdeas = () => { ui.tab = "all"; return act("结合你的星标和拒绝，再出 10 条…", () => api("POST", `/api/projects/${pid()}/ideas`, { count: 10 })); };
const moreLike = (id) => act("找同一路子的点子…", () => api("POST", `/api/projects/${pid()}/ideas/${id}/more`));
async function doRemix() {
  const [a, b] = ui.sel;
  ui.remix = false; ui.sel = [];
  await act("混搭中…", () => api("POST", `/api/projects/${pid()}/remix`, { a, b }));
}

// ---------- story ----------

function viewStory() {
  const idea = ideaById(P.picked);
  const v = activeVersion();
  const versions = P.story.versions.filter((x) => x.idea === P.picked);
  let body = `<h1>把点子写成故事</h1><p class="sub">先定四拍大纲，再展开成脚本和镜头。任何一拍都能改、能单独重写。</p>
    <div class="card picked-idea"><div class="tags"><span class="tag fmt">${esc(idea.format)}</span><span class="tag pick">选中的点子</span></div>
      <div style="font-size:19px;font-weight:800;margin-top:6px">${esc(idea.hook)}</div><div class="hint">${esc(idea.angle)} · ${esc(idea.why)}</div></div>`;
  if (!v || v.idea !== P.picked) {
    $("#app").innerHTML = body + `<div class="section card" style="text-align:center;padding:40px">
      <p class="sub">还没有大纲。</p><button class="pri big" onclick="genOutline()">生成四拍大纲</button></div>
      ${actionbar(`<button class="ghost" onclick="go('ideas')">← 换点子</button><span class="grow"></span>`)}`;
    return;
  }
  body += versionBar(versions, v);
  if (ui.cmp) body += compareView(versions);
  body += `<div class="section"><h2>四拍大纲 <span class="hint">v${v.n} · ${esc(v.label)}</span></h2><div class="beats">
    ${BEATS.map(([k, l, h]) => `<div class="card beat"><h3>${l} <span>${h}</span></h3>
      <textarea data-beat="${k}" onchange="saveBeat(this)" rows="3">${esc(v.beats[k])}</textarea>
      ${ui.noteFor === k
        ? `<input id="note" placeholder="想怎么改？（可空）" style="margin-top:8px"><div class="row" style="margin-top:8px"><button class="pri" onclick="regenBeat('${k}')">重写这一拍</button><button class="ghost" onclick="ui.noteFor=null;render()">取消</button></div>`
        : `<div class="row" style="margin-top:8px"><button onclick="ui.noteFor='${k}';render()">重写这一拍</button></div>`}
    </div>`).join("")}</div></div>`;
  body += `<div class="section"><h2>脚本 + 镜头表</h2>`;
  if (!v.script) {
    body += `<div class="card" style="text-align:center;padding:32px"><p class="sub">大纲满意了，就展开成脚本。</p><button class="pri big" onclick="genScript()">从大纲写脚本</button></div></div>`;
  } else {
    body += `<div class="card"><label style="margin-top:0">标题</label><input id="s-title" value="${esc(v.script.title)}" onchange="saveScript()">
      <table style="margin-top:12px"><tr><th>#</th><th>拍</th><th style="width:44%">口播</th><th>画面大字</th><th>画面描述</th></tr>
      ${v.script.shots.map((s, i) => `<tr data-shot="${i}"><td class="n">${i + 1}</td><td><span class="tag">${esc(beatLabel(s.beat))}</span></td>
        <td><textarea class="s-vo" rows="2" onchange="saveScript()">${esc(s.vo)}</textarea></td>
        <td><input class="s-st" value="${esc(s.screen_text)}" onchange="saveScript()"></td>
        <td><textarea class="s-vis" rows="2" onchange="saveScript()">${esc(s.visual)}</textarea></td></tr>`).join("")}
      </table><div class="row" style="margin-top:12px"><button onclick="genScript()">按当前大纲重写脚本（新版本）</button>
      <span class="hint">约 ${v.script.shots.reduce((n, s) => n + s.vo.length, 0)} 字 ≈ ${Math.round(v.script.shots.reduce((n, s) => n + s.vo.length, 0) / 4.5)} 秒</span></div></div></div>`;
  }
  $("#app").innerHTML = body + actionbar(`<button class="ghost" onclick="go('ideas')">← 换点子</button><span class="grow"></span>
    ${v.script ? `<button class="pri big" onclick="go('approve')">去批准 →</button>` : `<span class="hint">先写出脚本，才能批准</span>`}`);
}

const beatLabel = (k) => (BEATS.find((b) => b[0] === k) || [, k || "-"])[1];

function versionBar(versions, v) {
  return `<div class="versions"><span class="hint">版本：</span>
    ${versions.map((x) => `<span class="vchip ${x.id === v.id ? "on" : ""} ${x.id === P.story.approved ? "appr" : ""}" onclick="setActive('${x.id}')" title="${esc(x.label)}">v${x.n} ${esc(x.label)}${x.script ? "" : "（无脚本）"}</span>`).join("")}
    ${versions.length > 1 ? `<button onclick="toggleCmp()">${ui.cmp ? "关闭对比" : "对比两个版本"}</button>` : ""}</div>`;
}

function toggleCmp() {
  const vs = P.story.versions.filter((x) => x.idea === P.picked);
  ui.cmp = ui.cmp ? null : { a: vs[vs.length - 2].id, b: vs[vs.length - 1].id };
  render();
}

function compareView(versions) {
  const A = versions.find((x) => x.id === ui.cmp.a) || versions[0], B = versions.find((x) => x.id === ui.cmp.b) || versions[versions.length - 1];
  const sel = (side, cur) => `<select onchange="ui.cmp.${side}=this.value;render()">${versions.map((x) => `<option value="${x.id}" ${x.id === cur.id ? "selected" : ""}>v${x.n} ${esc(x.label)}</option>`).join("")}</select>`;
  const col = (X, Y, side) => `<div class="card">${sel(side, X)}
    ${BEATS.map(([k, l]) => `<h4>${l}</h4><p class="${X.beats[k] !== Y.beats[k] ? "diff" : ""}">${esc(X.beats[k])}</p>`).join("")}
    <h4>脚本</h4>${X.script ? X.script.shots.map((s, i) => `<p class="${Y.script && Y.script.shots[i] && Y.script.shots[i].vo === s.vo ? "" : "diff"}">${i + 1}. ${esc(s.vo)}</p>`).join("") : `<p class="hint">无脚本</p>`}
    <button class="pri" onclick="setActive('${X.id}')">用这个版本</button></div>`;
  return `<div class="section"><h2>版本对比 <span class="hint">黄色 = 不同</span></h2><div class="cmp">${col(A, B, "a")}${col(B, A, "b")}</div></div>`;
}

const genOutline = () => act("写四拍大纲…", () => api("POST", `/api/projects/${pid()}/outline`));
const genScript = () => act("展开成脚本和镜头…", () => api("POST", `/api/projects/${pid()}/script`));
async function regenBeat(k) { const note = ($("#note") || {}).value || ""; ui.noteFor = null; await act(`重写「${beatLabel(k)}」…`, () => api("POST", `/api/projects/${pid()}/beats/${k}`, { note })); }
async function setActive(id) { ui.cmp = null; await act("切换版本…", () => api("POST", `/api/projects/${pid()}/story/active`, { id })); }
async function saveBeat(el) { P = await api("PUT", `/api/projects/${pid()}/story`, { beats: { [el.dataset.beat]: el.value } }); toast("已保存"); }
async function saveScript() {
  const shots = [...document.querySelectorAll("tr[data-shot]")].map((tr, i) => ({
    beat: activeVersion().script.shots[i].beat, vo: tr.querySelector(".s-vo").value, screen_text: tr.querySelector(".s-st").value, visual: tr.querySelector(".s-vis").value,
  }));
  P = await api("PUT", `/api/projects/${pid()}/story`, { script: { title: $("#s-title").value, shots } });
  toast("已保存");
}

// ---------- approve ----------

function viewApprove() {
  const v = activeVersion();
  const approved = P.story.approved === v.id;
  const r = P.render;
  const file = `${STATUS.data}/${P.id}/script.json`;
  let html = `<h1>${approved ? "已批准" : "最后看一遍，再批准"}</h1>
    <p class="sub">${approved ? "这版脚本已交给渲染。改任何内容都会自动撤销批准。" : "批准后会生成给 desk render 用的 script.json。没批准不能渲染。"}</p>`;
  if (approved) html += `<div class="approved-banner">✓ v${v.n} 已批准 · ${esc(v.script.title)}</div>`;
  html += `<div class="section card"><h2 style="margin-top:0">${esc(v.script.title)}</h2>
    <table><tr><th>#</th><th>拍</th><th>口播</th><th>画面大字</th></tr>
    ${v.script.shots.map((s, i) => `<tr><td class="n">${i + 1}</td><td><span class="tag">${esc(beatLabel(s.beat))}</span></td><td>${esc(s.vo)}</td><td>${esc(s.screen_text)}</td></tr>`).join("")}</table></div>`;
  if (approved) {
    html += `<div class="section card"><h2 style="margin-top:0">交给渲染</h2>
      <p>脚本文件：<code>${file}</code> · <a href="/files/${P.id}/script.json" target="_blank">打开</a></p>
      <p>命令行：</p><pre>python -m desk render ${file} -o out/${P.id}.mp4 --bgm auto</pre>
      ${r && r.status === "running" ? `<p><b>渲染中…</b> 约 20-60 秒</p>` : ""}
      ${r && r.status === "error" ? `<p class="reason">渲染失败：${esc(r.error)}</p>` : ""}
      ${r && r.status === "done" ? `<video src="/files/${P.id}/video.mp4?v=${P.updated}" poster="/files/${P.id}/poster.jpg?v=${P.updated}" controls preload="none"></video><p class="hint">${r.report.duration_sec}s · ${r.report.size} · 配音 ${r.report.tts.join(",")} · 画面 ${r.report.visual.join(",")}</p>` : ""}
    </div>`;
  }
  $("#app").innerHTML = html + actionbar(approved
    ? `<button class="ghost" onclick="unapprove()">撤销批准</button><span class="grow"></span><button class="pri big" onclick="startRender()" ${r && r.status === "running" ? "disabled" : ""}>现在渲染成片</button>`
    : `<button class="ghost" onclick="go('story')">← 回去改</button><span class="grow"></span><button class="ok big" onclick="approve()">我看过了，批准这一版</button>`);
  if (r && r.status === "running") { clearTimeout(pollTimer); pollTimer = setTimeout(reload, 2500); }
}

const approve = () => act("批准…", () => api("POST", `/api/projects/${pid()}/approve`));
const unapprove = () => act("撤销…", () => api("POST", `/api/projects/${pid()}/unapprove`));
async function startRender() { await act("开始渲染…", () => api("POST", `/api/projects/${pid()}/render`)); await reload(); }

// ---------- router ----------

async function reload() {
  P = await api("GET", `/api/projects/${pid()}`);
  render();
}

function currentStep() { return (location.hash.match(/^#\/p\/\w+\/(\w+)/) || [])[1] || "brief"; }

function render() {
  if (!P) return;
  let step = currentStep();
  if (!reachable(step)) step = P.picked ? "story" : "ideas";
  renderSteps(step);
  ({ brief: viewBrief, ideas: viewIdeas, story: viewStory, approve: viewApprove })[step]();
}

async function route() {
  clearTimeout(pollTimer);
  const m = location.hash.match(/^#\/p\/(\w+)/);
  try {
    if (!m) return await viewHome();
    if (!P || P.id !== m[1]) { ui = { tab: "all", remix: false, sel: [], editing: null, rejecting: null, cmp: null, noteFor: null }; P = await api("GET", `/api/projects/${m[1]}`); }
    render();
    window.scrollTo(0, 0);
  } catch (e) { toast(e.message, true); }
}

(async function init() {
  const s = (STATUS = await api("GET", "/api/status"));
  $("#llm").textContent = `模型：${s.llm.name} / ${s.llm.model}`;
  if (s.mock) { const m = $("#mock"); m.innerHTML = `<b>${esc(s.hint.split("\n")[0])}</b>\n${esc(s.hint.split("\n").slice(1).join("\n"))}`; m.classList.remove("hidden"); }
  window.addEventListener("hashchange", route);
  route();
})();
