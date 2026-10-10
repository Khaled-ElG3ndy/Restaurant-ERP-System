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
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";

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

const fmtQty = (n) => (Number.isInteger(n) ? String(n) : String(parseFloat(n.toFixed(3))));
const roundQty = (n) => Math.round(n * 1000) / 1000;

export class HosnyVoidApprovalDialog extends Component {
    static template = "hosny_pos_controls.VoidApprovalDialog";
    static components = { Dialog };
    static props = {
        title: String,
        summary: Array,
        details: Object,
        // صنف واحد من سلة المهملات: يختار الكاشير كم يُلغى (الكل أو جزء).
        // { max, step, describe(qty) → { summary, details } }
        adjust: { type: Object, optional: true },
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
            qtyText: this.props.adjust ? fmtQty(this.props.adjust.max) : "",
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

    /* ── الكمية الملغاة (صنف واحد) ── */
    get cancelQty() {
        const value = parseFloat(String(this.state.qtyText).replace(",", "."));
        return Number.isFinite(value) ? roundQty(value) : 0;
    }

    get qtyValid() {
        const adjust = this.props.adjust;
        return !adjust || (this.cancelQty > 0 && this.cancelQty <= adjust.max);
    }

    get isAll() {
        return this.props.adjust && this.cancelQty === this.props.adjust.max;
    }

    get view() {
        // بعد الاعتماد يُحذف السطر قبل أن تُغلق النافذة: آخر رسم يقرأ النسخة المحفوظة
        if (this.frozenView) {
            return this.frozenView;
        }
        if (!this.props.adjust) {
            return { summary: this.props.summary, details: this.props.details };
        }
        return this.props.adjust.describe(this.qtyValid ? this.cancelQty : this.props.adjust.max);
    }

    get maxText() {
        return fmtQty(this.props.adjust.max);
    }

    stepQty(direction) {
        const { max, step } = this.props.adjust;
        const current = this.qtyValid ? this.cancelQty : max;
        const next = roundQty(Math.min(max, Math.max(Math.min(step, max), current + direction * step)));
        this.state.qtyText = fmtQty(next);
        this.state.error = "";
    }

    setAll() {
        this.state.qtyText = this.maxText;
        this.state.error = "";
    }

    get canSubmit() {
        return (
            !this.state.busy &&
            !this.state.loading &&
            this.qtyValid &&
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

    payloadExtras() {
        return { quantity: this.props.adjust ? this.cancelQty : null };
    }

    async submit() {
        if (!this.qtyValid) {
            this.state.error = _t("اكتب كمية الإلغاء: أكبر من صفر ولا تزيد عن %s.", this.maxText);
            return;
        }
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
                { ...this.view.details, reason: this.state.reason.trim() },
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
        this.frozenView = this.view;
        this.props.getPayload({
            approver: result.approver,
            reason: this.state.reason.trim(),
            ...this.payloadExtras(),
        });
        this.props.close();
    }
}

/**
 * «إلغاء أصناف الطلب» من قائمة ☰ (طلب 2026-10-10): كل أصناف الطلب في نافذة
 * واحدة، كلها محددة بكمياتها كاملة. الكاشير يلغي تحديد ما يبقى أو يقلل كمية،
 * ثم سبب واحد واعتماد واحد. ما لم يصل المطبخ لا يحتاج اعتماداً.
 */
export class HosnyOrderVoidDialog extends HosnyVoidApprovalDialog {
    static template = "hosny_pos_controls.OrderVoidDialog";
    static props = {
        title: String,
        // [{ uuid, product, max, step, sent }]
        items: Array,
        // selection [{ uuid, qty }] → { summary, details, count, amount, all }
        describe: Function,
        getPayload: Function,
        close: Function,
    };

    setup() {
        super.setup();
        this.picks = useState(
            Object.fromEntries(this.props.items.map((item) => [item.uuid, { on: true, qtyText: fmtQty(item.max) }]))
        );
    }

    pickQty(item) {
        const value = parseFloat(String(this.picks[item.uuid].qtyText).replace(",", "."));
        return Number.isFinite(value) ? roundQty(value) : 0;
    }

    itemValid(item) {
        const qty = this.pickQty(item);
        return !this.picks[item.uuid].on || (qty > 0 && qty <= item.max);
    }

    get selection() {
        return this.props.items
            .filter((item) => this.picks[item.uuid].on && this.itemValid(item))
            .map((item) => ({ uuid: item.uuid, qty: this.pickQty(item) }));
    }

    get qtyValid() {
        return this.selection.length > 0 && this.props.items.every((item) => this.itemValid(item));
    }

    get allPicked() {
        return this.props.items.every((item) => this.picks[item.uuid].on);
    }

    get view() {
        return this.frozenView || this.props.describe(this.selection);
    }

    /** ما وصل المطبخ يحتاج سبباً واعتماداً؛ غير المرسل يُحذف مباشرة. */
    get needsApproval() {
        return this.view.details.lines.length > 0;
    }

    get canSubmit() {
        if (!this.needsApproval) {
            return !this.state.busy && this.qtyValid;
        }
        return super.canSubmit;
    }

    toggle(item) {
        this.picks[item.uuid].on = !this.picks[item.uuid].on;
        this.state.error = "";
    }

    toggleAll() {
        const on = !this.allPicked;
        for (const item of this.props.items) {
            this.picks[item.uuid].on = on;
            if (on) {
                this.picks[item.uuid].qtyText = fmtQty(item.max);
            }
        }
        this.state.error = "";
    }

    stepItem(item, direction) {
        const current = this.itemValid(item) && this.pickQty(item) > 0 ? this.pickQty(item) : item.max;
        const next = roundQty(Math.min(item.max, Math.max(Math.min(item.step, item.max), current + direction * item.step)));
        this.picks[item.uuid].qtyText = fmtQty(next);
        this.picks[item.uuid].on = true;
        this.state.error = "";
    }

    payloadExtras() {
        return { selection: this.selection };
    }

    async submit() {
        if (!this.qtyValid) {
            this.state.error = _t("اختر صنفاً واحداً على الأقل، وكل كمية أكبر من صفر ولا تزيد عن الموجود.");
            return;
        }
        if (!this.needsApproval) {
            this.frozenView = this.view;
            this.props.getPayload({ approver: null, reason: "", selection: this.selection });
            this.props.close();
            return;
        }
        return super.submit();
    }
}

patch(PosStore.prototype, {
    /** صفوف النافذة وتفاصيل السجل لكمية جديدة لكل سطر. lines: [{ line, after }]. */
    _hosnyVoidData(order, lines, kind) {
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
        const summary = rows.map((row) => ({
            product: row.product,
            text:
                row.quantity_after > 0
                    ? `${_t("إلغاء")} ${fmtQty(row.cancelled)} ${_t("من")} ${fmtQty(row.quantity_before)}`
                    : `${_t("إلغاء الكمية المرسلة كلها")} (${fmtQty(row.quantity_before)})`,
            amount: this.env.utils.formatCurrency(row.amount),
        }));
        return { rows, details, summary };
    },

    /**
     * يفتح نافذة الاعتماد. lines: [{ line, after }] — after الكمية الجديدة (0 = حذف).
     * adjustable (صنف واحد): الكاشير يختار في النافذة كم يُلغى، الكل أو جزء.
     * يرجع { approver, reason, quantity } أو null لو تراجع الكاشير؛
     * quantity = الكمية المختارة للإلغاء (null بدون adjustable).
     */
    async hosnyApproveVoid(order, lines, { kind = "line", adjustable = false } = {}) {
        const data = this._hosnyVoidData(order, lines, kind);
        if (!data.rows.length) {
            return { approver: null, reason: "", quantity: null };
        }
        let adjust;
        if (adjustable && lines.length === 1) {
            const { line } = lines[0];
            const max = roundQty(Math.abs(line.getQuantity()));
            const product = data.rows[0].product;
            adjust = {
                max,
                // السمك بالجرام (سعر الوحدة أقل من ريال): الخطوة 50 جم
                step: max >= 50 && lineUnitPrice(line) < 1 ? 50 : 1,
                describe: (qty) => {
                    const view = this._hosnyVoidData(order, [{ line, after: roundQty(max - qty) }], kind);
                    if (!view.rows.length) {
                        // الجزء المختار لم يصل المطبخ بعد
                        view.summary = [
                            { product, text: `${_t("إلغاء")} ${fmtQty(qty)} (${_t("لم يُرسل للمطبخ")})`, amount: "" },
                        ];
                    }
                    return view;
                },
            };
        }
        const result = await makeAwaitable(this.dialog, HosnyVoidApprovalDialog, {
            title: kind === "order" ? _t("حذف طلب مُرسل للمطبخ") : _t("إلغاء صنف مُرسل للمطبخ"),
            summary: data.summary,
            details: data.details,
            adjust,
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

    /* ── سلة المهملات: إلغاء الصنف كله أو جزء منه ── */
    async hosnyGuardedRemoveLine(line) {
        const order = line?.order_id;
        if (!order) {
            return false;
        }
        if (hosnySentQty(line) > 0 && !line.refunded_orderline_id) {
            const approval = await this.hosnyApproveVoid(order, [{ line, after: 0 }], { adjustable: true });
            if (!approval || !order.lines.includes(line)) {
                return false;
            }
            const left = roundQty(Math.abs(line.getQuantity()) - (approval.quantity ?? Infinity));
            if (left > 0) {
                line.setQuantity(left, Boolean(line.combo_line_ids?.length));
                return true;
            }
        }
        order.removeOrderline(line);
        return true;
    },

    /* ── إلغاء أصناف الطلب (قائمة ☰): الكل أو بعضه أو جزء من كمية ── */
    hosnyOrderVoidLines(order) {
        return (order?.lines || []).filter(
            (line) =>
                !line.combo_parent_id &&
                !line.is_meal_component &&
                !line.is_additional_final_product &&
                !line.refunded_orderline_id &&
                line.getQuantity() > 0
        );
    },

    async hosnyCancelOrderItems() {
        const order = this.getOrder();
        if (!order || order.finalized) {
            return;
        }
        const lines = this.hosnyOrderVoidLines(order);
        if (!lines.length) {
            this.notification.add(_t("لا توجد أصناف في الطلب."), { type: "warning" });
            return;
        }
        const items = lines.map((line) => {
            const max = roundQty(line.getQuantity());
            return {
                uuid: line.uuid,
                line,
                product: line.getFullProductName?.() || line.full_product_name || line.product_id?.display_name || "",
                max,
                step: max >= 50 && lineUnitPrice(line) < 1 ? 50 : 1,
                sent: hosnySentQty(line),
            };
        });
        const byUuid = Object.fromEntries(items.map((item) => [item.uuid, item]));
        const isAll = (selection) =>
            selection.length === items.length && selection.every((pick) => pick.qty >= byUuid[pick.uuid].max);
        const describe = (selection) => {
            const all = isAll(selection);
            const chosen = selection.map((pick) => ({
                line: byUuid[pick.uuid].line,
                after: roundQty(byUuid[pick.uuid].max - pick.qty),
            }));
            const data = this._hosnyVoidData(order, chosen, all ? "order" : "line");
            const amount = selection.reduce((total, pick) => total + pick.qty * lineUnitPrice(byUuid[pick.uuid].line), 0);
            return { ...data, all, count: selection.length, amount: this.env.utils.formatCurrency(amount) };
        };
        const result = await makeAwaitable(this.dialog, HosnyOrderVoidDialog, {
            title: _t("إلغاء أصناف الطلب"),
            items: items.map(({ line, ...item }) => item),
            describe,
        });
        if (!result || order.finalized) {
            return;
        }
        if (isAll(result.selection)) {
            // الطلب كله: مسار أودو للحذف — يرسل «إلغاء» للمطبخ ويلغي الطلب على الخادم
            const deleted = await this.deleteOrders([order]);
            if (deleted) {
                order.uiState.displayed = false;
                await this.afterOrderDeletion();
                this.showDefault?.();
                this.notification.add(
                    result.approver
                        ? _t("أُلغي الطلب كله باعتماد %s، ووصل الإلغاء للمطبخ.", result.approver)
                        : _t("أُلغي الطلب كله."),
                    { type: "success" }
                );
            }
            return;
        }
        for (const pick of result.selection) {
            const { line, max } = byUuid[pick.uuid];
            if (!order.lines.includes(line)) {
                continue;
            }
            const left = roundQty(max - pick.qty);
            if (left > 0) {
                line.setQuantity(left, Boolean(line.combo_line_ids?.length));
            } else {
                order.removeOrderline(line);
            }
        }
        this.notification.add(
            result.approver
                ? _t("اعتمد الإلغاء: %s. اضغط «إرسال الطلب» ليصل الإلغاء للمطبخ.", result.approver)
                : _t("حُذفت الأصناف المحددة."),
            { type: "success" }
        );
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

/** عنصر «إلغاء أصناف الطلب» في قائمة ☰: على شاشة الأصناف وطلب فيه أصناف. */
patch(Navbar.prototype, {
    get hosnyCanCancelOrder() {
        const order = this.pos.getOrder();
        return (
            this.pos.router.state.current === "ProductScreen" &&
            Boolean(order && !order.finalized && this.pos.hosnyOrderVoidLines(order).length)
        );
    },
});
