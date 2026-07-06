"use strict";

const $ = (sel) => document.querySelector(sel);

// ---------- Навигация по вкладкам ----------
document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    $("#tab-" + btn.dataset.tab).classList.add("active");
    loadTab(btn.dataset.tab);
  });
});

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

// ---------- Рендер таблиц ----------
function renderTable(box, rows, columns) {
  if (!rows.length) {
    box.innerHTML = '<div class="empty">Пока пусто — данные появятся после первых запусков утилиты</div>';
    return;
  }
  const thead = columns.map((c) => `<th>${c.title}</th>`).join("");
  const tbody = rows
    .map((r) => `<tr>${columns.map((c) => `<td>${c.render(r)}</td>`).join("")}</tr>`)
    .join("");
  box.innerHTML = `<table><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table>`;
}

const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));

const link = (url, text) =>
  url ? `<a href="${esc(url)}" target="_blank">${esc(text)}</a>` : esc(text);

const salary = (r) => {
  const from = r.salary_from ?? r.vacancy_salary_from;
  const to = r.salary_to ?? r.vacancy_salary_to;
  const cur = r.currency ?? r.vacancy_currency ?? "";
  if (!from && !to) return "—";
  const fmt = (n) => Number(n).toLocaleString("ru-RU");
  if (from && to) return `${fmt(from)}–${fmt(to)} ${cur}`;
  return (from ? `от ${fmt(from)}` : `до ${fmt(to)}`) + ` ${cur}`;
};

const dt = (s) => (s ? String(s).replace("T", " ").slice(0, 16) : "—");

// ---------- Загрузка данных вкладок ----------
let userName = null;

async function loadStatus() {
  const badge = $("#auth-badge");
  const banner = $("#auth-banner");
  try {
    const { token } = await api("/api/status");
    const ok = token.authorized && !token.expired;
    banner.classList.toggle("hidden", ok);
    if (ok) {
      if (!userName) {
        try {
          const me = await api("/api/whoami");
          userName = [me.first_name, me.last_name].filter(Boolean).join(" ");
        } catch { /* API недоступен — покажем просто галочку */ }
      }
      badge.textContent = "✓ " + (userName || "авторизован");
      badge.className = "auth-badge ok";
    } else {
      userName = null;
      badge.textContent = token.authorized ? "токен истёк — войди заново" : "не авторизован";
      badge.className = "auth-badge bad";
    }
    return ok;
  } catch {
    badge.textContent = "сервер недоступен";
    badge.className = "auth-badge bad";
    return false;
  }
}

async function loadResumeOptions() {
  try {
    const sel = document.querySelector('#apply-form select[name="resume_id"]');
    const current = sel.value;
    const resumes = await api("/api/resumes");
    sel.innerHTML =
      '<option value="">первое резюме (по умолчанию)</option>' +
      resumes.map((r) => `<option value="${esc(r.id)}">${esc(r.title)}</option>`).join("");
    sel.value = current;
  } catch { /* без списка остаётся вариант по умолчанию */ }
}

async function loadOverview() {
  const stats = await api("/api/stats");
  $("#stats-cards").innerHTML = `
    <div class="card limit">
      <div class="value">${stats.today} / ${stats.daily_limit}</div>
      <div class="hint">откликов сегодня</div>
    </div>
    <div class="card"><div class="value">${stats.total}</div><div class="hint">откликов всего</div></div>
    <div class="card"><div class="value">${stats.skipped}</div><div class="hint">пропущено вакансий</div></div>
    <div class="card"><div class="value">${stats.employers}</div><div class="hint">работодателей в базе</div></div>`;

  renderTable($("#resumes-box"), await api("/api/resumes"), [
    { title: "Резюме", render: (r) => link(r.alternate_url, r.title) },
    { title: "Статус", render: (r) => esc(r.status_name ?? "—") },
    { title: "Просмотры", render: (r) => `${r.total_views ?? 0} (+${r.new_views ?? 0} новых)` },
    { title: "Обновлено", render: (r) => dt(r.updated_at) },
  ]);
}

async function loadNegotiations() {
  renderTable($("#negotiations-box"), await api("/api/negotiations"), [
    { title: "Вакансия", render: (r) => link(r.alternate_url, r.vacancy_name ?? r.vacancy_id) },
    { title: "Работодатель", render: (r) => esc(r.employer_name ?? "—") },
    { title: "Зарплата", render: salary },
    { title: "Регион", render: (r) => esc(r.area_name ?? "—") },
    { title: "Статус", render: (r) => `<span class="state ${esc(r.state)}">${esc(r.state)}</span>` },
    { title: "Отклик", render: (r) => dt(r.created_at) },
  ]);
}

async function loadSkipped() {
  renderTable($("#skipped-box"), await api("/api/skipped"), [
    { title: "Вакансия", render: (r) => link(r.alternate_url, r.name ?? r.vacancy_id) },
    { title: "Работодатель", render: (r) => esc(r.employer_name ?? "—") },
    { title: "Причина", render: (r) => esc(r.reason) },
    { title: "Когда", render: (r) => dt(r.created_at) },
  ]);
}

function loadTab(tab) {
  ({
    overview: loadOverview,
    negotiations: loadNegotiations,
    skipped: loadSkipped,
    run: loadResumeOptions,
  }[tab]?.() ?? null);
}

// ---------- Запуск операций ----------
const logEl = $("#log");
let logSource = null;
let onDoneCallback = null;

function followLogs() {
  if (logSource) logSource.close();
  logEl.textContent = "";
  logSource = new EventSource("/api/logs");
  logSource.onmessage = (e) => {
    logEl.textContent += JSON.parse(e.data) + "\n";
    logEl.scrollTop = logEl.scrollHeight;
  };
  logSource.addEventListener("done", () => {
    logSource.close();
    logSource = null;
    setRunning(false);
    loadStatus();
    if (onDoneCallback) {
      const cb = onDoneCallback;
      onDoneCallback = null;
      cb();
    }
  });
}

function setRunning(running) {
  $("#apply-btn").disabled = running;
  $("#update-btn").disabled = running;
  $("#cancel-btn").disabled = !running;
}

async function startOp(op, params = {}) {
  try {
    await api("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op, params }),
    });
    setRunning(true);
    followLogs();
    return true;
  } catch (e) {
    logEl.textContent = "Не удалось запустить: " + e.message;
    return false;
  }
}

// ---------- Авторизация из дашборда ----------
const AUTH_HINT_DEFAULT =
  "Нажми кнопку — откроется окно браузера, где нужно войти в свой аккаунт как обычно (пароль или код из SMS).";

$("#login-btn").addEventListener("click", async () => {
  const btn = $("#login-btn");
  const hint = $("#auth-hint");

  onDoneCallback = async () => {
    btn.disabled = false;
    btn.textContent = "Войти в hh.ru";
    if (await loadStatus()) {
      hint.textContent = AUTH_HINT_DEFAULT;
      loadOverview();
      loadResumeOptions();
    } else {
      hint.textContent = "Похоже, вход не завершился. Попробуй ещё раз.";
    }
  };

  btn.disabled = true;
  btn.textContent = "Жду входа…";
  hint.textContent =
    "Окно браузера открыто — войди в свой аккаунт hh.ru. После входа окно закроется само.";

  if (!(await startOp("authorize"))) {
    onDoneCallback = null;
    btn.disabled = false;
    btn.textContent = "Войти в hh.ru";
    hint.textContent = "Не удалось запустить вход (возможно, уже идёт другая операция).";
  }
});

$("#apply-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const f = e.target;
  startOp("apply", {
    resume_id: f.resume_id.value || null,
    search: f.search.value.trim(),
    salary: f.salary.value || null,
    max_responses: f.max_responses.value || null,
    only_with_salary: f.only_with_salary.checked,
    skip_tests: f.skip_tests.checked,
    dry_run: f.dry_run.checked,
  });
});

$("#update-btn").addEventListener("click", () => startOp("update"));
$("#whoami-btn").addEventListener("click", () => startOp("whoami"));
$("#cancel-btn").addEventListener("click", () => api("/api/cancel", { method: "POST" }));

async function checkUpdate() {
  try {
    const v = await api("/api/version");
    if (v.update_available) {
      $("#update-ver").textContent = v.latest;
      $("#update-banner").classList.remove("hidden");
    }
  } catch { /* нет сети — проверим в следующий раз */ }
}

// ---------- Старт ----------
loadStatus();
loadOverview();
loadResumeOptions();
checkUpdate();
setInterval(loadStatus, 30000);
