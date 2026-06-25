from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


_SSO_LOGIN_URL_TEMPLATE_ENV = "HUST_SSO_LOGIN_URL_TEMPLATE"


def _sso_login_url_template() -> str:
    template = os.getenv(_SSO_LOGIN_URL_TEMPLATE_ENV, "").strip()
    if not template:
        raise RuntimeError(f"{_SSO_LOGIN_URL_TEMPLATE_ENV} is not configured")
    if "{encoded_email}" not in template:
        raise RuntimeError(f"{_SSO_LOGIN_URL_TEMPLATE_ENV} must include {{encoded_email}}")
    return template


def _is_success_url(url: str) -> bool:
    if "sso_reload=true" in url:
        return True

    parsed = urlparse(url)
    return parsed.netloc == "login.microsoftonline.com" and parsed.path == "/login.srf"


def check_login(username: str, password: str) -> bool:
    encoded_username = username.replace("@", "%40")
    login_url = _sso_login_url_template().format(encoded_email=encoded_username)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            logger.info("Starting HUST SSO login for username=%s", username)
            page = browser.new_page()
            page.goto(login_url)
            logger.info("HUST SSO password page loaded for username=%s url=%s", username, page.url)
            page.get_by_role("textbox", name="Password").fill(password)
            page.get_by_text("Sign in", exact=True).click()
            page.wait_for_load_state("networkidle")
            current_url = page.url
            ok = _is_success_url(current_url)
            logger.info(
                "HUST SSO login finished for username=%s ok=%s final_url=%s",
                username,
                ok,
                current_url,
            )
            return ok
        except Exception:
            logger.exception("HUST SSO login failed for username=%s", username)
            raise
        finally:
            browser.close()


__all__ = ["check_login"]
