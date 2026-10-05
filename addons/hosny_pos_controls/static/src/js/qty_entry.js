/** @odoo-module **/
/**
 * إدخال الكمية والخصم بلا نوافذ (طلب 2026-10-02).
 *
 * الكيبورد هو الأساس: يُكتب الرقم مباشرة فيتغيّر الصنف المحدد في قائمة الطلب.
 * لوحة الأرقام للأجهزة بلا كيبورد مخفية: يُظهرها «الكمية» (أو «نسبة الخصم»،
 * أو شريحة الكمية في السطر) فوق المنتجات على يسار لوحة الطلب، ويُخفيها الضغط
 * على الزر نفسه مرة ثانية، أو أي ضغطة خارجها غير أسطر الطلب، أو Esc/Enter/«تم»
 * (طلب 2026-10-02 الثاني: لا تثبت، ولا تأخذ من مساحة الأصناف). إخفاؤها يعيد
 * الوضع إلى الكمية دائماً، فلا يُكتب «2» على صنف فيصير خصماً 2%.
 *
 * لماذا متحكّم خاص بدل number_buffer في أودو (قيس على 19.0.1.12.0):
 *   • يلصق الأرقام: «3» ثم «1750» أعطت 31750، و Esc لا يصفّره (أودو ينتظر
 *     "Esc" والمتصفح يرسل "Escape").
 *   • يعتبر أي ثلاث ضغطات خلال 150ms باركوداً فيرميها: كتابة عادية سريعة
 *     (120ms) ضاعت كلها بلا أي أثر.
 *   • Backspace على خانة فارغة يحذف الصنف من الطلب.
 * فمسار أودو على شاشة المنتجات معطَّل (updateSelectedOrderline) وهذا بديله:
 *   • أول رقم بعد اختيار صنف (أو بعد Enter/Esc) يبدأ من جديد، والتالي يُلحق.
 *   • Backspace يمسح آخر رقم، ولا يحذف الصنف أبداً؛ لو فرغت الخانة ترجع
 *     القيمة الأصلية. الحذف بزر سلة المهملات وحده.
 *   • Esc يرجّع القيمة التي كانت قبل الكتابة، Enter يثبّت، و4 ثوانٍ بلا
 *     كتابة تثبّت أيضاً (الإطار حول شريحة الكمية يختفي حين تنتهي الجلسة).
 *   • الخصم لا يتجاوز 100%: الرقم الذي يتجاوزها لا يُقبل.
 *   • تُقرأ المفاتيح من event.code، فتعمل الأرقام ولو كان الكيبورد عربياً،
 *     ومعها الأرقام الهندية (٠-٩) والفاصلة العشرية العربية.
 *   • خدمة الباركود في أودو تعدّ أي ثلاثة أحرف بفاصل أقل من 150ms مسحاً،
 *     فكتابة كاشير سريع «1750» كانت تُظهر «Unknown Barcode 1750» (ولو وُجد
 *     منتج بهذا الباركود لأُضيف). لذلك تُوقف مفاتيح الإدخال هنا قبل أن تصلها،
 *     ودفعة من ثلاثة مفاتيح أو أكثر بفاصل أقل من 35ms — وهذا قارئ باركود لا
 *     يد إنسان — تُعاد إليها بترتيبها فيبقى المسح يعمل. الحروف تمر كما هي،
 *     وما يليها مباشرة يمر معها.
 */
import { patch } from "@web/core/utils/patch";
import { useEffect, useExternalListener, useRef } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";

export const HOSNY_PAD_KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0", "Backspace"];
const MAX_DIGITS = 9;
const SCANNER_GAP_MS = 35;
// بعد 4 ثوانٍ بلا كتابة يبدأ الرقم التالي من جديد: «2» على عصير ثم «3» بعد
// نصف دقيقة تعني 3، لا 23.
const IDLE_RESET_MS = 4000;
let replayingKeys = false;
const EASTERN_DIGITS = { "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9" };

/** المفتاح كما يفهمه الإدخال، أو null لو لا يخصّه. */
export function hosnyEntryKeyFromEvent(ev) {
    const code = ev.code || "";
    let m = code.match(/^(?:Digit|Numpad)(\d)$/);
    if (m) {
        return m[1];
    }
    if (["NumpadDecimal", "Period", "Comma", "NumpadComma"].includes(code)) {
        return ".";
    }
    if (code === "Backspace" || code === "Delete" || code === "NumpadEnter" || code === "Enter" || code === "Escape") {
        return code === "NumpadEnter" ? "Enter" : code === "Delete" ? "Backspace" : code;
    }
    const key = ev.key || "";
    if (/^\d$/.test(key)) {
        return key;
    }
    if (EASTERN_DIGITS[key]) {
        return EASTERN_DIGITS[key];
    }
    if (key === "." || key === "," || key === "٫" || key === "٬") {
        return ".";
    }
    return null;
}

function formatNumber(value) {
    if (!Number.isFinite(value)) {
        return "";
    }
    return Number.isInteger(value) ? String(value) : String(parseFloat(value.toFixed(3)));
}

patch(PosStore.prototype, {
    get hosnyEntry() {
        if (!this._hosnyEntry) {
            this._hosnyEntry = {
                lineUuid: null, mode: null, buffer: "", original: null, sign: 1, open: false, pad: false,
            };
        }
        return this._hosnyEntry;
    },

    /** الصنف الذي يستقبل الإدخال: المحدد (أو أب الكومبو)، وإلا آخر صنف. */
    hosnyEntryTarget({ select = false } = {}) {
        const order = this.getOrder();
        if (!order || order.isEmpty?.() || order.finalized) {
            return null;
        }
        let line = order.getSelectedOrderline?.();
        if (!line) {
            line = order.getOrderlines?.().filter((l) => !l.combo_parent_id).at(-1) || null;
            if (line && select) {
                this.selectOrderLine(order, line);
            }
        }
        return line?.combo_parent_id || line || null;
    },

    hosnyEntryMode() {
        return this.numpadMode === "discount" ? "discount" : "quantity";
    },

    hosnyEntryValueOf(line, mode) {
        return mode === "discount" ? line.getDiscount() : line.getQuantity();
    },

    /** «الكمية» / «نسبة الخصم» / شريحة الكمية في السطر: وضع الإدخال وصنفه. */
    hosnyArmEntry(mode, line = null) {
        this.numpadMode = mode === "discount" ? "discount" : "quantity";
        const order = this.getOrder();
        const target = line ? line.combo_parent_id || line : this.hosnyEntryTarget({ select: true });
        if (order && target && order.getSelectedOrderline?.() !== target) {
            this.selectOrderLine(order, target);
        }
        this.hosnyEntryClose();
        return target;
    },

    /**
     * «الكمية» / «نسبة الخصم» / شريحة الكمية: نفس الزر على اللوحة المفتوحة
     * بنفس الوضع (ونفس الصنف للشريحة) يخفيها؛ غير ذلك يُظهرها بالوضع المطلوب.
     */
    hosnyTogglePad(mode, line = null) {
        const entry = this.hosnyEntry;
        const wanted = mode === "discount" ? "discount" : "quantity";
        const order = this.getOrder();
        const sameLine = !line || order?.getSelectedOrderline?.() === (line.combo_parent_id || line);
        if (entry.pad && this.hosnyEntryMode() === wanted && sameLine) {
            this.hosnyClosePad();
            return true;
        }
        const target = this.hosnyArmEntry(wanted, line);
        if (!target) {
            this.hosnyClosePad();
            return false;
        }
        entry.pad = true;
        return true;
    },

    hosnyOpenPad(mode, line = null) {
        const target = this.hosnyArmEntry(mode === "discount" ? "discount" : "quantity", line);
        this.hosnyEntry.pad = Boolean(target);
        return Boolean(target);
    },

    hosnyClosePad() {
        this.hosnyEntryClose();
        this.hosnyEntry.pad = false;
        this.numpadMode = "quantity";
    },

    /** ينهي جلسة الكتابة الحالية: الرقم التالي يبدأ من جديد. */
    hosnyEntryClose() {
        clearTimeout(this._hosnyEntryIdle);
        const entry = this.hosnyEntry;
        entry.open = false;
        entry.buffer = "";
        entry.lineUuid = null;
        entry.original = null;
    },

    hosnyEntryKey(key) {
        const line = this.hosnyEntryTarget({ select: true });
        if (!line) {
            return false;
        }
        const entry = this.hosnyEntry;
        const mode = this.hosnyEntryMode();

        if (key === "Enter") {
            this.hosnyEntryClose();
            if (entry.pad) {
                this.hosnyClosePad();
            }
            return true;
        }
        if (key === "Escape") {
            if (entry.open && entry.lineUuid === line.uuid && entry.original !== null) {
                this._hosnyEntryApply(line, entry.mode, entry.original, { raw: true });
            }
            this.hosnyEntryClose();
            if (entry.pad) {
                this.hosnyClosePad();
            }
            return true;
        }

        if (!entry.open || entry.lineUuid !== line.uuid || entry.mode !== mode) {
            try {
                line.order_id.assertEditable();
            } catch (error) {
                this.dialog.add(AlertDialog, {
                    title: _t("تعذر تعديل الصنف"),
                    body: error.message || _t("لا يمكن تعديل هذا الصنف الآن."),
                });
                return false;
            }
            if (key === "Backspace") {
                // لا جلسة مفتوحة: Backspace لا يفعل شيئاً (لا يحذف الصنف أبداً).
                return true;
            }
            const value = this.hosnyEntryValueOf(line, mode);
            Object.assign(entry, {
                open: true,
                lineUuid: line.uuid,
                mode,
                buffer: "",
                original: value,
                // سطر المرتجع كميته سالبة: نكتب الرقم موجباً ونحفظ الإشارة.
                sign: mode === "quantity" && (value < 0 || line.refunded_orderline_id) ? -1 : 1,
            });
        }

        let buffer = entry.buffer;
        if (key === "Backspace") {
            buffer = buffer.slice(0, -1);
        } else if (key === ".") {
            if (!buffer.includes(".")) {
                buffer = (buffer || "0") + ".";
            }
        } else if (/^\d$/.test(key)) {
            if (buffer.replace(".", "").length >= MAX_DIGITS) {
                return true;
            }
            buffer = buffer === "0" ? key : buffer + key;
        } else {
            return false;
        }
        if (mode === "discount" && parseFloat(buffer || "0") > 100) {
            return true;
        }
        entry.buffer = buffer;
        clearTimeout(this._hosnyEntryIdle);
        this._hosnyEntryIdle = setTimeout(() => this.hosnyEntryClose(), IDLE_RESET_MS);

        if (!buffer) {
            this._hosnyEntryApply(line, mode, entry.original, { raw: true });
            return true;
        }
        const value = parseFloat(buffer.endsWith(".") ? buffer.slice(0, -1) || "0" : buffer);
        if (Number.isFinite(value)) {
            this._hosnyEntryApply(line, mode, value * (mode === "quantity" ? entry.sign : 1));
        }
        return true;
    },

    /** نفس ما كانت تفعله نافذة الكمية/الخصم عند «تطبيق». */
    _hosnyEntryApply(line, mode, value, { raw = false } = {}) {
        if (mode === "discount") {
            const discount = raw ? value : Math.min(Math.max(value, 0), 100);
            this.setDiscountFromUI(line, discount);
            return true;
        }
        try {
            const result = line.setQuantity(value, Boolean(line.combo_line_ids?.length));
            if (result !== true) {
                this.dialog.add(AlertDialog, result);
                const entry = this.hosnyEntry;
                if (entry.original !== null && entry.lineUuid === line.uuid) {
                    line.setQuantity(entry.original, Boolean(line.combo_line_ids?.length));
                }
                this.hosnyEntryClose();
                return false;
            }
        } catch (error) {
            this.dialog.add(AlertDialog, {
                title: _t("تعذر تعديل الصنف"),
                body: error.message || _t("لا يمكن تعديل هذا الصنف الآن."),
            });
            this.hosnyEntryClose();
            return false;
        }
        return true;
    },

    /** ما تعرضه رأس الشبكة: الوضع والقيمة الحالية للصنف المحدد. */
    hosnyEntryView() {
        const line = this.hosnyEntryTarget();
        const mode = this.hosnyEntryMode();
        const entry = this.hosnyEntry;
        const typing = Boolean(line && entry.open && entry.lineUuid === line.uuid && entry.mode === mode);
        let value = "";
        if (line) {
            value = typing && entry.buffer ? entry.buffer : formatNumber(Math.abs(this.hosnyEntryValueOf(line, mode)));
            if (mode === "discount") {
                value = `${value}%`;
            }
        }
        return { hasLine: Boolean(line), mode, value, typing, padOpen: Boolean(entry.pad && line) };
    },
});

patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this._hosnyKeyQueue = [];
        this._hosnyPassUntil = 0;
        this.hosnyPadRef = useRef("hosnyPad");
        useExternalListener(window, "keydown", (ev) => this.onHosnyEntryKeydown(ev), { capture: true });
        useExternalListener(document, "pointerdown", (ev) => this.onHosnyOutsidePointer(ev), { capture: true });
        useExternalListener(window, "resize", () => this.placeHosnyPad());
        // تظهر اللوحة: نضعها بجانب لوحة الطلب قبل أن تبدأ حركة الظهور.
        useEffect(
            (open) => {
                if (open) {
                    this.placeHosnyPad();
                }
            },
            () => [Boolean(this.pos.hosnyEntry.pad)]
        );
        // طلب آخر، أو طلب فرغ: لا لوحة مفتوحة على صنف لم يعد أمام الكاشير.
        useEffect(
            () => {
                if (this.pos.hosnyEntry.pad) {
                    this.pos.hosnyClosePad();
                }
            },
            () => [this.pos.getOrder()?.uuid, Boolean(this.pos.getOrder()?.isEmpty?.())]
        );
    },

    get hosnyPadKeys() {
        return HOSNY_PAD_KEYS;
    },

    /** «الكمية» / «نسبة الخصم» تتلوّن ما دامت اللوحة مفتوحة بوضعها. */
    hosnyNumpadModeClass(mode) {
        return this.pos.hosnyEntry.pad && this.pos.hosnyEntryMode() === mode
            ? `is-active is-mode-${mode}`
            : "";
    },

    /**
     * على يسار لوحة الطلب (يمينها لو لم يتّسع اليسار)، بمحاذاة أول القائمة.
     * position: fixed، فلا يقصّها overflow لوحة الطلب ولا تأخذ من مساحتها.
     */
    placeHosnyPad() {
        const pad = this.hosnyPadRef.el;
        if (!pad || !this.pos.hosnyEntry.pad) {
            return;
        }
        const pane = pad.closest(".leftpane");
        if (!pane) {
            return;
        }
        const anchor = pane.querySelector(".order-container") || pane;
        const paneRect = pane.getBoundingClientRect();
        const anchorRect = anchor.getBoundingClientRect();
        const gap = 12;
        const width = pad.offsetWidth;
        let left = paneRect.left - width - gap;
        if (left < 8) {
            left = Math.min(paneRect.right + gap, window.innerWidth - width - 8);
        }
        const top = Math.max(8, Math.min(anchorRect.top, window.innerHeight - pad.offsetHeight - 8));
        pad.style.left = `${Math.round(left)}px`;
        pad.style.top = `${Math.round(top)}px`;
    },

    onHosnyOutsidePointer(ev) {
        if (!this.pos.hosnyEntry.pad) {
            return;
        }
        // اللوحة نفسها، وزرّا الوضع (يبدّلانها بأنفسهما)، وأسطر الطلب (لتنتقل
        // بين الأصناف واللوحة مفتوحة) لا تخفيها؛ كل ما عداها يخفيها.
        if (ev.target?.closest?.(".hosny-qtypad, .hosny-mode-buttons, .order-container .orderline")) {
            return;
        }
        this.pos.hosnyClosePad();
    },

    onHosnyEntryKeydown(ev) {
        if (replayingKeys || ev.ctrlKey || ev.metaKey || ev.altKey || ev.isComposing) {
            return;
        }
        const target = ev.target;
        if (target?.closest?.("input, textarea, select, [contenteditable=''], [contenteditable='true']")) {
            return;
        }
        // نافذة مفتوحة (تفاصيل الطلب، الدفع، تنبيه…): الأرقام ليست لقائمة الطلب.
        const overlays = this.env.services.overlay?.overlays;
        if ((overlays && Object.keys(overlays).length) || document.querySelector(".o_dialog")) {
            return;
        }
        const now = performance.now();
        // نص يمر لخدمة الباركود (بدأ بحرف): ما يليه مباشرة يمر معه.
        if (now < this._hosnyPassUntil) {
            this._hosnyPassUntil = now + 150;
            return;
        }
        const key = hosnyEntryKeyFromEvent(ev);
        if (!key) {
            if (ev.key && ev.key.length === 1) {
                this.replayHosnyEntryKeys();
                this._hosnyPassUntil = now + 150;
            }
            return;
        }
        const queue = this._hosnyKeyQueue;
        // Enter/Esc/Backspace خارج أي كتابة ولوحة مخفية: ليست لنا، تمر لأصحابها.
        const entry = this.pos.hosnyEntry;
        if (["Enter", "Escape", "Backspace"].includes(key) && !queue.length && !entry.open && !entry.pad) {
            return;
        }
        // Enter على زر مركَّز كان سيضغطه، ووصول الأرقام لخدمة الباركود يُظهر
        // «Unknown Barcode»؛ ما يتبيّن أنه مسح يُعاد إليها في replayHosnyEntryKeys.
        ev.preventDefault();
        ev.stopPropagation();
        queue.push({ key, rawKey: ev.key, code: ev.code });
        clearTimeout(this._hosnyKeyTimer);
        this._hosnyKeyTimer = setTimeout(() => this.flushHosnyEntryKeys(), SCANNER_GAP_MS);
    },

    flushHosnyEntryKeys() {
        // ثلاثة مفاتيح أو أكثر كل منها بعد سابقه بأقل من 35ms = قارئ باركود.
        if (this._hosnyKeyQueue.length >= 3) {
            this.replayHosnyEntryKeys();
            return;
        }
        for (const { key } of this._hosnyKeyQueue.splice(0)) {
            this.pos.hosnyEntryKey(key);
        }
    },

    /** يعيد المفاتيح المحجوزة لخدمة الباركود (تستمع على body) بترتيبها. */
    replayHosnyEntryKeys() {
        clearTimeout(this._hosnyKeyTimer);
        const queue = this._hosnyKeyQueue.splice(0);
        replayingKeys = true;
        try {
            for (const { rawKey, code } of queue) {
                document.body.dispatchEvent(
                    new KeyboardEvent("keydown", { key: rawKey, code, bubbles: true, cancelable: true })
                );
            }
        } finally {
            replayingKeys = false;
        }
    },

    openHosnyQuantityPopup() {
        if (!this.pos.hosnyTogglePad("quantity")) {
            this.notification.add(_t("اختر منتجاً أولاً."), { type: "warning" });
        }
    },

    openHosnyDiscountPopup() {
        if (!this.pos.hosnyTogglePad("discount")) {
            this.notification.add(_t("اختر منتجاً أولاً."), { type: "warning" });
        }
    },

    async addProductToOrder() {
        const result = await super.addProductToOrder(...arguments);
        // صنف جديد يبدأ بالكمية: لا يُكتب «2» على صنف جديد فيصير خصماً 2%.
        if (this.pos.numpadMode === "discount") {
            this.pos.numpadMode = "quantity";
        }
        this.pos.hosnyEntryClose();
        return result;
    },
});

patch(Orderline.prototype, {
    /**
     * شريحة الكمية في السطر: تحدد الصنف للكتابة وتُظهر لوحة الأرقام. تُظهرها
     * دائماً ولا تبدّلها: الضغط على السطر يختاره قبل أن يصل الضغط إلى الشريحة،
     * فلا يُعرف منه هل كان هو صنف اللوحة من قبل.
     */
    openHosnyOrderlineQuantityPopup(line) {
        this.pos.hosnyOpenPad("quantity", line);
    },
});

patch(OrderSummary.prototype, {
    /**
     * مسار أودو (number_buffer) معطَّل على شاشة المنتجات: الكيبورد والشبكة
     * يمرّان عبر hosnyEntryKey وحده، وإلا طُبّق كل رقم مرتين.
     */
    updateSelectedOrderline() {
        this.numberBuffer.reset();
    },

    clickLine(ev, orderline) {
        super.clickLine(...arguments);
        this.pos.hosnyEntryClose();
    },
});
