"""Helpers for the «عرض الطلب كاملاً» / kitchen-notes tests (notes clone, port 18103)."""
import base64, json, re
import numpy as np
from PIL import Image
from harness import Pos, EPOS_OK, OUT, POS

CHROME = "/tmp/hosny-takeaway-work/chrome/chrome-linux64/chrome"
PRINTERS = {"192.168.27.56": "grill", "192.168.27.192": "kitchen", "192.168.27.170": "fish",
            "192.168.27.163": "cafe", "192.168.27.58": "salads", "192.168.27.48": "cashier"}

results = []


def check(case, name, ok, detail=None):
    results.append((case, name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + f"[{case}] {name}" +
          ("" if ok else f"  -> {json.dumps(detail, ensure_ascii=False, default=str)[:700]}"), flush=True)
    return ok


def decode(body, path):
    m = re.search(r'<image[^>]*width="(\d+)"[^>]*height="(\d+)"[^>]*>([^<]+)</image>', body)
    if not m:
        return None
    w, h, b64 = int(m.group(1)), int(m.group(2)), m.group(3)
    bits = np.unpackbits(np.frombuffer(base64.b64decode(b64), dtype=np.uint8))[: w * h].reshape(h, w)
    Image.fromarray(((1 - bits) * 255).astype(np.uint8)).save(path)
    return path


class Printers:
    def __init__(self):
        self.hits = []
        self.seq = 0
        self.tag = "x"

    async def route(self, r):
        ip = re.search(r"//([\d.]+)/", r.request.url).group(1)
        self.seq += 1
        png = decode(r.request.post_data or "", f"{OUT}/{self.tag}_{self.seq:02d}_{PRINTERS.get(ip, ip)}.png")
        self.hits.append({"ip": ip, "name": PRINTERS.get(ip, ip), "png": png})
        await r.fulfill(status=200, content_type="application/xml", body=EPOS_OK)

    def take(self):
        out = list(self.hits)
        self.hits.clear()
        return out


async def wait_prints(pos, printers, n, timeout=25000):
    waited = 0
    while len(printers.hits) < n and waited < timeout:
        await pos.page.wait_for_timeout(500)
        waited += 500
    await pos.page.wait_for_timeout(2500)


async def add_product(pos, name, variant_index=0):
    """Search, tap the card, and pick a size in the Hosny variant picker if it opens."""
    page = pos.page
    box = await page.query_selector("input.search-bar-input, .pos-search-bar input, .hosny-category-search input, input[placeholder*='بحث'], input[placeholder*='Search']")
    await box.fill("")
    await box.type(name, delay=15)
    await page.wait_for_timeout(1200)
    cards = await page.query_selector_all("article.product")
    target = None
    for c in cards:
        if name in (await c.inner_text()):
            target = c
            break
    if not target:
        raise RuntimeError(f"no product card for {name}")
    await target.click()
    await page.wait_for_timeout(1200)
    opts = await page.query_selector_all(".hosny-variant-option")
    if opts:
        await opts[variant_index].click()
        await page.wait_for_timeout(1200)
    btn = await page.query_selector(".modal.show .modal-footer .btn-primary, .modal.d-block .modal-footer .btn-primary")
    if btn and not await page.query_selector(".hosny-oe"):
        await btn.click()
        await page.wait_for_timeout(1000)
    await box.fill("")
    await page.wait_for_timeout(500)


async def order_snapshot(pos):
    return await pos.js(f"""() => {{
        const pos = {POS};
        const o = pos.getOrder();
        if (!o) return null;
        const ch = pos.getOrderChanges(o);
        return {{
            uuid: o.uuid, id: o.id, internal_note: o.internal_note,
            lines: o.lines.map(l => ({{ uuid: l.uuid, name: l.product_id.name, qty: l.qty, note: l.note || '' }})),
            pending: Object.keys(ch.orderlines).length + Object.keys(ch.noteUpdate).length,
            orderNotePending: ch.internal_note !== undefined,
        }};
    }}""")


async def send_button(pos):
    return await pos.js("""() => {
        const b = document.querySelector('.hosny-send-action');
        if (!b) return null;
        return { text: b.innerText.replace(/\\s+/g, ' ').trim(), disabled: b.disabled,
                 sent: b.classList.contains('is-sent'),
                 count: b.querySelector('.hosny-send-count')?.innerText.trim() || null };
    }""")


async def dialog_state(pos):
    return await pos.js("""() => {
        const d = document.querySelector('.hosny-oe');
        if (!d) return null;
        const lines = [...d.querySelectorAll('.hosny-oe-line')].map(el => ({
            name: el.querySelector('.hosny-oe-name')?.innerText.trim(),
            tags: [...el.querySelectorAll('.hosny-oe-tag')].map(t => t.innerText.trim()),
            status: el.querySelector('.hosny-oe-status')?.innerText.trim() || null,
            qty: el.querySelector('.hosny-oe-qty')?.innerText.replace(/\\s+/g, '').trim(),
            total: el.querySelector('.hosny-oe-total')?.innerText.trim() || null,
            notes: [...el.querySelectorAll('.hosny-oe-note-text')].map(n => n.innerText.trim()),
            editing: el.classList.contains('is-editing'),
        }));
        const send = d.querySelector('.hosny-oe-btn.is-send');
        return {
            title: d.querySelector('.hosny-oe-title')?.innerText.trim(),
            meta: [...d.querySelectorAll('.hosny-oe-meta-chip')].map(c => c.innerText.trim()),
            lines,
            orderNotes: [...d.querySelectorAll('.hosny-oe-order-note .hosny-oe-note-text')].map(n => n.innerText.trim()),
            orderNotePending: !!d.querySelector('.hosny-oe-order-note .hosny-oe-status'),
            kitchen: d.querySelector('.hosny-oe-kitchen')?.innerText.trim(),
            total: d.querySelector('.hosny-oe-summary-row.is-total bdi')?.innerText.trim(),
            send: send ? { text: send.innerText.replace(/\\s+/g, ' ').trim(), disabled: send.disabled } : null,
            quick: [...d.querySelectorAll('.hosny-oe-order-note .hosny-oe-quick-chip')].map(c => c.innerText.trim()),
        };
    }""")


async def open_dialog(pos):
    await pos.page.click(".hosny-order-expand")
    await pos.page.wait_for_selector(".hosny-oe", timeout=10000)
    await pos.page.wait_for_timeout(700)


async def line_index(pos, name):
    return await pos.js("""(name) => [...document.querySelectorAll('.hosny-oe-line')]
        .findIndex(el => (el.querySelector('.hosny-oe-name')?.innerText || '').includes(name))""", name)


async def add_line_note(pos, name, text, via="enter"):
    page = pos.page
    card = page.locator(".hosny-oe-line", has=page.locator(".hosny-oe-name", has_text=name)).first
    if not await card.evaluate("el => el.classList.contains('is-editing')"):
        await card.locator(".hosny-oe-add-note").click()
        await page.wait_for_timeout(400)
    inp = card.locator(".hosny-oe-input")
    await inp.click()
    await inp.type(text, delay=10)
    if via == "enter":
        await inp.press("Enter")
    elif via == "button":
        await card.locator(".hosny-oe-input-add").click()
    await page.wait_for_timeout(400)


async def remove_line_note(pos, name, text):
    ok = await pos.js("""([name, text]) => {
        const el = [...document.querySelectorAll('.hosny-oe-line')].find(e => (e.querySelector('.hosny-oe-name')?.innerText || '').includes(name));
        const note = [...(el?.querySelectorAll('.hosny-oe-note') || [])].find(n => n.querySelector('.hosny-oe-note-text')?.innerText.trim() === text);
        const b = note?.querySelector('.hosny-oe-note-remove');
        if (b) { b.click(); return true; } return false; }""", [name, text])
    await pos.page.wait_for_timeout(400)
    return ok


async def add_order_note(pos, text, via="enter"):
    inp = await pos.page.query_selector(".hosny-oe-order-input")
    await inp.fill("")
    await inp.type(text, delay=10)
    if via == "enter":
        await inp.press("Enter")
    elif via == "button":
        await pos.page.click(".hosny-oe-order-note .hosny-oe-input-add")
    await pos.page.wait_for_timeout(400)


async def remove_order_note(pos, text):
    ok = await pos.js("""(text) => {
        const note = [...document.querySelectorAll('.hosny-oe-order-note .hosny-oe-note')].find(n => n.querySelector('.hosny-oe-note-text')?.innerText.trim() === text);
        const b = note?.querySelector('.hosny-oe-note-remove');
        if (b) { b.click(); return true; } return false; }""", text)
    await pos.page.wait_for_timeout(400)
    return ok


async def close_dialog(pos, how="button"):
    if how == "button":
        await pos.page.click(".hosny-oe-btn.is-close")
    elif how == "x":
        await pos.page.click(".hosny-oe-close")
    elif how == "esc":
        await pos.page.keyboard.press("Escape")
    await pos.page.wait_for_timeout(800)
