"""Вход в hh.ru с паузой — для мультиаккаунтов (соискатель + работодатель).

Обычный `hh-applicant-tool authorize` открывает браузер сразу на странице
выдачи токена: hh.ru молча отдаёт токен той роли, что активна в сессии.
Если на одной почте два аккаунта, активным часто оказывается работодатель,
и переключиться пользователь не успевает.

Здесь вход разбит на два шага: сначала человек спокойно входит на hh.ru и
переключается на аккаунт соискателя, и только потом, по его команде, мы
идём за токеном.
"""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlsplit

HH_ANDROID_SCHEME = "hhandroid"
LOGIN_URL = "https://hh.ru/account/login"


class LoginFlow:
    """Состояния: idle → waiting_user → finishing → done | error."""

    def __init__(self) -> None:
        self.state = "idle"
        self.error: str | None = None
        self._continue: asyncio.Event | None = None
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self.state in ("waiting_user", "finishing")

    def status(self) -> dict:
        return {"state": self.state, "error": self.error}

    async def start(self) -> None:
        if self.running:
            raise RuntimeError("Вход уже идёт")
        self._continue = asyncio.Event()
        self.state = "waiting_user"
        self.error = None
        self._task = asyncio.create_task(self._run())

    def proceed(self) -> None:
        if self.state != "waiting_user" or not self._continue:
            raise RuntimeError("Окно входа ещё не готово")
        self._continue.set()

    def cancel(self) -> bool:
        if not self.running or not self._task:
            return False
        self._task.cancel()  # закроет браузер через finally
        self.state = "idle"
        return True

    async def _run(self) -> None:
        from playwright.async_api import async_playwright

        from .hh import _make_tool

        try:
            tool = await asyncio.to_thread(_make_tool)
            api_client = tool.api_client

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=False)
                try:
                    page = await (await browser.new_context()).new_page()

                    loop = asyncio.get_running_loop()
                    code_future: asyncio.Future[str | None] = loop.create_future()

                    def handle_request(request) -> None:
                        # приложение hh для Android получает код через этот
                        # редирект; обычным браузером он не открывается
                        if request.url.startswith(f"{HH_ANDROID_SCHEME}://"):
                            if not code_future.done():
                                query = urlsplit(request.url).query
                                code = parse_qs(query).get("code", [None])[0]
                                code_future.set_result(code)

                    page.on("request", handle_request)

                    await page.goto(LOGIN_URL, timeout=60000)

                    # ждём, пока человек войдёт и выберет нужную роль
                    await self._continue.wait()
                    self.state = "finishing"

                    try:
                        await page.goto(
                            api_client.oauth_client.authorize_url,
                            timeout=60000,
                            wait_until="commit",
                        )
                    except Exception:
                        # редирект на hhandroid:// роняет навигацию — это норма
                        pass

                    code = await asyncio.wait_for(code_future, timeout=120)
                    if not code:
                        raise RuntimeError("hh.ru не выдал код авторизации")

                    token = await asyncio.to_thread(
                        api_client.oauth_client.authenticate, code
                    )
                    api_client.handle_access_token(token)
                    await asyncio.to_thread(tool.save_token)
                finally:
                    await browser.close()

            self.state = "done"
        except asyncio.CancelledError:
            self.state = "idle"
            raise
        except asyncio.TimeoutError:
            self.error = "hh.ru не ответил вовремя. Попробуй ещё раз."
            self.state = "error"
        except Exception as e:
            self.error = str(e)
            self.state = "error"


login_flow = LoginFlow()
