"""Render screenshots of dados and memory pages with backend running."""
import asyncio, os, json, csv, subprocess, time
from playwright.async_api import async_playwright

TOKEN = "demo-token-for-render"
TENANT = "default"

async def shoot():
    # Start server with known secret
    env = os.environ.copy()
    env["JWT_SECRET"] = "render-secret-key-12345678901234567890"
    proc = subprocess.Popen(
        ["python3", "web/server.py"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env
    )
    await asyncio.sleep(4)
    try:
        # Get valid token
        import urllib.request
        req = urllib.request.Request("http://localhost:8123/api/auth/login",
                                    data=json.dumps({"email": "admin@empire.local", "password": "empire"}).encode(),
                                    headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        token = data["access_token"]

        # Pre-seed: upload CSV + index
        with open("/tmp/leads.csv", "w") as f:
            w = csv.writer(f)
            w.writerow(["nome", "email", "telefone", "cargo", "empresa", "porte", "mrr"])
            w.writerow(["Carlos Souza", "carlos@vercel.com", "+5511911112222", "CTO", "Vercel", "200", "8000"])
            w.writerow(["Ana Lima", "ana@stripe.com", "+5511922223333", "CEO", "Stripe", "500", "15000"])
            w.writerow(["Pedro Costa", "pedro@github.com", "+5511933334444", "Head of Growth", "GitHub", "1500", "12000"])
        with open("/tmp/leads.csv", "rb") as f:
            req = urllib.request.Request(
                "http://localhost:8123/api/data/upload",
                data=f.read(),
                headers={"Authorization": f"Bearer {token}", "X-Tenant": TENANT, "Content-Type": "text/csv"}
            )
            req.add_header("Content-Disposition", 'form-data; name="file"; filename="leads.csv"')
            # Simpler: use multipart
            import http.client
            boundary = "----formboundaryempire123"
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="leads.csv"\r\n'
                f"Content-Type: text/csv\r\n\r\n"
            ).encode() + open("/tmp/leads.csv", "rb").read() + f"\r\n--{boundary}--\r\n".encode()
            conn = http.client.HTTPConnection("localhost", 8123)
            conn.request("POST", "/api/data/upload", body,
                         {"Authorization": f"Bearer {token}", "X-Tenant": TENANT,
                          "Content-Type": f"multipart/form-data; boundary={boundary}"})
            r = conn.getresponse()
            print(f"  upload: {r.status}")
            ds = json.loads(r.read())
            ds_id = ds.get("id")

            # Index
            if ds_id:
                conn.request("POST", f"/api/data/datasets/{ds_id}/index", "",
                             {"Authorization": f"Bearer {token}", "X-Tenant": TENANT})
                r = conn.getresponse()
                print(f"  index: {r.status}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu",
            ])
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                device_scale_factor=2,
            )
            await ctx.add_init_script(f"""
                localStorage.setItem('empire.token', '{token}');
                localStorage.setItem('empire.tenant', 'default');
                localStorage.setItem('empire.user', JSON.stringify({{email: 'admin@empire.local', role: 'admin'}}));
            """)

            for html, name in [
                ("dados.html", "dados"),
                ("memory.html", "memory"),
            ]:
                page = await ctx.new_page()
                await page.goto(f"file:///workspace/ai-empire/web/premium/{html}",
                                wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(2000)
                await page.evaluate("() => new Promise(r => setTimeout(r, 1000))")
                await page.screenshot(path=f"/workspace/ai-empire/web/premium/screenshot-{name}.png", full_page=True)
                await page.screenshot(path=f"/workspace/ai-empire/web/premium/screenshot-{name}-vp.png", full_page=False)
                await page.close()
                print(f"  {name}: done")
            await browser.close()
    finally:
        proc.terminate()
        proc.wait()

asyncio.run(shoot())
