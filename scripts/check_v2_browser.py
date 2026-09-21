"""Real-browser acceptance on synthetic data, desktop and mobile. Requires Playwright Chromium."""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory() as td:
        env = os.environ | {
            "PROCUREMENT_MODE": "demo",
            "PROCUREMENT_DATA_SOURCE": "local",
            "PROCUREMENT_DB_URL": "sqlite:///" + td + "/ui.db",
            "DATABRICKS_APP_PORT": "8128",
        }
        server = subprocess.Popen(
            [sys.executable, "run.py"],
            cwd=ROOT,
            env=env,
            stdout=open(Path(td) / "server.log", "w"),
            stderr=subprocess.STDOUT,
        )
        try:
            for _ in range(80):
                try:
                    urllib.request.urlopen("http://localhost:8128/api/health")
                    break
                except OSError:
                    time.sleep(0.1)
            with sync_playwright() as pw:
                args = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
                if os.getenv("CHROMIUM_PATH"):
                    args["executable_path"] = os.environ["CHROMIUM_PATH"]
                browser = pw.chromium.launch(**args)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                for path in [
                    "/",
                    "/articles",
                    "/articles/DEMO-001",
                    "/propositions",
                    "/simulation",
                    "/saisies",
                    "/imports",
                    "/referentiel",
                    "/parametres",
                ]:
                    page.goto("http://localhost:8128" + path)
                    page.wait_for_load_state("networkidle")
                    assert page.locator("main h1").count(), path
                    assert page.locator("body").inner_text().find("Erreur interne") < 0, path
                    assert page.get_by_role("alert").count() == 0, path
                page.goto("http://localhost:8128/saisies")
                page.get_by_role("button", name="Nouvelle saisie", exact=True).click()
                comment = page.get_by_label("Commentaire", exact=True)
                comment.press_sequentially("Vérification du focus clavier", delay=30)
                expect(comment).to_have_value("Vérification du focus clavier")
                expect(comment).to_be_focused()
                page.keyboard.press("Escape")
                expect(page.get_by_role("dialog")).to_have_count(0)
                page.goto("http://localhost:8128/propositions")
                page.get_by_role("button", name="Calcul CBN", exact=False).click()
                page.wait_for_timeout(1000)
                assert page.get_by_text("Résultat du dernier Calcul CBN").count()
                page.get_by_role("button", name="Accepter", exact=True).first.click()
                page.wait_for_timeout(600)
                assert page.get_by_text("Acceptée", exact=True).count()
                page.goto("http://localhost:8128/")
                page.wait_for_load_state("networkidle")
                out = ROOT / "test-results"
                out.mkdir(exist_ok=True)
                page.screenshot(path=str(out / "cockpit-desktop.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                page.reload()
                page.wait_for_load_state("networkidle")
                page.get_by_role("button", name="Menu", exact=True).click()
                assert page.locator(".sidebar.open").is_visible()
                page.screenshot(path=str(out / "cockpit-mobile.png"), full_page=True)
                assert not errors, errors
                (out / "browser.json").write_text(
                    json.dumps(
                        {
                            "routes": 9,
                            "javascript_errors": errors,
                            "cbn": "passed",
                            "acceptance": "passed",
                            "mobile_navigation": "passed",
                            "drawer_keyboard": "passed",
                        },
                        indent=2,
                    )
                )
                print((out / "browser.json").read_text())
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
