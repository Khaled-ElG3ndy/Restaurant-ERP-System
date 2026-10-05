"""Print the photographed FERP slip's own data through the real cashier printer object
(EpsonPrinter.printReceipt → htmlToCanvas → Floyd–Steinberg → ePOS), intercept the request
to 192.168.27.48 and decode the raster exactly as the printer would receive it.

usage: ferp_print.py <out.png> [clipped]   (clipped = FERP's cut-off date «0/2/2026», for measuring)
"""
import asyncio, re, sys, json
from playwright.async_api import async_playwright
from harness import Pos, POS, EPOS_OK
from common import decode

sys.path.insert(0, "/opt/Hosney-Pos/tools/receipt_calibration")
from calibrate import FERP_DATA

CHROME = "/tmp/hosny-takeaway-work/chrome/chrome-linux64/chrome"
OUTPNG = sys.argv[1]
CLIPPED = len(sys.argv) > 2 and sys.argv[2] == "clipped"


async def main():
    data = dict(FERP_DATA)
    if not CLIPPED:
        data["date"] = data["closedAt"] = "10/2/2026 10:58:42 PM"
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        page = await (await b.new_context(locale="ar-SA", viewport={"width": 1400, "height": 900})).new_page()
        got = []

        async def route(r):
            body = r.request.post_data or ""
            m = re.search(r'<image[^>]*width="(\d+)"[^>]*height="(\d+)"', body)
            got.append({"ip": re.search(r"//([\d.]+)/", r.request.url).group(1),
                        "w": int(m.group(1)) if m else None, "h": int(m.group(2)) if m else None,
                        "png": decode(body, OUTPNG)})
            await r.fulfill(status=200, content_type="application/xml", body=EPOS_OK)

        await page.route(re.compile(r"https?://(192\.168\.27\.\d+|0\.0\.0\.0)/.*"), route)
        pos = Pos(page)
        await pos.open()
        res = await pos.js(f"""async (data) => {{
            const pos = {POS};
            const M = (n) => odoo.loader.modules.get(n);
            const {{ loadReceiptFonts }} = M('@hosny_pos_receipt/js/ferp_receipt');
            const {{ computeSAQRCode }} = M('@l10n_sa_pos/app/utils/qr');
            const {{ Component, useRef }} = owl;
            class Probe extends Component {{
                static template = 'hosny_pos_receipt.FerpReceiptBody';
                static props = ['r'];
                setup() {{ this.ferpRoot = useRef('ferpRoot'); }}
                get r() {{ return this.props.r; }}
            }}
            await loadReceiptFonts();
            const when = luxon.DateTime.fromObject({{ year: 2026, month: 10, day: 2, hour: 22, minute: 58, second: 42 }});
            const v = computeSAQRCode(data.title, data.vat, when, data.total, data.tax);
            const svg = new window.ZXing.BrowserQRCodeSvgWriter().write(v, 240, 240);
            const r = Object.assign({{}}, data, {{
                logoUrl: pos.config.receiptLogoUrl,
                qrCode: 'data:image/svg+xml;base64,' + btoa(new XMLSerializer().serializeToString(svg)),
            }});
            const el = await pos.env.services.renderer.toHtml(Probe, {{ r }});
            const printer = pos.hardwareProxy.printer;
            const result = await printer.printReceipt(el);
            return {{ printer: printer.constructor.name, ip: printer.url, ok: !!result?.successful }};
        }}""", data)
        await page.wait_for_timeout(1500)
        print(json.dumps({"printer": res, "requests": got}, ensure_ascii=False))
        await b.close()

asyncio.run(main())
