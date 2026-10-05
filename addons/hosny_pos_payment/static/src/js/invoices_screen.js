/** @odoo-module **/

/**
 * «تسديد الفواتير» بتقسيمة شاشة FERP (manageorderlist): فلاتر فوق، وجدول
 * فواتير الفرع من الخادم تحته — المدفوعة والمفتوحة والأجل والمرتجعة.
 *
 * الشاشة نفسها (HosnyPaymentOrdersScreen) يسجلها hosny_pos_controls ويفتحها
 * زرّه؛ هنا يُستبدل قالبها ويُضاف لها جلب الفواتير والأزرار.
 * العمليات تحمّل الطلب من الخادم بنفس طريقة شاشة الطلبات في أودو
 * (loadServerOrders)، إلا إن كان مفتوحاً على هذا الجهاز فيُستخدم كما هو.
 */
import { onMounted, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { deserializeDateTime, serializeDateTime } from "@web/core/l10n/dates";
import { HosnyPaymentOrdersScreen } from "@hosny_pos_controls/js/payment_orders_screen";
import { HosnyReceiptPreview } from "@hosny_pos_payment/js/payment_screen";

const { DateTime } = luxon;
const pad = (n) => String(n).padStart(2, "0");

const STATUS = {
    paid: { label: "مدفوعة", tone: "green" },
    pay_later: { label: "أجل", tone: "amber" },
    open: { label: "غير مدفوعة", tone: "red" },
    refund: { label: "مرتجع", tone: "violet" },
    cancel: { label: "ملغاة", tone: "gray" },
};

/** «2026-10-05T17:56» لحقول datetime-local بالتوقيت المحلي. */
const toInput = (dt) => dt.toFormat("yyyy-LL-dd'T'HH:mm");

function defaultFilters() {
    const today = DateTime.local();
    return {
        dateFrom: toInput(today.startOf("day")),
        dateTo: toInput(today.endOf("day")),
        orderTypeId: "",
        number: "",
        status: "all",
        tableId: "",
    };
}

patch(HosnyPaymentOrdersScreen, {
    template: "hosny_pos_payment.InvoicesScreen",
});

patch(HosnyPaymentOrdersScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.inv = useState({
            filters: defaultFilters(),
            rows: [],
            types: [],
            tables: [],
            totalCount: 0,
            limit: 0,
            loading: false,
            busyId: null,
            sort: { key: "date", desc: true },
        });
        onMounted(() => this.invSearch());
    },

    // ── الجلب ───────────────────────────────────────────────────────────
    invToServer(value) {
        if (!value) {
            return false;
        }
        const dt = DateTime.fromISO(value);
        return dt.isValid ? serializeDateTime(dt) : false;
    },
    async invSearch() {
        const f = this.inv.filters;
        this.inv.loading = true;
        try {
            const result = await this.pos.data.call("pos.order", "hosny_invoice_list", [
                this.pos.config.id,
                {
                    date_from: this.invToServer(f.dateFrom),
                    date_to: this.invToServer(f.dateTo),
                    order_type_id: f.orderTypeId || false,
                    number: f.number,
                    status: f.status,
                    table_id: f.tableId || false,
                },
            ]);
            this.inv.rows = result.rows;
            this.inv.types = result.types;
            this.inv.tables = result.tables;
            this.inv.totalCount = result.total_count;
            this.inv.limit = result.limit;
        } catch {
            this.pos.notification?.add("تعذّر جلب الفواتير — تأكد من الاتصال بالسيرفر.", { type: "warning" });
        } finally {
            this.inv.loading = false;
        }
    },
    invReset() {
        this.inv.filters = defaultFilters();
        this.invSearch();
    },

    // ── العرض ───────────────────────────────────────────────────────────
    invMoney(amount) {
        const symbol = this.pos.currency?.symbol ?? "";
        const number = this.env.utils.formatCurrency(amount || 0, false);
        return symbol ? `⁦${number} ${symbol}⁩` : number;
    },
    invLocal(row) {
        return deserializeDateTime(row.date).setZone("default");
    },
    invDate(row) {
        const d = this.invLocal(row);
        return `${pad(d.day)}-${pad(d.month)}-${d.year}`;
    },
    invTime(row) {
        const d = this.invLocal(row);
        return `${pad(d.hour % 12 || 12)}:${pad(d.minute)} ${d.hour < 12 ? "ص" : "م"}`;
    },
    invStatus(row) {
        return STATUS[row.status] || STATUS.paid;
    },
    invPlace(row) {
        return [row.type, row.table && `طاولة ${row.table}`].filter(Boolean).join(" · ");
    },
    get invRows() {
        const { key, desc } = this.inv.sort;
        const value = (row) =>
            key === "date" ? row.date
            : key === "amount" ? row.amount
            : key === "prints" ? row.prints
            : key === "number" ? Number(row.number) || row.number
            : (row[key] || "").toString();
        return [...this.inv.rows].sort((a, b) => {
            const va = value(a);
            const vb = value(b);
            const cmp = typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb), "ar");
            return desc ? -cmp : cmp;
        });
    },
    invSortBy(key) {
        const sort = this.inv.sort;
        this.inv.sort = { key, desc: sort.key === key ? !sort.desc : true };
    },
    invSortIcon(key) {
        const sort = this.inv.sort;
        return sort.key !== key ? "fa-sort" : sort.desc ? "fa-sort-desc" : "fa-sort-asc";
    },
    get invTotals() {
        const rows = this.inv.rows;
        return {
            count: rows.length,
            amount: rows.reduce((sum, row) => sum + (row.status === "cancel" ? 0 : row.amount), 0),
            open: rows.filter((row) => row.status === "open").length,
        };
    },

    // ── العمليات ────────────────────────────────────────────────────────
    /** الطلب في الذاكرة إن كان مفتوحاً على هذا الجهاز، وإلا يُحمَّل من الخادم. */
    async invLoadOrder(row) {
        const local = this.pos.models["pos.order"].find((o) => o.uuid === row.uuid || o.id === row.id);
        if (local) {
            return local;
        }
        const orders = await this.pos.data.loadServerOrders([["id", "=", row.id]]);
        return orders[0] || null;
    },
    async invRun(row, action) {
        if (this.inv.busyId) {
            return;
        }
        this.inv.busyId = row.id;
        try {
            const order = await this.invLoadOrder(row);
            if (!order) {
                this.pos.notification?.add("تعذّر تحميل الفاتورة.", { type: "danger" });
                return;
            }
            await action(order);
        } catch {
            this.pos.notification?.add("تعذّر تنفيذ العملية — تأكد من الاتصال بالسيرفر.", { type: "warning" });
        } finally {
            this.inv.busyId = null;
        }
    },
    /** «طباعة فورية»: الإيصال (للمفتوحة: الفاتورة المبدئية بلا زيادة عدّاد الطباعة). */
    invPrint(row) {
        return this.invRun(row, async (order) => {
            const isOpen = row.status === "open";
            await this.pos.printReceipt({ order, printBillActionTriggered: isOpen });
            if (!isOpen && typeof order.nb_print === "number") {
                row.prints = order.nb_print;
            }
        });
    },
    invView(row) {
        return this.invRun(row, async (order) => {
            this.pos.dialog.add(HosnyReceiptPreview, { order });
        });
    },
    /** «تسديد»: الفاتورة المفتوحة في شاشة الدفع. */
    invPay(row) {
        return this.invRun(row, async (order) => {
            this.pos.setOrder(order);
            this.pos.navigate("PaymentScreen", { orderUuid: order.uuid });
        });
    },

    /** تصدير الجدول الحالي إلى ملف يفتحه Excel (CSV بترميز UTF-8). */
    invExport() {
        const header = ["التاريخ", "الوقت", "رقم الفاتورة", "النوع", "الدفع", "الصافي", "مرتجع", "العميل", "رقم الهاتف", "عدد مرات الطباعة"];
        const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
        const lines = this.invRows.map((row) =>
            [
                this.invDate(row),
                this.invTime(row),
                row.number,
                this.invPlace(row),
                this.invStatus(row).label,
                row.amount.toFixed(2),
                row.refunded ? "نعم" : "",
                row.partner,
                row.phone,
                row.prints,
            ].map(esc).join(",")
        );
        const csv = "﻿" + [header.map(esc).join(","), ...lines].join("\r\n");
        const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
        const link = document.createElement("a");
        link.href = url;
        link.download = `invoices-${DateTime.local().toFormat("yyyy-LL-dd-HHmm")}.csv`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
});
