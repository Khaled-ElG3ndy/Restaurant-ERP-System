"""Render the FERP receipt with the photographed slip's data through the POS's own htmlToCanvas,
measure every element's ink, compare with the FERP ink boxes (canvas px), optionally auto-adjust spec.json.

usage: calibrate.py [iterations] [--no-adjust] [--only key,key]
"""
import asyncio, json, sys, base64, io, os, copy
import numpy as np
from PIL import Image
from playwright.async_api import async_playwright
import ferp_css

BASE = os.environ.get("BASE", "http://127.0.0.1:18105")
CHROME = "/tmp/hosny-takeaway-work/chrome/chrome-linux64/chrome"
OUT = "/tmp/hosny-receipt-work/calib/out"
os.makedirs(OUT, exist_ok=True)
SP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ferp")
T = json.load(open(f"{SP}/ferp_canvas.json"))
T.update(json.load(open(f"{SP}/ferp_table.json")))

FERP_DATA = {
    "title": "مطاعم حسنى - المدينة", "status": "تم التسديد", "vat": "302120759500003",
    "address": "حى العريض المدينة المنورة", "docTitle": "فاتورة ضريبية مبسطة",
    "invoiceNumber": "160", "orderType": "سفري", "paymentType": "اجل", "serial": "158558",
    "date": "0/2/2026 10:58:42 PM", "closedAt": "0/2/2026 10:58:42 PM", "note": "1780",
    "customer": "تطبيق كيتا المدينه", "customerPhone": "0581626041",
    "lines": [
        {"key": "1", "name": "نصف دجاجة على الفحم", "details": [], "qty": "1", "unit": "20.87", "tax": "3.13", "total": "24.00"},
        {"key": "2", "name": "كفتة شامى 1/4", "details": [], "qty": "1", "unit": "35.65", "tax": "5.35", "total": "41.00"},
        {"key": "3", "name": "مشكل حسنى (كفتة واوصال) 1/3", "details": [], "qty": "1", "unit": "46.96", "tax": "7.04", "total": "54.00"},
        {"key": "4", "name": "ورقة لحمة بالبطاطس", "details": [], "qty": "1", "unit": "40.00", "tax": "6.00", "total": "46.00"},
        {"key": "5", "name": "طاجن خضار مشكل باللحم الضانى", "details": [], "qty": "1", "unit": "30.43", "tax": "4.57", "total": "35.00"},
        {"key": "6", "name": "ملوخية بالدجاج", "details": [], "qty": "1", "unit": "25.22", "tax": "3.78", "total": "29.00"},
    ],
    "net": "199.13", "discount": "0.00", "tax": "29.87", "total": "229.00",
    "cashier": "ahmed", "printedAt": "10/2/2026 10:58:44 PM", "phone": "0501037666",
}

R = ".hosny-ferp-receipt"
# element key -> (selector, ink mode, which measures are trusted: x, w, y, h)
ELEMS = {
    "logo": (".hfr-logo", "dark", "xwyh"),
    "title": (".hfr-title > span", "dark", "xwyh"),
    "paid": (".hfr-status > span", "dark", "xwyh"),
    "vat_label": (".hfr-vat-label", "dark", "xwyh"),
    "vat": (".hfr-vat > span", "dark", "xwyh"),
    "address": (".hfr-address > span", "dark", "xwyh"),
    "simplified": (".hfr-doc-title > span", "dark", "xwyh"),
    "l_invno": (".hfr-row-invoice .hfr-label", "dark", "xwyh"),
    "l_type": (".hfr-row-type .hfr-label", "dark", "xwyh"),
    "l_pay": (".hfr-row-payment .hfr-label", "dark", "xwyh"),
    "l_serial": (".hfr-row-serial .hfr-label", "dark", "xwyh"),
    "l_date": (".hfr-row-date .hfr-label", "dark", "xwyh"),
    "l_close": (".hfr-row-closed .hfr-label", "dark", "xwyh"),
    "l_note": (".hfr-row-note .hfr-label", "dark", "xwyh"),
    "l_cust": (".hfr-row-customer .hfr-label", "dark", "xwyh"),
    "l_phone": (".hfr-row-phone .hfr-label", "dark", "xwyh"),
    "v_invno": (".hfr-row-invoice .hfr-value > span", "dark", "xwyh"),
    "v_type": (".hfr-row-type .hfr-value > span", "dark", "xwyh"),
    "v_pay": (".hfr-row-payment .hfr-value > span", "dark", "xwyh"),
    "v_serial": (".hfr-row-serial .hfr-value > span", "dark", "xwyh"),
    "v_date": (".hfr-row-date .hfr-value > span", "dark", "xwyh"),
    "v_close": (".hfr-row-closed .hfr-value > span", "dark", "xwyh"),
    "v_note": (".hfr-row-note .hfr-value > span", "dark", "xwyh"),
    "v_cust": (".hfr-row-customer .hfr-value > span", "dark", "xwyh"),
    "v_phone": (".hfr-row-phone .hfr-value > span", "dark", "xwyh"),
    "th_name": ("thead .hfr-c-name", "dark", "xwyh"),
    "th_qty": ("thead .hfr-c-qty", "dark", "xwyh"),
    "th_unit": ("thead .hfr-c-unit", "dark", "xwyh"),
    "th_tax": ("thead .hfr-c-tax", "dark", "xwyh"),
    "th_total": ("thead .hfr-c-total", "dark", "xwyh"),
    "r1_name": ("tbody tr:nth-child(1) .hfr-c-name", "dark", "xwyh"),
    "r1_qty": ("tbody tr:nth-child(1) .hfr-c-qty", "dark", "xwyh"),
    "r1_unit": ("tbody tr:nth-child(1) .hfr-c-unit", "dark", "xwyh"),
    "r1_tax": ("tbody tr:nth-child(1) .hfr-c-tax", "dark", "xwyh"),
    "r1_total": ("tbody tr:nth-child(1) .hfr-c-total", "dark", "xwyh"),
    "r2_name": ("tbody tr:nth-child(2) .hfr-c-name", "dark", "xwyh"),
    "r2_unit": ("tbody tr:nth-child(2) .hfr-c-unit", "dark", "xwyh"),
    "r3_name": ("tbody tr:nth-child(3) .hfr-c-name", "dark", "xwyh"),
    "r3_unit": ("tbody tr:nth-child(3) .hfr-c-unit", "dark", "xwyh"),
    "r4_name": ("tbody tr:nth-child(4) .hfr-c-name", "dark", "xwyh"),
    "r5_name": ("tbody tr:nth-child(5) .hfr-c-name", "dark", "xwyh"),
    "r6_name": ("tbody tr:nth-child(6) .hfr-c-name", "dark", "xwy"),
    "l_net": (".hfr-row-net .hfr-label", "dark", "xwyh"),
    "v_net": (".hfr-row-net .hfr-value > span", "dark", "xwyh"),
    "l_disc": (".hfr-row-discount .hfr-label", "dark", "xwyh"),
    "v_disc": (".hfr-row-discount .hfr-value > span", "dark", "xwyh"),
    "l_vat": (".hfr-row-tax .hfr-label", "dark", "xwyh"),
    "v_vat": (".hfr-row-tax .hfr-value > span", "dark", "xwyh"),
    "l_total": (".hfr-row-total .hfr-label", "dark", "xwyh"),
    "v_total": (".hfr-row-total .hfr-value > span", "dark", "xwyh"),
    "l_cashier": (".hfr-cashier .hfr-label", "dark", "xwyh"),
    "v_cashier": (".hfr-cashier-name > span", "dark", "xwyh"),
    "v_printed": (".hfr-printed-at > span", "dark", "xw"),
    "phone": (".hfr-phone", "dark", "xw"),
    "qr": (".hfr-qr", "dark", "xwyh"),
}


async def render(page, css):
    return await page.evaluate("""async ([css, data, elems]) => {
        const M = (n) => odoo.loader.modules.get(n);
        const { renderToElement } = M('@web/core/utils/render');
        const { htmlToCanvas } = M('@point_of_sale/app/services/render_service');
        const { loadReceiptFonts } = M('@hosny_pos_receipt/js/ferp_receipt');
        const pos = odoo.__WOWL_DEBUG__.root.env.services.pos;
        let st = document.getElementById('calib-css');
        if (!st) { st = document.createElement('style'); st.id = 'calib-css'; document.head.appendChild(st); }
        st.textContent = css;
        await loadReceiptFonts();
        const r = Object.assign({}, data, { logoUrl: pos.config.receiptLogoUrl });
        if (!window.__qr) {
            const { computeSAQRCode } = M('@l10n_sa_pos/app/utils/qr');
            const v = computeSAQRCode(data.title, data.vat, luxon.DateTime.now(), '229.00', '29.87');
            const svg = new window.ZXing.BrowserQRCodeSvgWriter().write(v, 240, 240);
            window.__qr = 'data:image/svg+xml;base64,' + btoa(new XMLSerializer().serializeToString(svg));
        }
        r.qrCode = window.__qr;
        const { Component, useRef } = owl;
        class Probe extends Component {
            static template = 'hosny_pos_receipt.FerpReceiptBody';
            static props = ['r'];
            setup() { this.ferpRoot = useRef('ferpRoot'); }
            get r() { return this.props.r; }
        }
        const renderer = odoo.__WOWL_DEBUG__.root.env.services.renderer;
        const mk = async () => (await renderer.toHtml(Probe, { r })).cloneNode(true);
        const probe = await mk(); probe.classList.add('pos-receipt-print');
        document.querySelector('.render-container').appendChild(probe);
        await new Promise((res) => setTimeout(res, 300));
        const root = probe.getBoundingClientRect(); const boxes = {};
        for (const [k, s] of Object.entries(elems)) {
            const el = probe.querySelector(s);
            if (!el) { boxes[k] = null; continue; }
            if (s.endsWith('> span')) {
                const sb = el.getBoundingClientRect(); const pb = el.parentElement.getBoundingClientRect();
                boxes[k] = [sb.left - root.left - 6, sb.right - root.left + 6, sb.top - root.top - 6, sb.bottom - root.top + 6];
                continue;
            }
            const b = el.getBoundingClientRect(); const cs = getComputedStyle(el);
            const pl = parseFloat(cs.paddingLeft) || 0, pr = parseFloat(cs.paddingRight) || 0;
            const pt = el.tagName === 'TD' || el.tagName === 'TH' ? 0 : (parseFloat(cs.paddingTop) || 0);
            boxes[k] = [b.left - root.left + pl, b.right - root.left - pr, b.top - root.top + pt, b.bottom - root.top];
        }
        boxes._w = root.width; boxes._h = root.height; probe.remove();
        let canvas;
        for (let i = 0; i < 2; i++) canvas = await htmlToCanvas(await mk(), { addClass: 'pos-receipt-print' });
        return { boxes, png: canvas.toDataURL('image/png'), w: canvas.width, h: canvas.height };
    }""", [css, FERP_DATA, {k: v[0] for k, v in ELEMS.items()}])


def ink_box(img, box, mode):
    x0, x1, y0, y1 = [int(round(v)) for v in box]
    pad = 2 if mode != "cell" else 4
    sub = img[max(0, y0 + pad):y1 - pad, max(0, x0 + pad):x1 - pad]
    m = sub < 128
    ys, xs = np.nonzero(m)
    if not len(ys):
        return None
    return (x0 + pad + xs.min(), x0 + pad + xs.max() + 1, y0 + pad + ys.min(), y0 + pad + ys.max() + 1)


def measure(res):
    img = np.array(Image.open(io.BytesIO(base64.b64decode(res["png"].split(",")[1]))).convert("L")).astype(int)
    Image.fromarray(img.astype(np.uint8)).save(f"{OUT}/calib.png")
    found = {}
    for k, (sel, mode, trust) in ELEMS.items():
        b = res["boxes"].get(k)
        if not b:
            continue
        cell = sel.startswith(("thead", "tbody"))
        ib = ink_box(img, b, "cell" if cell else mode)
        if ib:
            found[k] = ib
    return img, found


def report(found):
    errs = []
    print("%-10s %-27s %-27s %s" % ("elem", "ours x0-x1 / y0-y1", "FERP", "dx0 dx1 dy0 dy1 | w/h ratio"))
    for k, (sel, mode, trust) in ELEMS.items():
        if k not in found or k not in T:
            print(f"{k:10s} --missing--")
            continue
        o = found[k]; f = T[k]
        d = [o[0] - f[0], o[1] - f[1], o[2] - f[2], o[3] - f[3]]
        wr = (o[1] - o[0]) / max(1, f[1] - f[0]); hr = (o[3] - o[2]) / max(1, f[3] - f[2])
        for i, c in enumerate("xxyy"):
            if (c == "x" and "x" in trust) or (c == "y" and i == 2 and "y" in trust) or (c == "y" and i == 3 and "h" in trust):
                errs.append(abs(d[i]))
        print("%-10s %4d-%4d %6.0f-%6.0f   %5.0f-%5.0f %6.0f-%6.0f   %+5.0f %+5.0f %+5.0f %+5.0f | %.2f %.2f" % (
            k, o[0], o[1], o[2], o[3], f[0], f[1], f[2], f[3], *d, wr, hr))
    print("mean |d| = %.1f  max = %.1f  n=%d" % (np.mean(errs), np.max(errs), len(errs)))
    return np.mean(errs)


async def main():
    iters = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
    adjust = "--no-adjust" not in sys.argv
    import adjust as adj
    spec = ferp_css.load()
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = await b.new_context(locale="ar-SA", viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()
        await page.goto(BASE + "/web/login"); await page.fill("input[name=login]", "1")
        await page.fill("input[name=password]", "claudetest123"); await page.click("button[type=submit]")
        await page.wait_for_load_state("domcontentloaded")
        await page.goto(BASE + "/pos/ui?config_id=3", wait_until="domcontentloaded")
        await page.wait_for_selector(".pos", timeout=180000)
        await page.wait_for_function("() => { try { return !!odoo.__WOWL_DEBUG__.root.env.services.pos.config; } catch (e) { return false; } }", timeout=180000)
        await page.wait_for_timeout(3000)
        for it in range(iters):
            res = await render(page, "" if "--bundle" in sys.argv else ferp_css.render(spec))
            img, found = measure(res)
            json.dump({k: [int(x) for x in v] for k, v in found.items()}, open(f"{OUT}/found.json", "w"))
            band = img[:, 440:560] < 128
            rows_dark = np.nonzero(band.mean(1) > 0.9)[0]
            groups = []
            for y in rows_dark:
                if groups and y - groups[-1][-1] <= 1: groups[-1].append(y)
                else: groups.append([y])
            print("table lines:", [round((g[0] + g[-1]) / 2, 1) for g in groups], " FERP: [1035.2, 1100.1, 1153.2, 1197.4, 1249.5, 1291.8, 1342.9, 1387.1]")
            print(f"--- iteration {it}  canvas {res['w']}x{res['h']}")
            report(found)
            if adjust and it < iters - 1:
                spec = adj.step(spec, found, T)
                ferp_css.save(spec)
        await b.close()

if __name__ == "__main__":
    asyncio.run(main())
