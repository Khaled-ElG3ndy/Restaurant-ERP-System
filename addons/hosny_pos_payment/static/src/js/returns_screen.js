/** @odoo-module **/

/**
 * «مردود المبيعات» بتقسيمة FERP، صفحة كاملة خلف زر «استرداد الأموال».
 *
 *   يمين: رقم الفاتورة / رقم المردود / العميل، التواريخ والكاشير، طريقة الدفع
 *         والمبلغ المدفوع، وملخص المردود.
 *   يسار: بطاقات أصناف الفاتورة (المباعة والمتبقية) مع «اختيار الكل»، وجدول
 *         الأصناف بكمية المردود وسبب الإلغاء لكل صنف، وسبب الاسترجاع.
 *
 * الفاتورة تُختار من نافذة بحث (hosny_invoice_list بفلتر refundable) ثم تُحمّل
 * كاملة (loadServerOrders). «حفظ المردود» يبني طلب الإرجاع بطريقة أودو نفسها
 * (TicketScreen.onDoRefund: أسطر بكمية سالبة مربوطة بـ refunded_orderline_id)
 * ويفتح شاشة الدفع وفيها سطر بطريقة الدفع المختارة. الأسهم أعلى الصفحة تتصفح
 * المرتجعات السابقة للعرض والطباعة.
 *
 * البيانات تُنسخ إلى كائنات عادية عند التحميل؛ العرض لا يقرأ نماذج نقطة البيع
 * (درس «نقل الطلبات»: قراءة الأسعار أثناء العرض كانت تبطئ كل ضغطة).
 */
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { deserializeDateTime } from "@web/core/l10n/dates";

const EPS = 0.00001;
const PAGE = "HosnyReturnScreen";
const FEE_KIND = {
    HOSNY_FEE_SERVICE: "service",
    HOSNY_FEE_DELIVERY: "delivery",
    HOSNY_FEE_DRIVER: "delivery",
};

const pad = (n) => String(n).padStart(2, "0");
function dateText(value) {
    if (!value) {
        return "—";
    }
    const dt = typeof value === "string" ? deserializeDateTime(value) : value;
    return `${pad(dt.day)}/${pad(dt.month)}/${dt.year}`;
}
function todayText() {
    const d = new Date();
    return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
}
function qtyText(qty) {
    return String(Math.round((Number(qty) || 0) * 1000) / 1000);
}
function lineName(line) {
    return line.getFullProductName?.() || line.full_product_name || line.product_id?.display_name || "";
}
function orderNumber(order) {
    return String(order?.hosny_session_number || order?.tracking_number || order?.pos_reference || order?.name || "");
}

// ── نافذة اختيار الفاتورة ─────────────────────────────────────────────
export class HosnyReturnPicker extends Component {
    static template = "hosny_pos_payment.ReturnPicker";
    static components = { Dialog };
    static props = { getPayload: Function, close: Function };

    setup() {
        this.pos = usePos();
        this.state = useState({ search: "", typeId: "", rows: [], types: [], picked: null, loading: false, error: "" });
        this.load();
    }
    async load() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await this.pos.data.call("pos.order", "hosny_invoice_list", [
                this.pos.config.id,
                { refundable: true, search: this.state.search, order_type_id: this.state.typeId || false, limit: 200 },
            ]);
            this.state.rows = result.rows;
            this.state.types = result.types;
            if (!result.rows.some((r) => r.id === this.state.picked)) {
                this.state.picked = null;
            }
        } catch {
            this.state.error = "تعذّر جلب الفواتير — تأكد من الاتصال بالسيرفر.";
        } finally {
            this.state.loading = false;
        }
    }
    money(amount) {
        return hrMoney(this.pos, amount);
    }
    dateText(value) {
        return dateText(value);
    }
    pick(row) {
        this.state.picked = row.id;
    }
    choose(row) {
        this.props.getPayload(row);
        this.props.close();
    }
    show() {
        const row = this.state.rows.find((r) => r.id === this.state.picked);
        if (row) {
            this.choose(row);
        }
    }
}

function hrMoney(pos, amount) {
    const number = (Number(amount) || 0).toFixed(pos.currency?.decimal_places ?? 2);
    return `⁦${number} ${pos.currency?.symbol || "SR"}⁩`;
}

// ── الصفحة ────────────────────────────────────────────────────────────
export class HosnyReturnScreen extends Component {
    static template = "hosny_pos_payment.ReturnScreen";
    static props = {};

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.order = null; // الفاتورة الأصلية (نموذج نقطة البيع، لا يُقرأ أثناء العرض)
        this.state = useState(this.emptyState());
        this.history = useState({ rows: [], index: -1, loading: false });
    }

    emptyState() {
        return {
            mode: "new", // new | view
            loading: false,
            saving: false,
            error: "",
            head: null, // بيانات الفاتورة أو المردود المعروض
            rows: [],
            sel: {},
            checked: {},
            notes: {},
            editing: null,
            reason: "",
            methodId: null,
        };
    }

    // ── مساعدات العرض ───────────────────────────────────────────────────
    money(amount) {
        return hrMoney(this.pos, amount);
    }
    qtyText(qty) {
        return qtyText(qty);
    }
    get today() {
        return todayText();
    }
    get cashierName() {
        return this.pos.getCashier?.()?.name || this.pos.cashier?.name || this.pos.user?.name || "—";
    }
    get methods() {
        return (this.pos.config.payment_method_ids || []).map((m) => ({ id: m.id, name: m.name }));
    }
    get stockName() {
        const type = this.pos.config.picking_type_id;
        return type?.warehouse_id?.name || type?.default_location_src_id?.display_name || "مخزن نقطة البيع";
    }
    get isView() {
        return this.state.mode === "view";
    }

    // ── التحديد ─────────────────────────────────────────────────────────
    selQty(row) {
        return this.state.sel[row.uuid] || 0;
    }
    isChecked(row) {
        return this.selQty(row) > EPS;
    }
    toggleRow(row) {
        if (this.isView || row.remaining <= EPS) {
            return;
        }
        this.state.sel[row.uuid] = this.isChecked(row) ? 0 : row.remaining;
    }
    addOne(row) {
        if (this.isView || row.remaining <= EPS) {
            return;
        }
        this.state.sel[row.uuid] = Math.min(row.remaining, Math.round((this.selQty(row) + 1) * 1000) / 1000);
    }
    stepQty(row, direction) {
        if (this.isView) {
            return;
        }
        const next = Math.round((this.selQty(row) + direction) * 1000) / 1000;
        this.state.sel[row.uuid] = Math.max(0, Math.min(row.remaining, next));
    }
    typeQty(row, ev) {
        const raw = String(ev.target.value).replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d)).replace(",", ".");
        const value = parseFloat(raw);
        const qty = Number.isFinite(value) ? Math.max(0, Math.min(row.remaining, value)) : 0;
        this.state.sel[row.uuid] = qty;
        if (qty !== value) {
            ev.target.value = qty ? qtyText(qty) : "";
        }
    }
    get allSelected() {
        const open = this.state.rows.filter((r) => r.remaining > EPS);
        return open.length > 0 && open.every((r) => Math.abs(this.selQty(r) - r.remaining) < EPS);
    }
    toggleAll() {
        if (this.isView) {
            return;
        }
        const all = !this.allSelected;
        for (const row of this.state.rows) {
            this.state.sel[row.uuid] = all ? row.remaining : 0;
        }
    }
    clearRow(row) {
        this.state.sel[row.uuid] = 0;
        delete this.state.notes[row.uuid];
        if (this.state.editing === row.uuid) {
            this.state.editing = null;
        }
    }
    editNote(row) {
        if (!this.isView) {
            this.state.editing = this.state.editing === row.uuid ? null : row.uuid;
        }
    }
    setReason(ev) {
        this.state.reason = ev.target.value;
    }
    setNote(row, ev) {
        this.state.notes[row.uuid] = ev.target.value;
    }

    /** الملخص في مرور واحد (للمردود الجديد من التحديد، وللمعروض من أسطره). */
    get summary() {
        const s = { items: 0, qty: 0, excl: 0, tax: 0, discount: 0, service: 0, delivery: 0, incl: 0 };
        for (const row of this.state.rows) {
            const q = this.isView ? row.returned : this.selQty(row);
            if (q <= EPS) {
                continue;
            }
            s.items++;
            s.qty += q;
            s.excl += row.unitExcl * q;
            s.incl += row.unitIncl * q;
            s.discount += row.unitDiscount * q;
            if (row.kind === "service") {
                s.service += row.unitIncl * q;
            } else if (row.kind === "delivery") {
                s.delivery += row.unitIncl * q;
            }
        }
        s.tax = s.incl - s.excl;
        return s;
    }

    // ── تحميل الفاتورة ──────────────────────────────────────────────────
    async pickInvoice() {
        const row = await makeAwaitable(this.dialog, HosnyReturnPicker, {});
        if (row) {
            await this.loadInvoice(row);
        }
    }
    async loadOrder(id, uuid) {
        const local = this.pos.models["pos.order"].find((o) => o.id === id || (uuid && o.uuid === uuid));
        if (local && local.lines?.length) {
            return local;
        }
        const orders = await this.pos.data.loadServerOrders([["id", "=", id]]);
        return orders?.[0] || null;
    }
    snapshotRow(line, { returned = 0 } = {}) {
        const qty = Math.abs(line.qty) || 0;
        const incl = Math.abs(line.priceIncl ?? 0);
        const excl = Math.abs(line.priceExcl ?? incl);
        const gross = (line.price_unit || 0) * qty;
        return {
            uuid: line.uuid,
            name: lineName(line),
            sold: qty,
            remaining: Math.max(0, qty - (line.refundedQty || 0)),
            returned,
            discountPct: line.discount || 0,
            unitIncl: qty ? incl / qty : 0,
            unitExcl: qty ? excl / qty : 0,
            unitDiscount: qty ? (gross * (line.discount || 0)) / 100 / qty : 0,
            kind: FEE_KIND[line.product_id?.default_code] || null,
            combo: Boolean(line.combo_line_ids?.length),
        };
    }
    async loadInvoice(row) {
        this.state.loading = true;
        this.state.error = "";
        try {
            const order = await this.loadOrder(row.id, row.uuid);
            if (!order) {
                this.state.error = "تعذّر تحميل الفاتورة.";
                return;
            }
            this.order = order;
            const lines = (order.lines || []).filter((l) => !l.combo_parent_id && l.qty > EPS);
            const firstPayment = (order.payment_ids || []).find((p) => p.amount > 0);
            Object.assign(this.state, this.emptyState(), {
                mode: "new",
                head: {
                    number: row.number || orderNumber(order),
                    refundNumber: "جديد",
                    partner: order.partner_id?.name || row.partner || "",
                    phone: order.partner_id?.phone || row.phone || "",
                    invoiceDate: dateText(row.date || order.date_order),
                    refundDate: todayText(),
                    invoiceCashier: row.cashier || order.employee_id?.name || order.user_id?.name || "—",
                    refundCashier: this.cashierName,
                    paid: Math.abs(order.amount_paid ?? row.amount ?? 0),
                    type: row.type || "",
                },
                rows: lines.map((l) => this.snapshotRow(l)),
                methodId: firstPayment?.payment_method_id?.id || this.methods[0]?.id || null,
            });
            this._lines = Object.fromEntries(lines.map((l) => [l.uuid, l]));
            this.history.index = -1;
            if (!this.state.rows.some((r) => r.remaining > EPS)) {
                this.state.error = "كل أصناف هذه الفاتورة مُرتجعة من قبل.";
            }
        } catch {
            this.state.error = "تعذّر تحميل الفاتورة — تأكد من الاتصال بالسيرفر.";
        } finally {
            this.state.loading = false;
        }
    }
    newReturn() {
        this.order = null;
        this._lines = {};
        Object.assign(this.state, this.emptyState());
        this.history.index = -1;
    }

    // ── حفظ المردود ─────────────────────────────────────────────────────
    get canSave() {
        return !this.isView && this.order && this.summary.items > 0 && !this.state.saving;
    }
    _createRefundLine(source, destination, qty) {
        const alreadyRefundedLots = (source.refund_orderline_ids || [])
            .filter((item) => !["cancel", "draft"].includes(item.order_id?.state))
            .flatMap((item) => item.pack_lot_ids || [])
            .map((lot) => lot.lot_name);
        const lots = (source.pack_lot_ids || [])
            .map((lot) => lot.lot_name)
            .filter((name) => !alreadyRefundedLots.includes(name));
        return this.pos.models["pos.order.line"].create({
            qty: -qty,
            price_unit: source.price_unit,
            price_subtotal_incl: source.price_subtotal_incl,
            product_id: source.product_id,
            order_id: destination,
            discount: source.discount,
            tax_ids: (source.tax_ids || []).map((tax) => ["link", tax]),
            refunded_orderline_id: source,
            pack_lot_ids: lots.slice(0, qty).map((lot_name) => ["create", { lot_name }]),
            price_type: "automatic",
            attribute_value_ids: (source.attribute_value_ids || []).map((attr) => ["link", attr]),
        });
    }
    async save() {
        if (!this.canSave) {
            return;
        }
        this.state.saving = true;
        this.state.error = "";
        try {
            const order = this.order;
            const partner = order.partner_id || false;
            const destination = this.pos.addNewOrder({ partner_id: partner });
            destination.is_refund = true;
            destination.pricelist_id = order.pricelist_id;
            for (const row of this.state.rows) {
                const qty = this.selQty(row);
                const source = this._lines[row.uuid];
                if (qty <= EPS || !source) {
                    continue;
                }
                const parent = this._createRefundLine(source, destination, qty);
                const note = (this.state.notes[row.uuid] || "").trim();
                if (note) {
                    parent.customer_note = note;
                }
                const children = (source.combo_line_ids || []).map((child) =>
                    this._createRefundLine(child, destination, source.qty ? (child.qty * qty) / source.qty : 0)
                );
                if (children.length) {
                    parent.combo_line_ids = [["link", ...children]];
                }
            }
            destination.fiscal_position_id = order.fiscal_position_id || false;
            if (partner && !destination.getPartner?.()) {
                destination.setPartner?.(partner);
            }
            destination.refunded_order_id = order;
            const reason = this.state.reason.trim();
            if (reason) {
                destination.internal_note = reason;
            }
            this.pos.setOrder(destination);
            const method = this.pos.models["pos.payment.method"].get(this.state.methodId);
            if (method) {
                destination.addPaymentline(method);
            }
            destination.setScreenData?.({ name: "PaymentScreen" });
            this.pos.navigate("PaymentScreen", { orderUuid: destination.uuid });
        } catch (error) {
            this.state.error = error?.message || "تعذّر إنشاء المردود.";
        } finally {
            this.state.saving = false;
        }
    }

    // ── المرتجعات السابقة ───────────────────────────────────────────────
    async loadHistory() {
        if (this.history.rows.length || this.history.loading) {
            return;
        }
        this.history.loading = true;
        try {
            const result = await this.pos.data.call("pos.order", "hosny_invoice_list", [
                this.pos.config.id,
                { status: "refund", limit: 200 },
            ]);
            this.history.rows = result.rows;
        } catch {
            this.notification.add("تعذّر جلب المرتجعات السابقة.", { type: "warning" });
        } finally {
            this.history.loading = false;
        }
    }
    get historyCount() {
        return this.history.rows.length;
    }
    async goHistory(where) {
        await this.loadHistory();
        const count = this.history.rows.length;
        if (!count) {
            this.notification.add("لا توجد مرتجعات سابقة.", { type: "info" });
            return;
        }
        let index = this.history.index;
        if (where === "first") {
            index = 0;
        } else if (where === "last") {
            index = count - 1;
        } else if (where === "prev") {
            index = index < 0 ? 0 : Math.max(0, index - 1);
        } else {
            index = index < 0 ? 0 : Math.min(count - 1, index + 1);
        }
        await this.showRefund(index);
    }
    async showRefund(index) {
        const row = this.history.rows[index];
        if (!row) {
            return;
        }
        this.state.loading = true;
        try {
            const refund = await this.loadOrder(row.id, row.uuid);
            if (!refund) {
                this.state.error = "تعذّر تحميل المردود.";
                return;
            }
            this.order = null;
            this.viewed = refund;
            const lines = (refund.lines || []).filter((l) => !l.combo_parent_id);
            const payments = (refund.payment_ids || []).map((p) => p.payment_method_id?.name).filter(Boolean);
            Object.assign(this.state, this.emptyState(), {
                mode: "view",
                head: {
                    number: row.refunded_number || "—",
                    refundNumber: row.number,
                    partner: row.partner || "",
                    phone: row.phone || "",
                    invoiceDate: dateText(refund.refunded_order_id?.date_order),
                    refundDate: dateText(row.date),
                    invoiceCashier:
                        refund.refunded_order_id?.employee_id?.name || refund.refunded_order_id?.user_id?.name || "—",
                    refundCashier: row.cashier || "—",
                    paid: Math.abs(row.amount || 0),
                    type: row.type || "",
                    methods: [...new Set(payments)].join("، ") || "—",
                },
                rows: lines.map((l) => {
                    const snap = this.snapshotRow(l, { returned: Math.abs(l.qty) });
                    const origin = l.refunded_orderline_id;
                    snap.sold = origin ? Math.abs(origin.qty) : snap.returned;
                    snap.remaining = origin ? Math.max(0, Math.abs(origin.qty) - (origin.refundedQty || 0)) : 0;
                    return snap;
                }),
                notes: Object.fromEntries(lines.filter((l) => l.customer_note).map((l) => [l.uuid, l.customer_note])),
                reason: refund.internal_note || "",
            });
            this.history.index = index;
        } catch {
            this.state.error = "تعذّر تحميل المردود — تأكد من الاتصال بالسيرفر.";
        } finally {
            this.state.loading = false;
        }
    }

    // ── أزرار الشريط ────────────────────────────────────────────────────
    async print() {
        const order = this.isView ? this.viewed : this.order;
        if (!order) {
            this.notification.add("اختر فاتورة أو مردوداً أولاً.", { type: "info" });
            return;
        }
        try {
            await this.pos.printReceipt({ order });
        } catch {
            this.notification.add("تعذّرت الطباعة.", { type: "warning" });
        }
    }
    async refresh() {
        if (this.isView) {
            this.history.rows = [];
            await this.loadHistory();
            await this.showRefund(Math.min(this.history.index, this.history.rows.length - 1));
        } else if (this.order) {
            await this.loadInvoice({ id: this.order.id, uuid: this.order.uuid, number: this.state.head?.number });
        }
    }
    back() {
        const order = this.pos.getOrder();
        if (order && !order.finalized) {
            this.pos.navigate("ProductScreen", { orderUuid: order.uuid });
        } else {
            const page = this.pos.defaultPage;
            this.pos.navigate(page.page, page.params);
        }
    }
}

registry.category("pos_pages").add(PAGE, {
    name: PAGE,
    component: HosnyReturnScreen,
    route: `/pos/ui/${odoo.pos_config_id}/returns`,
    params: {},
});

patch(ControlButtons.prototype, {
    clickRefund() {
        this.dialog?.closeAll?.();
        this.pos.navigate(PAGE);
    },
});
