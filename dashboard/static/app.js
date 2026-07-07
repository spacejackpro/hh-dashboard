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

async function loadLetter() {
  try {
    const l = await api("/api/letter");
    const ta = document.querySelector('#apply-form textarea[name="letter"]');
    if (!ta.value) ta.value = l.text;
  } catch { /* поле останется пустым — движок возьмёт свой шаблон */ }
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

async function loadOverview(fresh = false) {
  const stats = await api("/api/stats" + (fresh ? "?fresh=1" : ""));
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

async function loadNegotiations(fresh = false) {
  renderTable($("#negotiations-box"), await api("/api/negotiations" + (fresh ? "?fresh=1" : "")), [
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

const fmtSalary = (it) => {
  if (!it.salary_from && !it.salary_to) return "з/п не указана";
  const f = (n) => Number(n).toLocaleString("ru-RU");
  const cur = it.currency || "";
  if (it.salary_from && it.salary_to) return `${f(it.salary_from)}–${f(it.salary_to)} ${cur}`;
  return (it.salary_from ? `от ${f(it.salary_from)}` : `до ${f(it.salary_to)}`) + ` ${cur}`;
};

function renderLetterSample(template, vacancy, resumeTitle) {
  const firstName = (userName || "").split(" ")[0] || "";
  return template
    .replace(/\{([^{}|]*)\|[^{}]*\}/g, "$1")
    .replaceAll("%(vacancy_name)s", vacancy.name ?? "")
    .replaceAll("%(employer_name)s", vacancy.employer ?? "")
    .replaceAll("%(first_name)s", firstName)
    .replaceAll("%(resume_title)s", resumeTitle || "")
    .replace(/%\([a-z_]+\)s/g, "…");
}

async function runPreview(params, letterText, resumeTitle) {
  logEl.textContent = "Пробный запуск: спрашиваю hh.ru, кого бы выбрала рассылка…";
  try {
    const p = await api("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op: "apply", params }),
    });
    const lines = [
      `Найдено по фильтру: ${p.found} вакансий (показываю первые ${p.shown}).`,
      `Реальная рассылка отправила бы откликов: ${p.would_apply} (твой лимит: ${p.limit}).`,
      "",
    ];
    for (const it of p.items) {
      const base = `${it.name} — ${it.employer ?? "?"} (${fmtSalary(it)})`;
      if (it.verdict === "apply") lines.push(`[ ДА ] ${base}\n       ${it.url}`);
      else if (it.verdict === "over_limit") lines.push(`[ -- ] ${base} — не влезает в лимит`);
      else lines.push(`[ НЕТ ] ${base} — ${it.reason}`);
    }
    const firstApply = p.items.find((it) => it.verdict === "apply");
    if (firstApply && letterText) {
      lines.push(
        "",
        params.force_message
          ? "Письмо уйдёт каждому. Пример для первой вакансии:"
          : "Письмо уйдёт только там, где оно обязательно. Пример для первой вакансии:",
        `«${renderLetterSample(letterText, firstApply, resumeTitle)}»`
      );
    }
    lines.push(
      "",
      "Это прикидка без отправки чего-либо. Реальная рассылка может отсеять ещё немного",
      "(чёрный список работодателей и т.п.). Готов? Сними галочку «Пробный запуск» и жми ещё раз."
    );
    logEl.textContent = lines.join("\n");
  } catch (e) {
    logEl.textContent = "Ошибка пробного запуска: " + e.message;
  }
}

$("#apply-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const letterText = f.letter.value.trim();
  try {
    // письмо сохраняется в файл — его же подхватит движок через --letter-file
    await api("/api/letter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: letterText }),
    });
  } catch { /* не удалось сохранить — движок возьмёт прошлый вариант */ }
  const params = {
    resume_id: f.resume_id.value || null,
    search: f.search.value.trim(),
    salary: f.salary.value || null,
    max_responses: f.max_responses.value || null,
    only_with_salary: f.only_with_salary.checked,
    skip_tests: f.skip_tests.checked,
    force_message: f.force_message.checked,
  };
  const resumeTitle = f.resume_id.selectedOptions[0]?.textContent || "";
  if (f.dry_run.checked) {
    runPreview(params, letterText, resumeTitle);
  } else {
    startOp("apply", params);
  }
});

$("#update-btn").addEventListener("click", () => startOp("update"));
$("#whoami-btn").addEventListener("click", () => startOp("whoami"));
$("#cancel-btn").addEventListener("click", () => api("/api/cancel", { method: "POST" }));

async function checkUpdate() {
  try {
    const v = await api("/api/version");
    $("#app-version").textContent = "версия " + v.current;
    if (v.update_available) {
      $("#update-ver").textContent = v.latest;
      $("#update-banner").classList.remove("hidden");
    }
  } catch { /* нет сети — проверим в следующий раз */ }
}

document.querySelectorAll("[data-refresh]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Обновляю…";
    try {
      const target = btn.dataset.refresh;
      if (target === "overview") await loadOverview(true);
      else if (target === "negotiations") await loadNegotiations(true);
      else if (target === "skipped") await loadSkipped();
    } finally {
      btn.disabled = false;
      btn.textContent = "Обновить данные";
    }
  });
});

$("#do-update-btn").addEventListener("click", async () => {
  try {
    await api("/api/update", { method: "POST" });
  } catch (e) {
    alert("Не удалось начать обновление: " + e.message);
    return;
  }
  $("#updating-overlay").classList.remove("hidden");

  const startedAt = Date.now();
  let sawRestart = false;
  const timer = setInterval(async () => {
    if (Date.now() - startedAt > 5 * 60 * 1000) {
      clearInterval(timer);
      $("#updating-hint").textContent =
        "Что-то пошло не так. Закрой приложение и запусти update.cmd вручную.";
      return;
    }
    try {
      if (!sawRestart) {
        const st = await api("/api/update/status");
        if (st.error) {
          clearInterval(timer);
          $("#updating-overlay").classList.add("hidden");
          alert("Ошибка обновления: " + st.error + "\nЗапасной способ: update.cmd");
        }
      } else {
        await api("/api/version");
        clearInterval(timer);
        location.reload();
      }
    } catch {
      sawRestart = true; // сервер ушёл на перезапуск — ждём возвращения
    }
  }, 2000);
});

$("#logout-btn").addEventListener("click", async () => {
  if (!confirm("Выйти из аккаунта hh.ru? Для работы придётся войти заново.")) return;
  try {
    await api("/api/logout", { method: "POST" });
  } catch (e) {
    alert("Не получилось выйти: " + e.message);
    return;
  }
  userName = null;
  await loadStatus();
  loadOverview();
  document.querySelector('.nav-btn[data-tab="overview"]').click();
});

// ---------- Старт ----------
loadStatus();
loadOverview();
loadResumeOptions();
loadLetter();
checkUpdate();
setInterval(loadStatus, 30000);
