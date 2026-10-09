/** @odoo-module **/
/**
 * فاتورة العميل بتصميم FERP (فاتورة فرع المدينة المصوَّرة 10/2/2026).
 *
 * القالب hosny_pos_receipt.FerpReceiptBody يُرسم من كائن بيانات واحد يبنيه
 * buildFerpReceipt، فشاشة الإيصال والطباعة وصورة البريد تعرض نفس الشيء.
 * الفاتورة المبسّطة «بدون أسعار» (basic_receipt) تبقى بقالب أودو.
 *
 * الحسابات: كل سطر بعد خصم السطر — الكمية × سعر الوحدة (بدون ضريبة) + ضريبة
 * السطر = إجمالي السطر. سطور الخصم العام (منتج الخصم / مكافآت الولاء) لا تظهر
 * كأصناف بل في «الخصم»، فيبقى: صافي المبلغ − الخصم + الضريبة = الإجمالي.
 */
import { onMounted, onPatched, useRef } from "@odoo/owl";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { computeSAQRCode } from "@l10n_sa_pos/app/utils/qr";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

const { DateTime } = luxon;

// عرض الفاتورة بالنقاط = عرض الطباعة على TM-T20III (72 مم)، مثل فاتورة FERP.
const RECEIPT_WIDTH = 576;

// نص فيه كل ما تحتاجه الفاتورة، حتى يحمّل المتصفح الخط كاملاً وليس جزءاً منه.
const FONT_SAMPLE = "مطاعم حسنى فاتورة ضريبية مبسطة الإجمالي 0123456789.:/ PM ahmed";
const RECEIPT_FONTS = [
    '400 30px "Hosny Receipt Arabic Light"',
    '400 30px "Hosny Receipt Arabic Medium"',
    '700 30px "Hosny Receipt Arabic SemiBold"',
    '700 30px "Hosny Receipt Arabic Bold"',
    '700 30px "Hosny Receipt Arabic Heavy"',
    '700 30px "Hosny Receipt Naskh"',
    '400 30px "Hosny Receipt Sans"',
    '700 30px "Hosny Receipt Sans"',
    '400 30px "Hosny Receipt Narrow"',
    '700 30px "Hosny Receipt Narrow"',
];
let receiptFontsReady = null;

/**
 * الفاتورة تُقاس في الصفحة قبل تحويلها لصورة؛ لو لم يكن الخط محمّلاً بعد
 * لقيست بخط بديل وخرجت الصورة مقصوصة أو مزاحة. نحمّل الخطوط مرة واحدة، ولا
 * نحفظ الوعد إلا لو نجح التحميل حتى تعيد الطباعة التالية المحاولة.
 */
export function loadReceiptFonts() {
    if (!receiptFontsReady) {
        receiptFontsReady = Promise.all(
            RECEIPT_FONTS.map((font) => document.fonts.load(font, FONT_SAMPLE))
        ).then(
            (faces) => {
                if (faces.some((list) => !list.length)) {
                    receiptFontsReady = null;
                }
            },
            () => {
                receiptFontsReady = null;
            }
        );
    }
    return receiptFontsReady;
}

/** 199.13 / -5.00 بأرقام لاتينية وبدون فواصل آلاف، كما في FERP. */
export function formatMoney(amount) {
    const value = Math.round((Number(amount) || 0) * 100) / 100;
    return (Object.is(value, -0) ? 0 : value).toFixed(2);
}

/** سعر الوحدة: خانتان عشريتان، وأكثر فقط لو ضاع السعر بالتقريب (الأصناف بالجرام). */
export function formatUnitPrice(amount) {
    const value = Number(amount) || 0;
    const fixed = formatMoney(value);
    if (Math.abs(value - Number(fixed)) < 0.0005 || Math.abs(value) >= 1) {
        return fixed;
    }
    return String(parseFloat(value.toFixed(4)));
}

/** 1 → "1"، 0.5 → "0.5"، 1750 → "1750" */
export function formatQty(quantity) {
    const qty = Number(quantity) || 0;
    return Number.isInteger(qty) ? String(qty) : String(parseFloat(qty.toFixed(3)));
}

/** حقول التاريخ تصل luxon أو نصاً (date_order بعد الدفع نص مُسلسل). */
const toDateTime = (value) =>
    value ? (typeof value === "string" ? deserializeDateTime(value) : value) : null;

/** نفس صيغة FERP: 10/2/2026 10:58:42 PM، بأرقام لاتينية مهما كانت لغة الكاشير. */
export function formatFerpDate(value) {
    const date = toDateTime(value);
    if (!date?.isValid) {
        return "";
    }
    return date
        .setZone("default")
        .reconfigure({ locale: "en-US", numberingSystem: "latn", outputCalendar: "gregory" })
        .toFormat("M/d/yyyy h:mm:ss a");
}

const unique = (values) => [...new Set(values.filter(Boolean))];

/** رمز QR الضريبي (TLV هيئة الزكاة) باسم البائع والرقم الضريبي المطبوعين نفسيهما. */
function ferpQrCode(order, sellerName, vat, total, tax) {
    if (order.company?.country_id?.code !== "SA" || order.isSettlement?.() || !window.ZXing) {
        return "";
    }
    const date = toDateTime(order.date_order) || DateTime.now();
    const value = computeSAQRCode(sellerName, vat, date, total, tax);
    const svg = new window.ZXing.BrowserQRCodeSvgWriter().write(value, 240, 240);
    return "data:image/svg+xml;base64," + window.btoa(new XMLSerializer().serializeToString(svg));
}

/** كل ما تعرضه الفاتورة، من الطلب وإعدادات الفرع. */
export function buildFerpReceipt(order, pos = null) {
    const config = order.config || order.config_id;
    const company = order.company || config?.company_id;
    const title = config?.hosny_receipt_title || company?.name || "";
    const vat = config?.hosny_receipt_vat || company?.vat || "";
    const address =
        config?.hosny_receipt_address ||
        [company?.street, company?.street2, company?.city].filter(Boolean).join(" ");
    const finalized = Boolean(order.finalized);

    const discountProductId = config?.discount_product_id?.id;
    const orderLines = order.lines || [];
    // سطور لا تظهر وحدها، كما في شاشة الطلب: مكوّنات الكومبو، ومكوّنات الوجبة
    // والمنتجات النهائية الإضافية (hosny_pos_meal_combo). سعرها يُضاف لسطر الوجبة.
    const parentOf = (line) =>
        line.combo_parent_id ||
        (line.is_meal_component && orderLines.find((l) => l.uuid === line.meal_parent_uuid)) ||
        (line.is_additional_final_product &&
            orderLines.find((l) => l.uuid === line.additional_final_parent_uuid)) ||
        null;
    const children = new Map();
    for (const line of orderLines) {
        const parent = parentOf(line);
        if (parent) {
            children.set(parent, [...(children.get(parent) || []), line]);
        }
    }
    const lines = [];
    let discountExcl = 0;
    for (const line of orderLines) {
        if (parentOf(line)) {
            continue;
        }
        const parts = [line, ...(children.get(line) || [])];
        const excl = parts.reduce((sum, part) => sum + (part.priceExcl || 0), 0);
        const incl = parts.reduce((sum, part) => sum + (part.priceIncl || 0), 0);
        const isDiscountLine =
            (discountProductId && line.product_id?.id === discountProductId) ||
            Boolean(line.is_reward_line);
        if (isDiscountLine) {
            discountExcl += excl;
            continue;
        }
        const qty = line.getQuantity ? line.getQuantity() : line.qty;
        // مكوّنات الكومبو تُكتب تحت اسمه كما في إيصال أودو؛ مكوّنات الوجبة لا.
        const details = (children.get(line) || [])
            .filter(
                (child) =>
                    child.combo_parent_id &&
                    !child.is_meal_component &&
                    !child.is_additional_final_product
            )
            .map((child) => `- ${child.getFullProductName?.() || child.full_product_name}`);
        const discount = line.getDiscount ? line.getDiscount() : line.discount;
        if (discount) {
            details.push(`خصم ${formatQty(discount)}%`);
        }
        lines.push({
            key: line.uuid || String(lines.length),
            name: line.getFullProductName?.() || line.full_product_name || line.product_id?.name,
            details,
            qty: formatQty(qty),
            unit: formatUnitPrice(qty ? excl / qty : 0),
            tax: formatMoney(incl - excl),
            total: formatMoney(incl),
        });
    }

    const tax = formatMoney(order.amountTaxes);
    const total = formatMoney(order.priceIncl);
    // صافي المبلغ = الأصناف قبل الضريبة وقبل الخصم العام
    const net = formatMoney((order.priceExcl || 0) - discountExcl);

    const payments = (order.payment_ids || []).filter((payment) => !payment.is_change);
    // أودو يكتب وقت الدفع في date_order عند إتمام الطلب (وهو نفس وقت رمز QR)، فوقت
    // فتح الطلب يُؤخذ من create_date حين يكون أقدم منه.
    const orderDate = toDateTime(order.date_order);
    const createdAt = toDateTime(order.create_date);
    const openedAt =
        createdAt?.isValid && orderDate?.isValid && createdAt < orderDate ? createdAt : orderDate;
    const orderType = pos?.getEffectiveOrderType?.(order) || order.order_type_id;
    const partner = order.partner_id;
    const note = (order.hosny_invoice_note || order.general_customer_note || "").trim();
    // الطاولة على كل فاتورة لطلب عليها (2026-10-09): «5 · أرضي»، و«سفري 3»
    // لطاولات طلبات الهاتف. السفري بلا طاولة يبقى بلا هذا السطر.
    const table = order.table_id?.rootTable || order.table_id;
    const floorName = (table?.floor_id?.name || "").trim();
    const tableLabel = table
        ? /سفري|takeaway|تيك/i.test(floorName)
            ? `سفري ${table.table_number}`
            : [String(table.table_number ?? ""), floorName].filter(Boolean).join(" · ")
        : "";

    return {
        logoUrl: config?.receiptLogoUrl || "",
        title,
        status: finalized ? "تم التسديد" : "لم يتم التسديد",
        vat,
        address,
        docTitle: order.isRefund ? "إشعار دائن مبسط" : "فاتورة ضريبية مبسطة",
        invoiceNumber: String(order.hosny_session_number || order.tracking_number || ""),
        orderType: orderType?.name || "",
        table: tableLabel,
        paymentType: unique(payments.map((payment) => payment.payment_method_id?.name)).join("، "),
        serial: order.pos_reference || "",
        date: formatFerpDate(openedAt),
        closedAt: finalized ? formatFerpDate(orderDate || DateTime.now()) : "",
        // ملاحظات الفاتورة (hosny_invoice_note)؛ ملاحظة أودو العامة احتياطاً لطلبات قديمة
        note,
        // سطر واحد قصير يبقى في مكانه بجانب «ملاحظة» كما في FERP؛ الأطول يأخذ عرض الفاتورة
        noteIsBlock: note.includes("\n") || note.length > 16,
        customer: partner?.name || "",
        customerPhone: partner?.phone || "",
        lines,
        net,
        discount: formatMoney(-discountExcl),
        tax,
        total,
        cashier: order.employee_id?.name || order.user_id?.name || "",
        printedAt: formatFerpDate(DateTime.now()),
        phone: config?.hosny_receipt_phone || company?.phone || "",
        qrCode: ferpQrCode(order, title, vat, total, tax),
    };
}

patch(OrderReceipt, { template: "hosny_pos_receipt.OrderReceipt" });

/**
 * على الشاشة (شاشة الإيصال) تُصغَّر الفاتورة لتملأ عرض إطارها بدل أن تُقص؛
 * نسخة الطباعة تُرسم خارج الشاشة في render-container فتبقى 576 نقطة كما هي.
 */
export function fitReceiptToScreen(el) {
    if (!el?.parentElement || el.closest(".render-container-parent")) {
        return;
    }
    const box = el.parentElement;
    const style = getComputedStyle(box);
    const padding = (parseFloat(style.paddingLeft) || 0) + (parseFloat(style.paddingRight) || 0);
    const available = box.clientWidth - padding;
    el.style.zoom =
        available > 0 && available < RECEIPT_WIDTH ? String(available / RECEIPT_WIDTH) : "";
}

patch(OrderReceipt.prototype, {
    setup() {
        super.setup(...arguments);
        this.ferpRoot = useRef("ferpRoot");
        const fit = () => fitReceiptToScreen(this.ferpRoot.el);
        onMounted(fit);
        onPatched(fit);
    },

    get ferp() {
        return buildFerpReceipt(this.order, this.env.services.pos);
    },
});

patch(PosStore.prototype, {
    /**
     * «رقم الفاتورة» هو رقم الطلب في الوردية ويعطيه الخادم عند أول مزامنة؛ فاتورة
     * طلب لم يُرسل بعد («طباعة» قبل إرسال الطلب) تُزامن الطلب أولاً حتى تحمل نفس
     * رقم تذكرة المطبخ والإيصال. لو فشلت المزامنة لا نوقف الطباعة (يخرج رقم التتبّع).
     */
    async printReceipt({ order = this.getOrder() } = {}) {
        if (
            order &&
            !order.finalized &&
            !order.hosny_session_number &&
            order.lines?.length &&
            !this.data.network.offline
        ) {
            try {
                await this.syncAllOrders({ orders: [order], force: true });
            } catch {
                // الطباعة أهم من الرقم
            }
        }
        await loadReceiptFonts();
        return await super.printReceipt(...arguments);
    },
});
