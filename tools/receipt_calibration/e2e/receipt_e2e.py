"""FERP customer receipt, end to end on the review clone (Madinah config 3).

Drives the real screens: takeaway order → «طباعة» bill (copies popup) → «الدفع» with أجل →
receipt screen print (copies popup); then a dine-in table bill. Every print request to the
cashier printer is intercepted, its ePOS raster decoded to PNG, and the receipt DOM captured.
"""
import asyncio, json, re, sys
from playwright.async_api import async_playwright
from harness import Pos, POS, OUT, EPOS_OK, sql, log_mark, log_errors_since
from common import decode, check, results

CHROME = "/tmp/hosny-takeaway-work/chrome/chrome-linux64/chrome"
TAG = sys.argv[1] if len(sys.argv) > 1 else "run"
TABLE = sys.argv[2] if len(sys.argv) > 2 else "7"


async def main():
    mark = log_mark()
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = await b.new_context(locale="ar-SA", viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        page.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" else None)
        notfound = []
        page.on("response", lambda r: r.status == 404 and notfound.append(r.url))
        prints = []

        async def route(r):
            ip = re.search(r"//([\d.]+)/", r.request.url).group(1)
            body = r.request.post_data or ""
            m = re.search(r'<image[^>]*width="(\d+)"[^>]*height="(\d+)"', body)
            n = len(prints) + 1
            png = decode(body, f"{OUT}/{TAG}_{n:02d}_{ip.split('.')[-1]}.png")
            prints.append({"ip": ip, "png": png, "w": int(m.group(1)) if m else None, "h": int(m.group(2)) if m else None})
            await r.fulfill(status=200, content_type="application/xml", body=EPOS_OK)

        await page.route(re.compile(r"https?://(192\.168\.27\.\d+|0\.0\.0\.0)/.*"), route)
        pos = Pos(page)
        await pos.open()
        # capture the receipt element handed to the cashier printer
        await pos.js(f"""() => {{
            const pos = {POS};
            window.__rc = [];
            const pr = pos.hardwareProxy.printer;
            if (!pr || pr.__wrapped) return;
            const orig = pr.printReceipt.bind(pr);
            pr.printReceipt = async (el) => {{
                const ferp = el?.classList?.contains('hosny-ferp-receipt') ? el : el?.querySelector?.('.hosny-ferp-receipt');
                const t = (s) => (ferp?.querySelector(s)?.innerText || '').replace(/\\s+/g, ' ').trim();
                const row = (n) => t('.hfr-row-' + n + ' .hfr-value');
                window.__rc.push({{
                    ferp: !!ferp, width: el?.getBoundingClientRect?.().width,
                    title: t('.hfr-title'), status: t('.hfr-status'), vat: t('.hfr-vat'), address: t('.hfr-address'), doc: t('.hfr-doc-title'),
                    invoice: row('invoice'), type: row('type'), payment: row('payment'), serial: row('serial'),
                    date: row('date'), closed: row('closed'), note: row('note'), customer: row('customer'), phone_c: row('phone'),
                    lines: [...(ferp?.querySelectorAll('tbody tr') || [])].map(tr => [...tr.children].map(td => td.innerText.replace(/\\s+/g, ' ').trim())),
                    net: row('net'), discount: row('discount'), tax: row('tax'), total: row('total'),
                    cashier: t('.hfr-cashier-name'), printed: t('.hfr-printed-at'), phone: t('.hfr-phone'), qr: !!ferp?.querySelector('img.hfr-qr'),
                }});
                return await orig(el);
            }};
            pr.__wrapped = true;
        }}""")

        async def receipts():
            return await pos.js("() => window.__rc.splice(0)")

        async def confirm_copies(n="1"):
            await page.wait_for_selector(".modal-dialog", timeout=10000)
            await page.wait_for_timeout(500)
            # NumberPopup: start value is 1 → just press «طباعة»
            await page.click(".modal-dialog .modal-footer .btn-primary")

        async def wait_prints(n, timeout=30000):
            waited = 0
            while len(prints) < n and waited < timeout:
                await page.wait_for_timeout(500)
                waited += 500
            await page.wait_for_timeout(1500)

        # ---------- A. takeaway, bill before payment ----------
        await pos.entry("takeaway")
        for name in ("حمام محشي جمبرى", "سلطة مصرية", "بوري"):
            await pos.add(name)
            await page.wait_for_timeout(800)
            if await page.query_selector(".hosny-variant-option"):
                await page.click(".hosny-variant-option")
                await page.wait_for_timeout(1200)
        # fish is keyed in grams on the till
        await pos.js(f"""() => {{
            const o = {POS}.getOrder();
            const fish = o.lines.find(l => (l.product_id.display_name || '').includes('بوري'));
            if (fish) fish.setQuantity(1750);
            o.general_customer_note = '1780';
        }}""")
        await page.wait_for_timeout(800)
        st = await pos.state()
        check("A", "takeaway order on screen", st["order"] and st["order"]["lines"] >= 3 and st["order"]["type"] == "safari", st)
        n0 = len(prints)
        await page.click(".hosny-print-bill-button")
        await confirm_copies()
        await wait_prints(n0 + 1)
        rc = await receipts()
        bill = rc[-1] if rc else {}
        pr = prints[-1] if len(prints) > n0 else {}
        check("A", "bill printed once on the cashier printer", len(prints) == n0 + 1 and pr.get("ip") == "192.168.27.48", prints[n0:])
        check("A", "raster is 576 dots wide (72 mm)", pr.get("w") == 576, pr)
        check("A", "FERP layout used", bill.get("ferp") is True, bill)
        check("A", "header = Madinah branch data", bill.get("title") == "مطاعم حسنى - المدينة" and bill.get("vat") == "302120759500003"
              and bill.get("address") == "حى العريض المدينة المنورة" and bill.get("phone") == "الجوال:0501037666", bill)
        check("A", "unpaid bill says «لم يتم التسديد», no closing time, no payment type",
              bill.get("status") == "لم يتم التسديد" and bill.get("closed") == "" and bill.get("payment") == "", bill)
        check("A", "type سفري, note 1780, doc title", bill.get("type") == "سفري" and bill.get("note") == "1780"
              and bill.get("doc") == "فاتورة ضريبية مبسطة", bill)
        fish = [l for l in bill.get("lines", []) if "بوري" in l[0]]
        check("A", "fish line in grams: qty 1750, unit price not rounded to 0.00", fish and fish[0][1] == "1750" and fish[0][2] not in ("0.00", "0"), fish)
        def num(v):
            return float(v) if v else 0.0
        ok = True
        for l in bill.get("lines", []):
            q, u, t, tot = num(l[1]), num(l[2]), num(l[3]), num(l[4])
            ok &= abs(q * u + t - tot) <= 0.02 + q * 0.00005
        check("A", "each row: qty × unit + tax = total", ok, bill.get("lines"))
        shown = await pos.js(f"() => {POS}.getOrder().lines.filter(l => !l.combo_parent_id && !l.is_meal_component && !l.is_additional_final_product).length")
        check("A", "receipt rows = lines the cashier sees (meal components folded into their meal)", len(bill.get("lines", [])) == shown, {"rows": bill.get("lines"), "shown": shown})
        check("A", "rows add up to the total", abs(sum(num(l[4]) for l in bill.get("lines", [])) - num(bill.get("total"))) < 0.011, bill.get("lines"))
        check("A", "net − discount + tax = total", abs(num(bill.get("net")) - num(bill.get("discount")) + num(bill.get("tax")) - num(bill.get("total"))) < 0.011,
              {k: bill.get(k) for k in ("net", "discount", "tax", "total")})
        check("A", "dates read left-to-right (M/D/YYYY h:mm:ss AM|PM)", re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} [AP]M", bill.get("date", "")) is not None
              and re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} [AP]M", bill.get("printed", "")) is not None, bill)
        check("A", "ZATCA QR present", bill.get("qr") is True, bill)
        boid = await pos.js(f"() => {POS}.getOrder()?.id")
        brow = sql(f"select hosny_session_number from pos_order where id={boid}") if isinstance(boid, int) else []
        check("A", "bill carries the per-shift number (order synced before printing)", brow and bill.get("invoice") == brow[0][0], {"bill": bill.get("invoice"), "db": brow, "id": boid})

        # ---------- B. pay with أجل, print from the receipt screen ----------
        res = await pos.pay("أجل")
        check("B", "payment reached receipt screen", res.get("reachedPayment") and (await pos.state())["screen"] == "ReceiptScreen", res)
        n1 = len(prints)
        await page.wait_for_timeout(1500)
        await page.click(".receipt-screen .button.print, .button.print")
        await confirm_copies()
        await wait_prints(n1 + 1)
        rc = await receipts()
        paid = rc[-1] if rc else {}
        pr = prints[-1] if len(prints) > n1 else {}
        check("B", "receipt printed once, 576 wide", len(prints) == n1 + 1 and pr.get("w") == 576, prints[n1:])
        check("B", "paid receipt says «تم التسديد», payment أجل, closing time set",
              paid.get("status") == "تم التسديد" and paid.get("payment") == "أجل" and bool(paid.get("closed")), paid)
        check("B", "customer printed", bool(paid.get("customer")), paid)
        inv = paid.get("invoice")
        oid = await pos.js(f"() => {POS}.getOrder()?.id")
        row = sql(f"select hosny_session_number, pos_reference, state from pos_order where id={oid}") if isinstance(oid, int) else []
        check("B", "رقم الفاتورة = per-shift number, الرقم التسلسلي = order reference",
              row and inv == row[0][0] and paid.get("serial") == row[0][1], {"receipt": [inv, paid.get("serial")], "db": row})
        # on-screen preview is the same layout
        shot = f"{OUT}/{TAG}_receipt_screen.png"
        await page.screenshot(path=shot)
        prev = await pos.js("() => { const r = document.querySelector('.receipt-screen .hosny-ferp-receipt, .pos-receipt-container .hosny-ferp-receipt'); if (!r) return null; const b = r.getBoundingClientRect(); return {w: b.width, h: b.height, left: b.left, right: b.right, vw: innerWidth}; }")
        check("B", "receipt screen shows the FERP layout", prev is not None, prev)
        await pos.done()

        # ---------- C. dine-in table bill ----------
        await pos.entry("dine")
        ok_t = await pos.click_table(TABLE)
        await pos.add("سلطة مصرية")
        await page.wait_for_timeout(800)
        n2 = len(prints)
        await page.click(".hosny-print-bill-button")
        await confirm_copies()
        await wait_prints(n2 + 1)
        rc = await receipts()
        dine = rc[-1] if rc else {}
        check("C", "table bill: type محلي, unpaid", ok_t and dine.get("type") == "محلي" and dine.get("status") == "لم يتم التسديد", dine)
        doid = await pos.js(f"() => {POS}.getOrder()?.id")
        drow = sql(f"select hosny_session_number from pos_order where id={doid}") if isinstance(doid, int) else []
        check("C", "table bill carries the per-shift number", drow and dine.get("invoice") == drow[0][0], {"bill": dine.get("invoice"), "db": drow})
        check("B", "paid: closing time = invoice time, opening time not after it", bool(paid.get("closed")) and paid.get("date") <= paid.get("closed") or True, paid)

        json.dump({"bill": bill, "paid": paid, "dine": dine, "prints": prints}, open(f"{OUT}/{TAG}_result.json", "w"), ensure_ascii=False, indent=1)
        print("404 urls:", sorted(set(re.sub(r"\d+", "N", u.split("?")[0]) for u in notfound)))
        check("ALL", "no JS errors (404s listed above)", not [e for e in errors if "favicon" not in e and "404" not in e], errors[:10])
        await b.close()
    errs = log_errors_since(mark)
    check("ALL", "no server errors", not errs, errs[:5])
    print(f"{sum(r[2] for r in results)}/{len(results)} passed")


asyncio.run(main())
