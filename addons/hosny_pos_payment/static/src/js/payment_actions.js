/** @odoo-module **/

/**
 * أزرار شاشة الدفع بتقسيمة FERP (2026-10-07): النادل، الموظف (وجبة موظف)،
 * العملاء، الخصم، خصم 100%.
 *
 *   • النادل: اختيار موظف يُحفظ اسمه على الفاتورة (hosny_waiter_*).
 *   • الموظف: وجبة موظف — يُحفظ على الفاتورة (hosny_staff_meal_*) ويصير
 *     الموظف عميلها (جهة اتصاله)، فتُسجَّل عليه بـ«أجل» إن أردت.
 *   • الخصم: نسبة على كل الأصناف (خصم السطر في أودو)، لا على رسوم الخدمة
 *     والتوصيل. أكثر من 5% — وخصم 100% دائماً — برقم سري المدير
 *     (requireManagerApproval في hosny_pos_controls) ويُسجَّل في سجل التدقيق.
 */
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { patch } from "@web/core/utils/patch";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

const FEE_CODES = new Set(["HOSNY_FEE_SERVICE", "HOSNY_FEE_DELIVERY", "HOSNY_FEE_DRIVER"]);
const APPROVAL_ABOVE = 5;
const QUICK_DISCOUNTS = [5, 10, 15, 20, 25, 50];

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
    async hpApplyDiscount(pc) {
        pc = Math.min(100, Math.max(0, Number(pc) || 0));
        if (pc > APPROVAL_ABOVE) {
            if (typeof this.pos.requireManagerApproval !== "function") {
                this.notification.add("موافقة المدير غير متاحة — لم يُطبَّق الخصم.", { type: "danger" });
                return;
            }
            const approval = await this.pos.requireManagerApproval(
                "discount",
                pc === 100 ? "خصم \u2066100%\u2069" : "تفويض الخصم",
                `خصم \u2066${pc}%\u2069 على الفاتورة — يلزم موافقة المدير`
            );
            if (!approval?.approved) {
                this.notification.add("لم يُطبَّق الخصم — لا توجد موافقة مدير.", { type: "warning" });
                return;
            }
            try {
                await this.pos.data.call("pos.audit.log", "log_action", [], {
                    action: "discount",
                    reason: approval.reason || "",
                    approved_by: approval.approvedBy || "",
                    cashier: this.pos.getCashier?.()?.name || "",
                    amount: pc,
                    session_id: this.pos.session?.id,
                });
            } catch {
                // سجل التدقيق لا يوقف الخصم
            }
        }
        for (const line of this.hpDiscountLines) {
            line.setDiscount(pc);
        }
        this.notification.add(pc ? `تم تطبيق خصم \u2066${pc}%\u2069` : "تم إلغاء الخصم", { type: pc ? "success" : "info" });
    },
});
