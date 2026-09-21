"""Management POC acceptance: editing inputs, navigation, Mondays and simulation netting."""

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
OUT = ROOT / "test-results/poc"
BASE = "http://127.0.0.1:8128"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td, (OUT / "server.log").open("w") as log:
        env = os.environ | {"PROCUREMENT_DB_URL": f"sqlite:///{td}/poc.db", "DATABRICKS_APP_PORT": "8128"}
        server = subprocess.Popen(
            [sys.executable, "run_poc.py"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
        )
        try:
            for _ in range(150):
                try:
                    with urllib.request.urlopen(BASE + "/api/config", timeout=2):
                        break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError("Serveur arrêté ; voir server.log")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Serveur indisponible")
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, channel="chromium")
                page = browser.new_page(viewport={"width": 1440, "height": 1050})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                for path in ["/referentiel", "/pdp", "/commandes", "/articles", "/articles/DEMO-001", "/parametres"]:
                    page.goto(BASE + path)
                    page.wait_for_load_state("networkidle")
                    page.screenshot(path=str(OUT / f"route-{path.split('/')[-1]}.png"), full_page=True)
                    expect(page.locator("main h1")).to_have_count(1)
                    expect(page.get_by_role("alert")).to_have_count(0)
                    assert page.locator("main p").count() == 0, (path, page.locator("main p").all_inner_texts())
                    expect(page.locator("aside svg, aside .brand")).to_have_count(0)
                page.goto(BASE + "/referentiel")
                page.get_by_role("tab", name="Nomenclatures (BOM)", exact=True).click()
                expect(page.get_by_label("Quantité par produit ligne 1", exact=True)).to_have_value("2")
                page.goto(BASE + "/commandes")
                date = page.get_by_label("Livraison ligne 2", exact=True)
                date.fill("2026-09-30")
                with page.expect_response(
                    lambda r: r.url.endswith("/api/poc/tables/orders") and r.request.method == "PUT"
                ) as saved:
                    page.get_by_role("button", name="Enregistrer", exact=True).click()
                assert saved.value.status == 200
                expect(date).to_have_value("2026-09-28")
                page.goto(BASE + "/pdp")
                page.get_by_label("Quantité ligne 2", exact=True).fill("400")
                with page.expect_response(
                    lambda r: r.url.endswith("/api/poc/tables/pdp") and r.request.method == "PUT"
                ) as saved:
                    page.get_by_role("button", name="Enregistrer", exact=True).click()
                assert saved.value.status == 200
                page.goto(BASE + "/articles/DEMO-001")
                for label in [
                    "Commandes & mouvements",
                    "Commandes simulées & ajustements saisis",
                    "Alertes",
                    "Données de base",
                ]:
                    page.get_by_role("tab", name=label, exact=True).click()
                    panel = page.get_by_role("tabpanel")
                    expect(panel).to_be_visible()
                    expect(panel).to_be_empty()
                page.get_by_role("tab", name="Tableau de simulation", exact=True).click()
                toolbar = page.get_by_role("toolbar", name="Simulation", exact=True)
                expect(toolbar).to_be_visible()
                with page.expect_response(lambda r: r.url.endswith("/api/cbn/run")) as response:
                    toolbar.get_by_role("button", name="Calcul CBN", exact=True).click()
                assert response.value.status == 200
                report = response.value.json()
                assert report["items"]
                proposal = report["items"][0]
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(OUT / "simulation-semaine.png"), full_page=True)
                toolbar.get_by_role("button", name="Jour", exact=True).click()
                page.wait_for_load_state("networkidle")
                with page.expect_download() as download:
                    toolbar.get_by_role("link", name="Excel", exact=True).click()
                download.value.save_as(OUT / "simulation.xlsx")
                # Place the firm order using the article's Saisir drawer.
                toolbar.get_by_role("button", name="Saisir", exact=True).click()
                page.get_by_label("Date de livraison attendue", exact=True).fill(proposal["delivery_date"])
                page.get_by_label("Quantité (PCE)", exact=True).fill(str(proposal["qty"]))
                comment = page.get_by_label("Commentaire", exact=True)
                comment.press_sequentially("Confirmation POC", delay=20)
                expect(comment).to_be_focused()
                with page.expect_response(
                    lambda r: r.url.endswith("/api/poc/tables/orders") and r.request.method == "PUT"
                ) as saved:
                    page.get_by_role("dialog").get_by_role("button", name="Enregistrer", exact=True).click()
                assert saved.value.status == 200
                expect(page.get_by_role("dialog")).to_have_count(0)
                page.wait_for_load_state("networkidle")
                projection = page.request.get(
                    BASE + "/api/articles/DEMO-001/projection?granularity=day&horizon_days=60"
                ).json()
                i = projection["periods"].index(proposal["delivery_date"])
                planned = next(s["values"] for s in projection["series"] if s["key"] == "supply_planned")
                # More than one proposal can share Monday: absorb only the confirmed amount.
                remaining = (
                    sum(p["qty"] for p in report["items"] if p["delivery_date"] == proposal["delivery_date"])
                    - proposal["qty"]
                )
                assert planned[i] == remaining
                page.screenshot(path=str(OUT / "simulation-jour.png"), full_page=True)
                page.goto(BASE + "/commandes")
                expect(page.locator("tbody tr")).to_have_count(3)
                page.screenshot(path=str(OUT / "commandes.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                page.get_by_role("button", name="Menu", exact=True).click()
                expect(page.locator("aside.open")).to_be_visible()
                page.get_by_role("link", name="Fiches articles", exact=True).click()
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(OUT / "mobile.png"), full_page=True)
                assert not errors, errors
                (OUT / "result.json").write_text(
                    json.dumps(
                        {
                            "routes": 6,
                            "errors": errors,
                            "forecast_monday": "passed",
                            "pdp_edit": "passed",
                            "empty_tabs": 4,
                            "cbn": "passed",
                            "firm_reconciliation": "passed",
                            "excel_download": "passed",
                            "keyboard": "passed",
                            "mobile": "passed",
                        },
                        indent=2,
                    )
                )
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
