"""Shared helpers for driving the Hosny POS headless (review instance only).

Printers are intercepted (the server has no route to the branch LANs); every
kitchen ticket's HTML is captured from printer.printReceipt so the rendered
«نوع الفاتوره» / «طاوله» rows can be asserted.
"""
import asyncio, json, os, re, subprocess

BASE = os.environ.get("BASE", "http://127.0.0.1:18105")
DB = os.environ.get("DB", "hosny_receipt_test")
LOGIN = os.environ.get("LOGIN", "1")
PW = os.environ.get("PW", "claudetest123")
CONFIG_ID = int(os.environ.get("CONFIG_ID", "3"))
OUT = os.environ.get("OUT", "/tmp/hosny-receipt-work/e2e/out")
EPOS_OK = '<?xml version="1.0" encoding="utf-8"?><response success="true" code="" status="251658262" battery="0"/>'
os.makedirs(OUT, exist_ok=True)

POS = "odoo.__WOWL_DEBUG__.root.env.services.pos"


def sql(query):
    res = subprocess.run(["sudo", "-u", "postgres", "psql", "-d", DB, "-tAF", "|", "-c", query],
                         capture_output=True, text=True)
    if res.returncode:
        raise RuntimeError(res.stderr)
    return [line.split("|") for line in res.stdout.strip().splitlines() if line]


class Pos:
    def __init__(self, page):
        self.page = page
        self.errors = []
        self.printer_hits = []

    async def js(self, body, arg=None):
        return await self.page.evaluate(body, arg)

    async def state(self):
        """What the cashier is looking at, and the selected order."""
        return await self.js(f"""() => {{
            const pos = {POS};
            const o = pos.getOrder();
            const screen = pos.router.state.current;
            return {{
                screen,
                entryOverlay: !!document.querySelector('.entry-overlay'),
                floorTablesVisible: screen === 'FloorScreen' && !document.querySelector('.entry-overlay')
                    && document.querySelectorAll('.floor-map .table').length,
                order: o ? {{
                    uuid: o.uuid, id: o.id, lines: o.lines.length,
                    table: o.table_id ? (o.table_id.floor_id?.name + ' ' + o.table_id.table_number) : null,
                    type: o.order_type_id?.code || null,
                    effectiveType: pos.getEffectiveOrderType?.(o)?.code || null,
                    state: o.state, finalized: !!o.finalized,
                }} : null,
            }};
        }}""")

    async def order_by_uuid(self, uuid):
        return await self.js(f"""(uuid) => {{
            const pos = {POS};
            const o = pos.models['pos.order'].getBy('uuid', uuid);
            if (!o) return null;
            return {{ id: o.id, lines: o.lines.length, state: o.state,
                     table: o.table_id ? (o.table_id.floor_id?.name + ' ' + o.table_id.table_number) : null,
                     type: o.order_type_id?.code || null }};
        }}""", uuid)

    async def open(self, fresh_login=True):
        page = self.page
        if fresh_login:
            await page.goto(BASE + "/web/login", wait_until="domcontentloaded")
            await page.fill("input[name=login]", LOGIN)
            await page.fill("input[name=password]", PW)
            await page.click("button[type=submit]")
            await page.wait_for_load_state("domcontentloaded")
            if "/web/login" in page.url:
                raise RuntimeError("login failed")
        await page.goto(f"{BASE}/pos/ui?config_id={CONFIG_ID}", wait_until="domcontentloaded")
        await self.boot()

    async def boot(self):
        page = self.page
        await page.wait_for_selector(".pos", timeout=180000)
        await page.wait_for_function(f"() => {{ try {{ return !!{POS}.config; }} catch (e) {{ return false; }} }}",
                                     timeout=180000)
        await page.wait_for_timeout(4000)
        reg = await page.query_selector(".open-register-btn")
        if reg:
            await reg.click()
            await page.wait_for_timeout(5000)
        for _ in range(3):
            d = await page.query_selector(".modal.show .btn-primary, .modal.d-block .btn-primary")
            if not d:
                break
            await d.click()
            await page.wait_for_timeout(2000)
        await self.instrument()

    async def instrument(self):
        await self.js(f"""() => {{
            const pos = {POS};
            window.__kt = window.__kt || [];
            for (const pr of pos.unwatched.printers) {{
                if (pr.__hosnyWrapped) continue;
                const orig = pr.printReceipt.bind(pr);
                pr.printReceipt = async (el) => {{
                    const text = (el?.innerText || '').replace(/\\s+/g, ' ').trim();
                    const r = await orig(el);
                    window.__kt.push({{ printer: pr.config.name, text, ok: r?.successful }});
                    return r;
                }};
                pr.__hosnyWrapped = true;
            }}
        }}""")

    async def tickets(self, reset=True):
        kt = await self.js("() => { const k = window.__kt || []; return k.splice(0, k.length); }")
        return kt

    async def click(self, selector, wait=2500):
        await self.page.click(selector)
        await self.page.wait_for_timeout(wait)

    async def entry(self, which):
        """which: 'takeaway' | 'dine'"""
        if not await self.page.query_selector(".entry-overlay"):
            # «اختر المكان» brings the selector back from any screen
            btn = await self.page.query_selector(".pos-workplace-btn")
            if btn:
                await btn.click()
                await self.page.wait_for_timeout(2500)
        sel = ".entry-card-cashier" if which == "takeaway" else ".entry-card-dine"
        await self.click(sel, 3500)

    async def click_table(self, number):
        ok = await self.js("""(num) => {
            const tables = [...document.querySelectorAll('.floor-map .table')];
            const t = tables.find(el => (el.innerText || '').trim().split(/\\s+/)[0] === String(num));
            if (t) { t.click(); return true; } return false; }""", number)
        await self.page.wait_for_timeout(3500)
        return ok

    async def add(self, name):
        page = self.page
        box = await page.query_selector("input.search-bar-input, .pos-search-bar input, input[placeholder*='بحث'], input[placeholder*='Search']")
        await box.fill("")
        await box.type(name, delay=20)
        await page.wait_for_timeout(1500)
        cards = await page.query_selector_all("article.product")
        target = None
        for c in cards:
            if name in (await c.inner_text()):
                target = c
                break
        target = target or (cards[0] if cards else None)
        if not target:
            raise RuntimeError(f"no product card for {name}")
        await target.click()
        await page.wait_for_timeout(1200)
        btn = await page.query_selector(".modal.show .modal-footer .btn-primary, .modal.d-block .modal-footer .btn-primary")
        if btn:
            await btn.click()
            await page.wait_for_timeout(1000)
        await box.fill("")

    async def send(self):
        await self.click(".hosny-send-action", 7000)

    async def pay(self, method_label, answer_prompt=True):
        """الدفع → (prompt «أرسل للتحضير؟») → method → تصديق. Returns the dialogs seen."""
        page = self.page
        seen = []
        await page.click(".hosny-pay-action")
        answered = 0
        for _ in range(25):
            await page.wait_for_timeout(1000)
            if (await self.state())["screen"] == "PaymentScreen":
                break
            modal = await page.query_selector(".modal.show, .modal.d-block")
            if modal and answered < 3:
                seen.append((await modal.inner_text()).replace("\n", " ")[:160])
                btn = await page.query_selector(".modal.show .modal-footer .btn-primary, .modal.d-block .modal-footer .btn-primary")
                if not btn or not answer_prompt:
                    break
                await btn.click()
                answered += 1
        st = await self.state()
        if st["screen"] != "PaymentScreen":
            return {"reachedPayment": False, "dialogs": seen, "state": st}
        await page.wait_for_selector(".paymentmethod", timeout=15000)
        await page.wait_for_timeout(800)
        cards = await page.query_selector_all(".paymentmethod")
        target = None
        for c in cards:
            if method_label in (await c.inner_text()):
                target = c
                break
        if not target:
            raise RuntimeError(f"payment method {method_label} not found")
        await target.click()
        await page.wait_for_timeout(2500)
        # «أجل» asks for a customer first (hosny_pos_controls), then adds the line itself
        partner = await page.query_selector(".modal.show .partner-info, .modal.d-block .partner-info")
        if partner:
            await partner.click()
            await page.wait_for_timeout(2500)
        order_before = await self.state()
        lines = await self.js(f"""() => {POS}.getOrder().payment_ids.map(p => p.payment_method_id.name)""")
        await page.click(".hosny-payment-validate")
        for _ in range(20):
            await page.wait_for_timeout(1000)
            if (await self.state())["screen"] != "PaymentScreen":
                break
            modal = await page.query_selector(".modal.show, .modal.d-block")
            if modal:
                seen.append((await modal.inner_text()).replace("\n", " ")[:160])
                btn = await page.query_selector(".modal.show .modal-footer .btn-primary, .modal.d-block .modal-footer .btn-primary")
                if btn:
                    await btn.click()
        await page.wait_for_timeout(1500)
        return {"reachedPayment": True, "dialogs": seen, "paidOrder": order_before["order"],
                "paymentLines": lines, "after": await self.state()}

    async def done(self):
        """«طلب جديد» on the receipt screen (pos.orderDone)."""
        btn = await self.page.query_selector("[name='done']")
        if btn:
            await btn.click()
            await self.page.wait_for_timeout(3500)
        return await self.state()

    async def track_navigation(self):
        await self.js(f"""() => {{
            const pos = {POS};
            window.__nav = window.__nav || [];
            if (pos.__navWrapped) return;
            const orig = pos.navigate.bind(pos);
            pos.navigate = (page, params) => {{ window.__nav.push(page); return orig(page, params); }};
            pos.__navWrapped = true;
        }}""")

    async def navigations(self):
        return await self.js("() => { const n = window.__nav || []; return n.splice(0, n.length); }")

    async def floor_tabs(self):
        return await self.js("() => [...document.querySelectorAll('.floor-selector .button-floor')].map(b => b.innerText.trim())")

    async def chip(self):
        return await self.js("() => { const c = document.querySelector('.hosny-order-type-chip'); return c ? c.innerText.trim() : null; }")


def db_order(uuid=None, order_id=None):
    where = f"o.uuid='{uuid}'" if uuid else f"o.id={order_id}"
    rows = sql(f"""select o.id, o.state, coalesce(ot.code,'NULL'), coalesce(o.table_id::text,'NULL'),
        coalesce(f.name,''), o.amount_total, coalesce((select string_agg(pm.name->>'en_US', ',')
        from pos_payment p join pos_payment_method pm on pm.id=p.payment_method_id where p.pos_order_id=o.id), '')
        from pos_order o left join pos_order_type ot on ot.id=o.order_type_id
        left join restaurant_table t on t.id=o.table_id left join restaurant_floor f on f.id=t.floor_id
        where {where}""")
    if not rows:
        return None
    r = rows[0]
    return {"id": int(r[0]), "state": r[1], "type": r[2], "table_id": r[3], "floor": r[4],
            "total": r[5], "payments": r[6]}


def log_mark():
    return int(subprocess.run(["wc", "-l", os.environ.get("SERVER_LOG", "/tmp/hosny-receipt-work/server.log")],
                              capture_output=True, text=True).stdout.split()[0])


def log_errors_since(mark):
    with open(os.environ.get("SERVER_LOG", "/tmp/hosny-receipt-work/server.log"), errors="replace") as f:
        lines = f.readlines()[mark:]
    noise = ("Couldn't bind the websocket", "evented port")
    return [l.rstrip()[:400] for l in lines
            if (" ERROR " in l or "Traceback" in l or " CRITICAL " in l) and not any(n in l for n in noise)]
