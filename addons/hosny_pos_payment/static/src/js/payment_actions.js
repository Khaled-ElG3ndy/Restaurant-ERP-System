/** @odoo-module **/

/**
 * أزرار شاشة الدفع بتقسيمة FERP (2026-10-07): النادل، الموظف (وجبة موظف)،
 * العملاء، الخصم، خصم 100%.
 *
 *   • النادل: اختيار موظف يُحفظ اسمه على الفاتورة (hosny_waiter_*).
 *   • الموظف: وجبة موظف — يُحفظ على الفاتورة (hosny_staff_meal_*) ويصير
 *     الموظف عميلها (جهة اتصاله)، فتُسجَّل عليه بـ«أجل» إن أردت.
 *   • الخصم: نسبة على كل الأصناف (خصم السطر في أودو)، لا على رسوم الخدمة
 *     والتوصيل. أكثر من 5% — وخصم 100% دائماً — يحتاج سبباً واعتماد مسؤول
 *     بكلمة سر الاعتماد؛ الفحص والتسجيل في سجل المراجعة على الخادم
 *     (pos.audit.log.hosny_approve_discount في hosny_pos_controls).
 */
import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { patch } from "@web/core/utils/patch";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

const FEE_CODES = new Set(["HOSNY_FEE_SERVICE", "HOSNY_FEE_DELIVERY", "HOSNY_FEE_DRIVER"]);
const APPROVAL_ABOVE = 5;
const QUICK_DISCOUNTS = [5, 10, 15, 20, 25, 50];
const FULL_DISCOUNT_REASONS = [
    "ضيافة من الإدارة",
    "تعويض عميل عن مشكلة",
    "خطأ في الطلب",
    "تذوق صنف جديد",
    "وجبة للإدارة",
];
const DISCOUNT_REASONS = [
    "عميل دائم",
    "تعويض عن تأخير",
    "تعويض عن مشكلة في الجودة",
    "عرض ترويجي",
    "خطأ في الطلب",
];

const fold = (text) =>
    String(text || "")
        .toLowerCase()
        .replace(/[أإآ]/g, "ا")
        .replace(/ة/g, "ه")
        .replace(/ى/g, "ي")
        .trim();

/** اختيار موظف (النادل / وجبة موظف). */
export class HpStaffPicker extends Component {
    static template = "hosny_pos_payment.StaffPicker";
    static components = { Dialog };
    static props = {
        title: String,
        subtitle: { type: String, optional: true },
        clearLabel: String,
        employees: Array,
        selectedId: { optional: true },
        getPayload: Function,
        close: Function,
    };
    setup() {
        this.state = useState({ search: "" });
    }
    get list() {
        const q = fold(this.state.search);
        return q ? this.props.employees.filter((e) => fold(`${e.name} ${e.job}`).includes(q)) : this.props.employees;
    }
    pick(employee) {
        this.props.getPayload({ employee });
        this.props.close();
    }
    clear() {
        this.props.getPayload({ employee: null });
        this.props.close();
    }
}

/** نسبة الخصم: اختيارات سريعة أو أي رقم. */
export class HpDiscountPopup extends Component {
    static template = "hosny_pos_payment.DiscountPopup";
    static components = { Dialog };
    static props = { current: Number, getPayload: Function, close: Function };
    setup() {
        this.quick = QUICK_DISCOUNTS;
        this.state = useState({ value: this.props.current ? String(this.props.current) : "" });
    }
    get pc() {
        const value = parseFloat(String(this.state.value).replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d)));
        return Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : 0;
    }
    get needsApproval() {
        return this.pc > APPROVAL_ABOVE;
    }
    onInput(ev) {
        this.state.value = ev.target.value.replace(/[^\d٠-٩.]/g, "").slice(0, 5);
        ev.target.value = this.state.value;
    }
    set(n) {
        this.state.value = String(n);
    }
    confirm() {
        this.props.getPayload({ pc: this.pc });
        this.props.close();
    }
    remove() {
        this.props.getPayload({ pc: 0 });
        this.props.close();
    }
}

/**
 * اعتماد الخصم: سبب (اختيارات سريعة أو كتابة) + اختيار المسؤول + كلمة سر
 * الاعتماد. كلمة السر لا تُفحص هنا — يفحصها الخادم ويكتب سجل المراجعة.
 */
export class HpDiscountApproval extends Component {
    static template = "hosny_pos_payment.DiscountApproval";
    static components = { Dialog };
    static props = {
        pc: Number,
        before: String,
        discount: String,
        after: String,
        details: Object,
        getPayload: Function,
        close: Function,
    };
    setup() {
        this.reasons = this.props.pc >= 100 ? FULL_DISCOUNT_REASONS : DISCOUNT_REASONS;
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
    get title() {
        return this.props.pc >= 100 ? "اعتماد خصم \u2066100%\u2069" : `اعتماد خصم \u2066${this.props.pc}%\u2069`;
    }
    async loadApprovers() {
        try {
            const approvers = await this.pos.data.call("pos.audit.log", "hosny_void_approvers", [this.pos.config.id]);
            this.state.approvers = approvers || [];
            if (this.state.approvers.length === 1) {
                this.state.approverId = this.state.approvers[0].id;
            }
        } catch {
            this.state.error = "تعذّر الاتصال بالخادم — لا يمكن اعتماد الخصم بدون اتصال.";
        } finally {
            this.state.loading = false;
        }
    }
    pickReason(reason) {
        this.state.reason = reason;
        this.state.error = "";
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
            this.state.error = "اختر سبب الخصم أو اكتبه.";
            this.reasonRef.el?.focus();
            return;
        }
        if (!this.state.approverId) {
            this.state.error = "اختر المسؤول الذي يعتمد الخصم.";
            return;
        }
        if (!this.state.password) {
            this.state.error = "اكتب كلمة سر الاعتماد.";
            this.passwordRef.el?.focus();
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        let result;
        try {
            result = await this.pos.data.call("pos.audit.log", "hosny_approve_discount", [
                this.state.approverId,
                this.state.password,
                { ...this.props.details, reason: this.state.reason.trim() },
            ]);
        } catch {
            result = { ok: false, error: "تعذّر الاتصال بالخادم — لا يمكن اعتماد الخصم بدون اتصال." };
        }
        this.state.busy = false;
        if (!result?.ok) {
            this.state.error = result?.error || "لم يُعتمد الخصم.";
            this.state.password = "";
            this.passwordRef.el?.focus();
            return;
        }
        this.props.getPayload({ approver: result.approver, reason: this.state.reason.trim() });
        this.props.close();
    }
}

patch(PaymentScreen.prototype, {
    // ── النادل والموظف ──────────────────────────────────────────────────
    async hpStaffList() {
        if (!this._hpStaff) {
            try {
                this._hpStaff = await this.pos.data.call("pos.order", "hosny_staff_list", [this.pos.config.id]);
            } catch {
                this.notification.add("تعذّر جلب قائمة الموظفين — تأكد من الاتصال.", { type: "warning" });
                return null;
            }
        }
        if (!this._hpStaff.length) {
            this.notification.add("لا يوجد موظفون مسجلون في الموارد البشرية.", { type: "warning" });
            return null;
        }
        return this._hpStaff;
    },
    async hpPickWaiter() {
        const employees = await this.hpStaffList();
        if (!employees) {
            return;
        }
        const order = this.currentOrder;
        const result = await makeAwaitable(this.dialog, HpStaffPicker, {
            title: "النادل",
            subtitle: "اختر النادل الذي خدم هذه الفاتورة",
            clearLabel: "بدون نادل",
            employees,
            selectedId: order.hosny_waiter_id || null,
        });
        if (!result) {
            return;
        }
        order.hosny_waiter_id = result.employee?.id || 0;
        order.hosny_waiter_name = result.employee?.name || "";
    },
    async hpPickStaffMeal() {
        const employees = await this.hpStaffList();
        if (!employees) {
            return;
        }
        const order = this.currentOrder;
        const result = await makeAwaitable(this.dialog, HpStaffPicker, {
            title: "وجبة موظف",
            subtitle: "الفاتورة تُسجَّل باسم الموظف — ويمكن تسجيلها عليه بـ«أجل»",
            clearLabel: "ليست وجبة موظف",
            employees,
            selectedId: order.hosny_staff_meal_id || null,
        });
        if (!result) {
            return;
        }
        const employee = result.employee;
        order.hosny_staff_meal_id = employee?.id || 0;
        order.hosny_staff_meal_name = employee?.name || "";
        if (employee?.partner_id) {
            const Partner = this.pos.models["res.partner"];
            let partner = Partner.get(employee.partner_id);
            if (!partner) {
                try {
                    await this.pos.data.callRelated("res.partner", "get_new_partner", [
                        this.pos.config.id,
                        [["id", "=", employee.partner_id]],
                        0,
                    ]);
                    partner = Partner.get(employee.partner_id);
                } catch {
                    partner = null;
                }
            }
            if (partner) {
                order.setPartner(partner);
            }
        }
    },

    // ── الخصم ───────────────────────────────────────────────────────────
    get hpDiscountLines() {
        return this.currentOrder.lines.filter(
            (line) => !FEE_CODES.has(line.product_id?.default_code) && !line.isTipLine?.() && line.qty > 0
        );
    },
    /** نسبة الخصم الحالية لو كانت واحدة على كل الأصناف، وإلا أعلاها. */
    get hpDiscountPc() {
        return Math.max(0, ...this.hpDiscountLines.map((line) => line.getDiscount?.() || line.discount || 0));
    },
    async hpDiscount() {
        if (!this.hpDiscountLines.length) {
            return;
        }
        const result = await makeAwaitable(this.dialog, HpDiscountPopup, { current: this.hpDiscountPc });
        if (result) {
            await this.hpApplyDiscount(result.pc);
        }
    },
    async hpFullDiscount() {
        if (this.hpDiscountLines.length) {
            await this.hpApplyDiscount(100);
        }
    },
    /** المبالغ قبل الخصم وبعده لنافذة الاعتماد (الرسوم لا يشملها الخصم). */
    hpDiscountAmounts(pc) {
        const order = this.currentOrder;
        const lines = this.hpDiscountLines;
        const base = lines.reduce((sum, line) => sum + (line.prices?.no_discount_total_included ?? line.displayPrice ?? 0), 0);
        const now = lines.reduce((sum, line) => sum + (line.prices?.total_included ?? line.displayPrice ?? 0), 0);
        const discount = (base * pc) / 100;
        const total = order.priceIncl ?? order.getTotalWithTax?.() ?? now;
        return { before: total - now + base, discount, after: total - now + base - discount };
    },
    async hpApproveDiscount(pc) {
        const order = this.currentOrder;
        const amounts = this.hpDiscountAmounts(pc);
        const fmt = (n) => this.env.utils.formatCurrency(n);
        const table = order.table_id
            ? [order.table_id.floor_id?.name, order.table_id.table_number].filter(Boolean).join(" ")
            : "";
        return await makeAwaitable(this.dialog, HpDiscountApproval, {
            pc,
            before: fmt(amounts.before),
            discount: fmt(amounts.discount),
            after: fmt(amounts.after),
            details: {
                percent: pc,
                amount: amounts.discount,
                config_id: this.pos.config.id,
                session_id: this.pos.session?.id,
                order_id: typeof order.id === "number" ? order.id : false,
                order_uuid: order.uuid,
                order_ref: order.pos_reference || order.name || "",
                table,
                cashier: this.pos.getCashier?.()?.name || this.pos.user?.name || "",
            },
        });
    },
    async hpApplyDiscount(pc) {
        pc = Math.min(100, Math.max(0, Number(pc) || 0));
        let approval = null;
        if (pc > APPROVAL_ABOVE) {
            approval = await this.hpApproveDiscount(pc);
            if (!approval) {
                return;
            }
        }
        for (const line of this.hpDiscountLines) {
            line.setDiscount(pc);
        }
        const done = approval ? ` — اعتمده ${approval.approver}` : "";
        this.notification.add(pc ? `تم تطبيق خصم \u2066${pc}%\u2069${done}` : "تم إلغاء الخصم", { type: pc ? "success" : "info" });
    },
});
