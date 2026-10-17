"""Своя рассылка откликов через API hh.ru — с общим стоп-листом.

Почему не движок: движок (apply-vacancies) сверяется со списком пропущенных
только при включённом ИИ, поэтому надёжный общий стоп-лист между аккаунтами
поверх него не сделать. Здесь мы сами проходим по вакансиям и перед каждым
откликом сверяемся с общим журналом. Отклик отправляется тем же вызовом
POST /negotiations, что и в движке.

Плата за контроль: вакансии с тестом не проходятся автоматически (движок это
умеет) — они просто пропускаются. По умолчанию тесты и так пропускаются.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from hh_applicant_tool.api.errors import (
    CaptchaRequired,
    LimitExceeded,
    Redirect,
)
from hh_applicant_tool.utils.string import rand_text

from . import paths, profiles, stoplist
from .hh import _make_tool, build_search_text, get_letter

Emit = Callable[[str], None]
Cancelled = Callable[[], bool]


def _active_label() -> str:
    active = paths.active_profile()
    for p in profiles.list_profiles():
        if p["id"] == active:
            return p["label"]
    return "аккаунт"


async def run_apply(params: dict[str, Any], emit: Emit, cancelled: Cancelled) -> int:
    """Возвращает число отправленных (или в пробном режиме — потенциальных) откликов."""
    dry = bool(params.get("dry_run"))
    skip_tests = bool(params.get("skip_tests"))
    force_message = bool(params.get("force_message"))
    try:
        limit = int(params.get("max_responses") or 0) or 10
    except (TypeError, ValueError):
        limit = 10

    tool = await asyncio.to_thread(_make_tool)
    api = tool.api_client
    label = _active_label()

    # выбираем резюме: указанное или первое
    resumes = await asyncio.to_thread(tool.get_resumes)
    if not resumes:
        emit("У этого аккаунта нет резюме — откликаться нечем.")
        return 0
    wanted = params.get("resume_id")
    resume = next((r for r in resumes if r["id"] == wanted), None) if wanted else resumes[0]
    if resume is None:
        emit("Выбранное резюме не найдено у этого аккаунта.")
        return 0
    resume_id = resume["id"]

    me = await asyncio.to_thread(tool.get_me)
    letter_tpl = get_letter()["text"]
    base_ph = {
        "first_name": me.get("first_name") or "",
        "last_name": me.get("last_name") or "",
        "email": me.get("email") or "",
        "phone": me.get("phone") or "",
        "resume_title": resume.get("title") or "",
        "resume_url": resume.get("alternate_url") or "",
        "resume_hash": resume_id,
    }

    search = build_search_text(params.get("keywords") or [])
    query: dict[str, Any] = {"per_page": 100}
    if search:
        query["text"] = search
    if params.get("search_fields"):
        query["search_field"] = list(params["search_fields"])
    if params.get("areas"):
        query["area"] = [str(a) for a in params["areas"]]
    if params.get("salary"):
        query["salary"] = int(params["salary"])
    if params.get("only_with_salary"):
        query["only_with_salary"] = "true"

    stop_ids = stoplist.applied_ids()

    emit(f"Аккаунт: {label}. Резюме: {resume.get('title')}.")
    emit(f"Поиск: {search or 'рекомендованные вакансии'}. Лимит: {limit}."
         + ("  [ПРОБНЫЙ ЗАПУСК — ничего не отправляется]" if dry else ""))
    emit("")

    applied = 0
    page = 0
    letter_shown = False
    stopped = False
    while applied < limit and not stopped:
        if cancelled():
            emit("--- остановлено пользователем ---")
            break
        try:
            r = await asyncio.to_thread(_search, api, query, page)
        except Exception as e:
            emit(f"Ошибка поиска: {e}")
            break
        items = r.get("items", [])
        if not items:
            break

        for v in items:
            if applied >= limit or cancelled():
                break
            vid = str(v.get("id"))
            name = v.get("name") or vid
            empl = (v.get("employer") or {}).get("name") or "?"
            url = v.get("alternate_url") or ""
            tag = f"{name} — {empl}"

            if v.get("relations"):
                continue  # этот аккаунт уже откликался — тихо пропускаем
            if vid in stop_ids:
                emit(f"[ уже с другого аккаунта ] {tag}")
                continue
            if v.get("archived"):
                continue
            if skip_tests and v.get("has_test"):
                emit(f"[ пропуск: тест ] {tag}")
                continue
            if v.get("response_url"):
                continue  # отклик только на внешнем сайте

            letter = ""
            if force_message or v.get("response_letter_required"):
                ph = {**base_ph, "vacancy_name": name, "employer_name": empl}
                letter = rand_text(letter_tpl) % ph

            if dry:
                applied += 1
                emit(f"[ ДА {applied}/{limit} ] {tag}\n    {url}")
                if letter and not letter_shown:
                    letter_shown = True
                    emit(f"    письмо для этой вакансии: «{letter}»")
                continue

            try:
                try:
                    await asyncio.to_thread(_apply, api, resume_id, vid, letter)
                except CaptchaRequired as ex:
                    # пока капча не решена, hh.ru отвергает ВСЕ отклики подряд —
                    # пропускать бессмысленно, только злим антибот
                    emit(f"[ капча ] {tag}")
                    emit("hh.ru просит капчу. Открываю окно браузера — введи "
                         "символы с картинки, окно закроется само (до 5 минут).")
                    if not await solve_captcha(ex.captcha_url, cancelled):
                        emit("--- капча не введена — рассылка остановлена. "
                             "Запусти заново, когда будешь у компьютера ---")
                        stopped = True
                        break
                    emit("Капча принята, продолжаю.")
                    # повтор той же вакансии; новая капча сразу — значит не помогло
                    await asyncio.to_thread(_apply, api, resume_id, vid, letter)
            except CaptchaRequired:
                emit("--- hh.ru снова просит капчу — рассылка остановлена. "
                     "Подожди полчаса-час и запусти заново ---")
                stopped = True
                break
            except LimitExceeded:
                emit("--- достигнут дневной лимит откликов hh.ru (200) ---")
                applied = limit
                break
            except Redirect:
                continue
            except Exception as e:
                emit(f"[ ошибка ] {tag} — {e}")
                continue

            applied += 1
            stoplist.add(vid, label, name, url)
            stop_ids.add(vid)
            emit(f"[ отклик {applied}/{limit} ] {tag}\n    {url}")

        if stopped:
            break
        page += 1
        if page >= r.get("pages", 0):
            break

    await asyncio.to_thread(tool.save_token)
    emit("")
    if dry:
        emit(f"Пробный запуск: откликнулся бы на {applied}. Реальных откликов не отправлено.")
    else:
        emit(f"Готово. Отправлено откликов с аккаунта «{label}»: {applied}.")
    return applied


CAPTCHA_DONE_URL = "https://hh.ru/"
CAPTCHA_TIMEOUT = 300  # секунд на ввод


async def solve_captcha(captcha_url: str | None, cancelled: Cancelled) -> bool:
    """Показывает капчу человеку в видимом окне браузера.

    Движок решает её через ИИ (нужен ключ OpenAI), у нас ключа нет — поэтому
    вводит человек. Движок решает её в чистом браузере без кук — значит,
    капча привязана к самой ссылке. После ввода hh.ru уводит на backurl — по
    уходу со страницы капчи и понимаем, что готово.
    """
    if not captcha_url:
        return False
    from playwright.async_api import async_playwright

    parts = urlsplit(captcha_url)
    query = parse_qs(parts.query)
    if "backurl" not in query:
        query["backurl"] = [CAPTCHA_DONE_URL]
    url = urlunsplit(parts._replace(query=urlencode(query, doseq=True)))
    captcha_path = parts.path

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False)
            try:
                page = await (await browser.new_context()).new_page()
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                loop = asyncio.get_running_loop()
                deadline = loop.time() + CAPTCHA_TIMEOUT
                while loop.time() < deadline:
                    if cancelled() or page.is_closed() or not browser.is_connected():
                        return False
                    cur = urlsplit(page.url)
                    if cur.netloc and cur.path != captcha_path:
                        await asyncio.sleep(1)  # дать hh.ru записать решение
                        return True
                    await asyncio.sleep(1)
                return False
            finally:
                if browser.is_connected():
                    await browser.close()
    except Exception:
        return False


def _search(api, query: dict[str, Any], page: int) -> dict[str, Any]:
    return api.get("/vacancies", page=page, **query)


def _apply(api, resume_id: str, vacancy_id: str, message: str) -> None:
    # тот же вызов, что делает движок при отклике
    api.post(
        "/negotiations",
        {"resume_id": resume_id, "vacancy_id": vacancy_id, "message": message},
        delay=random.uniform(1, 3),
    )
