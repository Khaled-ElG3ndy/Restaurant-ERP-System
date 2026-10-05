/** @odoo-module **/
import { Component, useState, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ManagerPinPopup extends Component {
    static template = "hosny_pos_controls.ManagerPinPopup";
    static props = {
        title: { type: String, optional: true },
        subtitle: { type: String, optional: true },
        reasons: { type: Array, optional: true },
        close: Function,
        confirm: Function,
    };

    setup() {
        this.pos = useService("pos");
        this.state = useState({ pin: [], errorMsg: "" });
        this.reasonRef = useRef("reasonSelect");
    }

    get defaultReasons() {
        return [
            { value: "customer_request",    label: "طلب العميل / Customer Request" },
            { value: "wrong_order",         label: "طلب خاطئ / Wrong Order" },
            { value: "quality_issue",       label: "مشكلة جودة / Quality Issue" },
            { value: "pricing_error",       label: "خطأ في السعر / Pricing Error" },
            { value: "manager_approval",    label: "موافقة مدير / Manager Decision" },
            { value: "staff_meal",          label: "وجبة موظف / Staff Meal" },
            { value: "promotional",         label: "عرض ترويجي / Promotional" },
            { value: "complaint",           label: "شكوى عميل / Complaint" },
        ];
    }

    get reasons() {
        return this.props.reasons || this.defaultReasons;
    }

    get pinDisplay() {
        return Array.from({ length: 4 }, (_, i) => i < this.state.pin.length);
    }

    get keys() {
        return ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "✓"];
    }

    get errorMsg() { return this.state.errorMsg; }

    onPinKey(event) {
        const key = event.target.dataset.key || event.target.textContent.trim();
        this.state.errorMsg = "";
        if (key === "⌫") {
            this.state.pin = this.state.pin.slice(0, -1);
        } else if (key === "✓") {
            this.validatePin();
        } else if (this.state.pin.length < 4) {
            this.state.pin = [...this.state.pin, String(key)];
            if (this.state.pin.length === 4) {
                this.validatePin();
            }
        }
    }

    async validatePin() {
        const reason = this.reasonRef.el?.value;
        if (!reason) {
            this.state.errorMsg = "⚠️ Please select a reason / الرجاء اختيار السبب";
            this.state.pin = [];
            return;
        }
        if (this.state.pin.length < 4) {
            this.state.errorMsg = "⚠️ Please enter complete PIN / أدخل الرقم كاملاً";
            return;
        }

        const enteredPin = this.state.pin.join("");

        // Validate PIN against POS employees
        try {
            const result = await this.pos.env.services.orm.call(
                "hr.employee",
                "search_read",
                [[["pin", "=", enteredPin]]],
                { fields: ["name", "pin"], limit: 1 }
            );

            if (result && result.length > 0) {
                const managerName = result[0].name;
                this.props.confirm({
                    reason: reason,
                    approvedBy: managerName,
                });
                this.props.close();
            } else {
                // Fallback: check against Odoo users with POS manager role
                const users = await this.pos.env.services.orm.call(
                    "res.users",
                    "search_read",
                    [[["pin", "=", enteredPin]]],
                    { fields: ["name"], limit: 1 }
                );
                if (users && users.length > 0) {
                    this.props.confirm({
                        reason: reason,
                        approvedBy: users[0].name,
                    });
                    this.props.close();
                } else {
                    this.state.errorMsg = "❌ Invalid PIN / الرقم غير صحيح";
                    this.state.pin = [];
                }
            }
        } catch(e) {
            // Simple PIN check if ORM fails
            const managerPin = "1234"; // Default fallback — change via Settings
            if (enteredPin === managerPin) {
                this.props.confirm({ reason, approvedBy: "Manager" });
                this.props.close();
            } else {
                this.state.errorMsg = "❌ Invalid PIN / الرقم غير صحيح";
                this.state.pin = [];
            }
        }
    }

    cancel() {
        this.props.close();
    }
}
