/** @odoo-module **/
/**
 * اعتماد إلغاء صنف بعد إرساله للمطبخ (طلب 2026-10-05).
 *
 * ما أُرسل للمطبخ (last_order_preparation_change) لا يُحذف ولا تنقص كميته إلا
 * بعد أن يكتب الكاشير سبب الإلغاء ويعتمده حساب مفعّل له ذلك بكلمة سر الإلغاء.
 * الفحص على الخادم (pos.audit.log.hosny_approve_void) ويُكتب في سجل الإلغاءات.
 *
 * المداخل المحروسة: زر سلة المهملات في السطر، إنقاص الكمية بالكيبورد أو لوحة
 * الأرقام (qty_entry.js)، وحذف الطلب كله. النقل والدمج والتقسيم لا تمر من هنا:
 * تنقل الأصناف ولا تلغيها.
 */
import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

export const HOSNY_VOID_REASONS = [
    "طلب العميل",
    "خطأ في الطلب",
    "تأخر الطلب",
    "الصنف غير متوفر",
    "مشكلة في الجودة",
];

/** الكمية التي وصلت المطبخ من هذا السطر (0 لو لم يُرسل). */
export function hosnySentQty(line) {
    const sent = line?.order_id?.last_order_preparation_change?.lines?.[line.preparationKey];
    return Math.max(0, Number(sent?.quantity) || 0);
}

function lineUnitPrice(line) {
    const qty = line.getQuantity?.() || line.qty || 0;
    const total = line.displayPrice ?? line.getDisplayPrice?.() ?? 0;
    return qty ? total / qty : 0;
}

export class HosnyVoidApprovalDialog extends Component {
    static template = "hosny_pos_controls.VoidApprovalDialog";
    static components = { Dialog };
    static props = {
        title: String,
        summary: Array,
        details: Object,
        getPayload: Function,
        close: Function,
    };

    setup() {
        this.reasons = HOSNY_VOID_REASONS;
        this.state = useState({
            loading: true,
            approvers: [],
            approverId: null,
            password: "",
            reason: "",
            error: "",
            busy: false,
        });
        this.reasonRef = useRef("reason");
        this.passwordRef = useRef("password");
        onMounted(() => this.loadApprovers());
    }

    get pos() {
        return this.env.services.pos;
    }

    async loadApprovers() {
        try {
            const approvers = await this.pos.data.call("pos.audit.log", "hosny_void_approvers", [
                this.pos.config.id,
            ]);
            this.state.approvers = approvers || [];
            if (this.state.approvers.length === 1) {
                this.state.approverId = this.state.approvers[0].id;
            }
        } catch {
            this.state.error = _t("تعذّر الاتصال بالخادم — لا يمكن اعتماد الإلغاء بدون اتصال.");
        } finally {
            this.state.loading = false;
        }
        this.reasonRef.el?.focus();
    }

    addReason(reason) {
        const current = this.state.reason.trim();
        this.state.reason = current ? `${current} — ${reason}` : reason;
        if (this.reasonRef.el) {
            this.reasonRef.el.value = this.state.reason;
        }
    }

    selectApprover(id) {
        this.state.approverId = id;
        this.state.error = "";
        this.passwordRef.el?.focus();
    }

    get canSubmit() {
        return (
            !this.state.busy &&
            !this.state.loading &&
            this.state.reason.trim().length > 0 &&
            this.state.approverId &&
            this.state.password.length > 0
        );
    }

    onPasswordKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.submit();
        }
    }

    async submit() {
        if (!this.state.reason.trim()) {
            this.state.error = _t("اكتب سبب الإلغاء أولاً.");
            this.reasonRef.el?.focus();
            return;
        }
        if (!this.state.approverId) {
            this.state.error = _t("اختر من يعتمد الإلغاء.");
            return;
        }
        if (!this.state.password) {
            this.state.error = _t("اكتب كلمة سر الإلغاء.");
            this.passwordRef.el?.focus();
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        let result;
        try {
            result = await this.pos.data.call("pos.audit.log", "hosny_approve_void", [
                this.state.approverId,
                this.state.password,
                { ...this.props.details, reason: this.state.reason.trim() },
            ]);
        } catch {
            result = { ok: false, error: _t("تعذّر الاتصال بالخادم — لا يمكن اعتماد الإلغاء بدون اتصال.") };
        }
        this.state.busy = false;
        if (!result?.ok) {
            this.state.error = result?.error || _t("لم يُعتمد الإلغاء.");
            this.state.password = "";
            if (this.passwordRef.el) {
                this.passwordRef.el.value = "";
                this.passwordRef.el.focus();
            }
            return;
        }
        this.props.getPayload({ approver: result.approver, reason: this.state.reason.trim() });
        this.props.close();
    }
}

patch(PosStore.prototype, {
    /**
     * يفتح نافذة الاعتماد. lines: [{ line, after }] — after الكمية الجديدة (0 = حذف).
     * يرجع { approver, reason } أو null لو تراجع الكاشير.
     */
    async hosnyApproveVoid(order, lines, { kind = "line" } = {}) {
        const rows = lines
            .map(({ line, after }) => {
                const sent = hosnySentQty(line);
                const kept = Math.min(Math.max(after, 0), sent);
                const cancelled = sent - kept;
                return {
                    product: line.getFullProductName?.() || line.full_product_name || line.product_id?.display_name || "",
                    quantity_before: sent,
                    quantity_after: kept,
                    cancelled,
                    amount: cancelled * lineUnitPrice(line),
                };
            })
            .filter((row) => row.cancelled > 0);
        if (!rows.length) {
            return { approver: null, reason: "" };
        }
        const table = order.table_id
            ? [order.table_id.floor_id?.name, order.table_id.table_number].filter(Boolean).join(" ")
            : "";
        const details = {
            kind,
            config_id: this.config.id,
            session_id: this.session?.id,
            order_id: typeof order.id === "number" ? order.id : false,
            order_uuid: order.uuid,
            order_ref: order.pos_reference || order.name || "",
            table,
            cashier: this.getCashier?.()?.name || this.user?.name || "",
            lines: rows.map(({ cancelled, ...row }) => row),
        };
        const fmt = (n) => (Number.isInteger(n) ? String(n) : String(parseFloat(n.toFixed(3))));
        const summary = rows.map((row) => ({
            product: row.product,
            text:
                row.quantity_after > 0
                    ? `${_t("إلغاء")} ${fmt(row.cancelled)} ${_t("من")} ${fmt(row.quantity_before)}`
                    : `${_t("إلغاء الكمية المرسلة كلها")} (${fmt(row.quantity_before)})`,
            amount: this.env.utils.formatCurrency(row.amount),
        }));
        const result = await makeAwaitable(this.dialog, HosnyVoidApprovalDialog, {
            title: kind === "order" ? _t("حذف طلب مُرسل للمطبخ") : _t("إلغاء صنف مُرسل للمطبخ"),
            summary,
            details,
        });
        if (!result) {
            return null;
        }
        this.notification.add(
            _t("اعتمد الإلغاء: %s. اضغط «إرسال الطلب» ليصل الإلغاء للمطبخ.", result.approver),
            { type: "success" }
        );
        return result;
    },

    /* ── سلة المهملات ── */
    async hosnyGuardedRemoveLine(line) {
        const order = line?.order_id;
        if (!order) {
            return false;
        }
        if (hosnySentQty(line) > 0 && !line.refunded_orderline_id) {
            const approval = await this.hosnyApproveVoid(order, [{ line, after: 0 }]);
            if (!approval) {
                return false;
            }
        }
        order.removeOrderline(line);
        return true;
    },

    /* ── إنقاص الكمية بالكيبورد / لوحة الأرقام ──
     * كل رقم يُطبَّق فوراً («1» ثم «12»)، فلا يُسأل عند كل ضغطة: القيمة الأقل من
     * المُرسل لا تُطبَّق وتنتظر، ويُطلب الاعتماد حين تنتهي الكتابة. */
    _hosnyEntryApply(line, mode, value, opts = {}) {
        const entry = this.hosnyEntry;
        if (
            mode === "quantity" &&
            !opts.raw &&
            !line.refunded_orderline_id &&
            value >= 0 &&
            value < hosnySentQty(line)
        ) {
            entry.hosnyPendingLow = { lineUuid: line.uuid, value };
            return true;
        }
        entry.hosnyPendingLow = null;
        return super._hosnyEntryApply(...arguments);
    },

    hosnyEntryClose() {
        const pending = this.hosnyEntry.hosnyPendingLow;
        this.hosnyEntry.hosnyPendingLow = null;
        const result = super.hosnyEntryClose(...arguments);
        if (pending) {
            this.hosnyConfirmPendingReduction(pending);
        }
        return result;
    },

    async hosnyConfirmPendingReduction({ lineUuid, value }) {
        const order = this.getOrder();
        const line = order?.lines?.find((l) => l.uuid === lineUuid);
        if (!line || order.finalized) {
            return;
        }
        const approval = await this.hosnyApproveVoid(order, [{ line, after: value }]);
        if (!approval || !order.lines.includes(line)) {
            return;
        }
        if (value === 0) {
            order.removeOrderline(line);
        } else {
            line.setQuantity(value, Boolean(line.combo_line_ids?.length));
        }
    },

    /* ── حذف الطلب كله ── */
    async beforeDeleteOrder(order) {
        const canDelete = await super.beforeDeleteOrder(...arguments);
        if (!canDelete) {
            return false;
        }
        const sentLines = (order?.lines || []).filter(
            (line) => !line.combo_parent_id && hosnySentQty(line) > 0 && !line.refunded_orderline_id
        );
        if (!sentLines.length) {
            return true;
        }
        const approval = await this.hosnyApproveVoid(
            order,
            sentLines.map((line) => ({ line, after: 0 })),
            { kind: "order" }
        );
        return Boolean(approval);
    },
});
