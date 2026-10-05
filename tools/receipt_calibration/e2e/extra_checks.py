import asyncio, re, json, time
from playwright.async_api import async_playwright
from harness import Pos, POS, EPOS_OK
CHROME = "/tmp/hosny-takeaway-work/chrome/chrome-linux64/chrome"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        page = await (await b.new_context(locale="ar-SA", viewport={"width": 1400, "height": 900})).new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        async def route(r): await r.fulfill(status=200, content_type="application/xml", body=EPOS_OK)
        await page.route(re.compile(r"https?://(192\.168\.27\.\d+|0\.0\.0\.0)/.*"), route)
        pos = Pos(page); await pos.open()
        await pos.entry("takeaway")
        await pos.add("سلطة مصرية"); await page.wait_for_timeout(800)
        res = await pos.js(f"""async () => {{
            const pos = {POS};
            const M = (n) => odoo.loader.modules.get(n);
            const {{ OrderReceipt }} = M('@point_of_sale/app/screens/receipt_screen/receipt/order_receipt');
            const {{ buildFerpReceipt }} = M('@hosny_pos_receipt/js/ferp_receipt');
            const order = pos.getOrder();
            const out = {{}};
            // 1) gift / basic receipt keeps Odoo's own layout
            const basic = await pos.env.services.renderer.toHtml(OrderReceipt, {{ order, basic_receipt: true }});
            out.basicIsCore = !!basic && !basic.classList.contains('hosny-ferp-receipt') && basic.classList.contains('pos-receipt');
            // 2) negative quantity (refund-like line) formats with a minus sign
            const line = order.lines[0];
            line.setQuantity(-2);
            const neg = buildFerpReceipt(order, pos);
            out.neg = {{ row: neg.lines[0], net: neg.net, tax: neg.tax, total: neg.total }};
            line.setQuantity(1);
            // 3) print time of one bill through the real printer path (ePOS intercepted)
            const t0 = performance.now();
            await pos.printReceipt({{ order, printBillActionTriggered: true }});
            out.printMs = Math.round(performance.now() - t0);
            const t1 = performance.now();
            await pos.printReceipt({{ order, printBillActionTriggered: true }});
            out.printMs2 = Math.round(performance.now() - t1);
            const t2 = performance.now();
            await pos.printReceipt({{ order, basic: true, printBillActionTriggered: true }});
            out.basicPrintMs = Math.round(performance.now() - t2);
            const t3 = performance.now();
            await pos.printReceipt({{ order, printBillActionTriggered: true }});
            out.printMs3 = Math.round(performance.now() - t3);
            return out;
        }}""")
        print(json.dumps(res, ensure_ascii=False, indent=1))
        print("page errors:", errors[:5])
        await b.close()
asyncio.run(main())
