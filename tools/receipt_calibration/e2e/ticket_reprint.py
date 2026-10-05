"""Reprint from the orders list («الطلبات» / TicketScreen → «طباعة الإيصال»), fresh POS session:
a PAID order loaded from the server, an UNPAID table order, and a cash order paid in this session."""
import asyncio, re, sys, json
from playwright.async_api import async_playwright
from harness import Pos, POS, OUT, EPOS_OK
from common import decode, check, results

CHROME = "/tmp/hosny-takeaway-work/chrome/chrome-linux64/chrome"
PAID_REF, UNPAID_REF = sys.argv[1], sys.argv[2]

FIND_TS = """() => {
    const walk = (n) => { if (!n) return null; if (n.component?.constructor?.name === 'TicketScreen') return n.component;
        for (const c of Object.values(n.children || {})) { const r = walk(c); if (r) return r; } return null; };
    return walk(odoo.__WOWL_DEBUG__.root.__owl__);
}"""


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        page = await (await b.new_context(locale="ar-SA", viewport={"width": 1400, "height": 900})).new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        prints = []

        async def route(r):
            body = r.request.post_data or ""
            m = re.search(r'<image[^>]*width="(\d+)"', body)
            prints.append({"ip": re.search(r"//([\d.]+)/", r.request.url).group(1), "w": int(m.group(1)) if m else None,
                           "png": decode(body, f"{OUT}/reprint_{len(prints) + 1:02d}.png")})
            await r.fulfill(status=200, content_type="application/xml", body=EPOS_OK)

        await page.route(re.compile(r"https?://(192\.168\.27\.\d+|0\.0\.0\.0)/.*"), route)
        pos = Pos(page)
        await pos.open()
        await pos.js(f"""() => {{
            window.__rc = [];
            const pr = {POS}.hardwareProxy.printer; const orig = pr.printReceipt.bind(pr);
            pr.printReceipt = async (el) => {{
                const f = el.classList.contains('hosny-ferp-receipt') ? el : el.querySelector('.hosny-ferp-receipt');
                const t = (s) => (f?.querySelector(s)?.innerText || '').replace(/\\s+/g, ' ').trim();
                window.__rc.push({{ ferp: !!f, status: t('.hfr-status'), payment: t('.hfr-row-payment .hfr-value'),
                    serial: t('.hfr-row-serial .hfr-value'), invoice: t('.hfr-row-invoice .hfr-value'),
                    customer: t('.hfr-row-customer .hfr-value'), date: t('.hfr-row-date .hfr-value'),
                    closed: t('.hfr-row-closed .hfr-value'), total: t('.hfr-row-total .hfr-value'), rows: f?.querySelectorAll('tbody tr').length }});
                return await orig(el);
            }};
        }}""")

        async def reprint(ref, filt):
            await pos.js(f"() => {POS}.navigate('TicketScreen')")
            await page.wait_for_timeout(3000)
            await pos.js(f"async (f) => {{ const ts = ({FIND_TS})(); await ts.onFilterSelected(f); }}", filt)
            await page.wait_for_timeout(4000)
            rows = page.locator(".ticket-screen .order-row")
            n = await rows.count()
            target = None
            for i in range(n):
                if ref in (await rows.nth(i).inner_text()):
                    target = rows.nth(i)
                    break
            if not target:
                return {"error": f"row {ref} not found in {n} rows"}
            await target.click()
            await page.wait_for_timeout(1500)
            before = len(prints)
            btns = await pos.js("() => [...document.querySelectorAll('.ticket-screen button')].map(b => (b.className + ' | ' + b.innerText.trim()).slice(0, 120))")
            await page.screenshot(path=f"{OUT}/ticket_{filt}.png")
            btn = page.locator(".ticket-screen button:has(.fa-print)")
            if not await btn.count():
                return {"error": "no print button", "buttons": btns}
            await btn.first.click()
            for _ in range(40):
                if len(prints) > before:
                    break
                await page.wait_for_timeout(500)
            await page.wait_for_timeout(1500)
            rc = await pos.js("() => window.__rc.splice(0)")
            return {"receipt": rc[-1] if rc else None, "print": prints[-1] if len(prints) > before else None, "n": len(prints) - before}

        r = await reprint(PAID_REF, "SYNCED")
        rc = r.get("receipt") or {}
        check("paid", "reprint of a PAID order loaded from the server: FERP layout, «تم التسديد», 576 dots",
              rc.get("ferp") and rc.get("status") == "تم التسديد" and (r.get("print") or {}).get("w") == 576 and r.get("n") == 1, r)
        check("paid", "paid details survive the reload (payment أجل, customer, closing time, serial)",
              rc.get("payment") == "أجل" and rc.get("customer") and rc.get("closed") and rc.get("serial") == PAID_REF, rc)

        r = await reprint(UNPAID_REF, "ACTIVE_ORDERS")
        rc = r.get("receipt") or {}
        check("unpaid", "reprint of an UNPAID order from the list: «لم يتم التسديد», no closing time",
              rc.get("ferp") and rc.get("status") == "لم يتم التسديد" and rc.get("closed") == "" and r.get("n") == 1, r)

        print("page errors:", errors[:5])
        print(f"{sum(x[2] for x in results)}/{len(results)} passed")
        await b.close()

asyncio.run(main())
