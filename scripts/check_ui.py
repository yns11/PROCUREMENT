"""Optional browser smoke test. Run after installing requirements-dev and Chromium.
python -m playwright install chromium
python -m scripts.check_ui
Set CHROMIUM_EXECUTABLE for an already-installed Chromium.
"""
import atexit
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    with tempfile.TemporaryDirectory() as tmp:
        env={**os.environ,'APP_MODE':'demo','DATABRICKS_APP_PORT':'8099','DATABASE_URL':'sqlite:///'+str(Path(tmp)/'ui.db')}
        process=subprocess.Popen(['python','run.py'],env=env,stdout=subprocess.DEVNULL)
        atexit.register(process.terminate)
        try:
            for _ in range(100):
                try:urllib.request.urlopen('http://127.0.0.1:8099/health');break
                except OSError:time.sleep(.1)
            with sync_playwright() as p:
                executable=os.getenv('CHROMIUM_EXECUTABLE')
                browser=p.chromium.launch(**({'executable_path':executable} if executable else {}),args=['--no-sandbox','--disable-dev-shm-usage'])
                page=browser.new_page(viewport={'width':1512,'height':1100});errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto('http://127.0.0.1:8099');page.wait_for_selector('.stats')
                page.locator('nav [data-page="orders"]').click()
                page.locator('[data-accept]').first.click();page.locator('#modal-submit').click()
                page.wait_for_selector('#modal',state='hidden')
                page.locator('nav [data-page="simulation"]').click();page.locator('#grain').select_option('week')
                assert page.locator('tbody tr').count()>0
                page.locator('nav [data-page="data"]').click();page.locator('[data-edit="items:0"]').click()
                page.locator('[name="name"]').fill('Composant de recette');page.locator('#modal-submit').click()
                page.wait_for_selector('#modal',state='hidden')
                page.locator('nav [data-page="history"]').click();page.wait_for_selector('[data-restore]')
                page.set_viewport_size({'width':390,'height':844});page.locator('nav [data-page="cockpit"]').click()
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                assert not errors,errors
                browser.close()
                print('Parcours navigateur validés.')
        finally:
            process.terminate();process.wait(timeout=10)

if __name__=='__main__':main()
