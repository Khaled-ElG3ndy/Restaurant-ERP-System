/** @odoo-module */

import { onWillStart, useState, Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { parseFloat } from "@web/views/fields/parsers";
import { Dialog } from "@web/core/dialog/dialog";

import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { Input } from "@point_of_sale/app/components/inputs/input/input";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { useAsyncLockedMethod } from "@point_of_sale/app/hooks/hooks";

import { MultiCashMoveReceipt } from "@pos_multi_payment_reconciliation/app/navbar/multi_cash_move_popup/multi_cash_move_receipt";

export class MultiCashMovePopup extends Component {
    static template = "pos_multi_payment_reconciliation.MultiCashMovePopup";
    static components = { Input, Dialog };
    static props = ["confirmKey?", "close", "getPayload?"];

    setup() {
        super.setup();
        this.pos = usePos();
        this.orm = useService("orm");
        this.popup = useService("popup");
        this.printer = useService("printer");
        this.notification = useService("pos_notification");
        this.state = useState({
            isLoading: true,
            lines: [],
            note: "",
        });
        this.confirm = useAsyncLockedMethod(this.confirm);

        onWillStart(async () => {
            await this.loadLines();
        });
    }

    async loadLines() {
        try {
            const response = await this.orm.call("pos.session", "get_multi_cash_in_out_data", [
                [this.pos.pos_session.id],
            ]);
            this.state.lines = (response.lines || []).map((line) => ({
                paymentMethodId: line.payment_method_id,
                name: line.name,
                type: line.type,
                expected: line.expected,
                counted: "",
                reason: "",
            }));
        } catch (error) {
            await this.popup.add(ErrorPopup, {
                title: _t("Cash in / out"),
                body: error.message || _t("Failed to load methods."),
            });
            this.props.close();
        } finally {
            this.state.isLoading = false;
        }
    }

    hasCountedValue(line) {
        return line.counted !== "";
    }

    hasValidCountedValue(line) {
        return this.hasCountedValue(line) && this.isCountedValueValid(line);
    }

    isCountedValueValid(line) {
        return !this.hasCountedValue(line) || this.env.utils.isValidFloat(line.counted);
    }

    parseCountedValue(line) {
        if (!this.hasCountedValue(line) || !this.isCountedValueValid(line)) {
            return NaN;
        }
        return parseFloat(line.counted);
    }

    getDifference(line) {
        const counted = this.parseCountedValue(line);
        if (Number.isNaN(counted)) {
            return NaN;
        }
        return counted - line.expected;
    }

    getDifferenceStatus(line) {
        if (!this.hasCountedValue(line)) {
            return _t("Pending");
        }
        if (!this.isCountedValueValid(line)) {
            return _t("Needs Review");
        }
        const difference = this.getDifference(line);
        if (this.env.utils.floatIsZero(difference)) {
            return _t("No Change");
        }
        return difference > 0 ? _t("Cash In") : _t("Cash Out");
    }

    getDifferenceClass(line) {
        if (!this.hasCountedValue(line)) {
            return { "text-muted": true };
        }
        if (!this.isCountedValueValid(line)) {
            return { "text-danger fw-bolder": true };
        }
        const difference = this.getDifference(line);
        return {
            "text-danger fw-bolder": !Number.isNaN(difference) && difference < 0,
            "text-success fw-bolder": !Number.isNaN(difference) && difference > 0,
            "text-dark fw-bolder":
                !Number.isNaN(difference) && this.env.utils.floatIsZero(difference),
        };
    }

    getDifferencePanelClass(line) {
        if (!this.hasCountedValue(line)) {
            return { "is-pending": true };
        }
        if (!this.isCountedValueValid(line)) {
            return { "is-invalid": true };
        }
        const difference = this.getDifference(line);
        return {
            "is-balanced": this.env.utils.floatIsZero(difference),
            "is-over": difference > 0,
            "is-short": difference < 0,
        };
    }

    getCardClass(line) {
        const difference = this.getDifference(line);
        return {
            "has-entry": this.hasCountedValue(line),
            "needs-review": this.hasCountedValue(line) && !this.isCountedValueValid(line),
            "has-difference":
                !Number.isNaN(difference) && !this.env.utils.floatIsZero(difference),
        };
    }

    getStatusBadgeClass(line) {
        return {
            "is-pending": !this.hasCountedValue(line),
            "is-invalid": this.hasCountedValue(line) && !this.isCountedValueValid(line),
            "is-balanced":
                this.hasValidCountedValue(line) &&
                this.env.utils.floatIsZero(this.getDifference(line)),
            "is-over": this.hasValidCountedValue(line) && this.getDifference(line) > 0,
            "is-short": this.hasValidCountedValue(line) && this.getDifference(line) < 0,
        };
    }

    getMethodTypeLabel(line) {
        if (line.type === "cash") {
            return _t("Cash");
        }
        return _t("Bank");
    }

    getCountLabel(line) {
        return _t("Counted Balance");
    }

    isFirstLine(line) {
        return this.state.lines[0]?.paymentMethodId === line.paymentMethodId;
    }

    matchLine(line) {
        line.counted = `${line.expected}`;
    }

    clearLine(line) {
        line.counted = "";
        line.reason = "";
    }

    canConfirm() {
        return (
            !this.state.isLoading &&
            this.state.lines.some((line) => this.hasCountedValue(line)) &&
            this.state.lines.every((line) => this.isCountedValueValid(line))
        );
    }

    getTotalExpected() {
        return this.state.lines.reduce((total, line) => total + line.expected, 0);
    }

    getEnteredExpectedTotal() {
        return this.state.lines
            .filter((line) => this.hasValidCountedValue(line))
            .reduce((total, line) => total + line.expected, 0);
    }

    getTotalCounted() {
        const enteredLines = this.state.lines.filter((line) => this.hasValidCountedValue(line));
        if (!enteredLines.length) {
            return NaN;
        }
        return enteredLines.reduce((total, line) => total + this.parseCountedValue(line), 0);
    }

    getTotalDifference() {
        const totalCounted = this.getTotalCounted();
        if (Number.isNaN(totalCounted)) {
            return NaN;
        }
        return totalCounted - this.getEnteredExpectedTotal();
    }

    formatTotalCounted() {
        const totalCounted = this.getTotalCounted();
        return Number.isNaN(totalCounted)
            ? _t("Awaiting input")
            : this.env.utils.formatCurrency(totalCounted);
    }

    formatTotalDifference() {
        const totalDifference = this.getTotalDifference();
        return Number.isNaN(totalDifference)
            ? _t("Pending")
            : this.env.utils.formatCurrency(totalDifference);
    }

    getTotalDifferenceClass() {
        const totalDifference = this.getTotalDifference();
        return {
            "text-muted": Number.isNaN(totalDifference),
            "text-danger fw-bolder": !Number.isNaN(totalDifference) && totalDifference < 0,
            "text-success fw-bolder": !Number.isNaN(totalDifference) && totalDifference > 0,
            "text-dark fw-bolder":
                !Number.isNaN(totalDifference) && this.env.utils.floatIsZero(totalDifference),
        };
    }

    get payloadLines() {
        const globalNote = this.state.note.trim();
        return this.state.lines
            .filter((line) => this.hasCountedValue(line))
            .map((line) => ({
                payment_method_id: line.paymentMethodId,
                counted: this.parseCountedValue(line),
                reason: (line.reason || globalNote).trim(),
            }));
    }

    async confirm() {
        if (!this.canConfirm()) {
            await this.popup.add(ErrorPopup, {
                title: _t("Cash in / out"),
                body: _t("Enter at least one valid amount before confirming."),
            });
            return;
        }

        const response = await this.orm.call("pos.session", "action_multi_cash_in_out", [
            [this.pos.pos_session.id],
            this.payloadLines,
        ]);

        if (response.created_count) {
            const receiptLines = response.processed_lines.map((line) => ({
                paymentMethodName: line.payment_method_name,
                currentBalance: this.env.utils.formatCurrency(line.expected),
                countedBalance: this.env.utils.formatCurrency(line.counted),
                difference: this.env.utils.formatCurrency(line.difference),
                reason: line.reason,
                entryCreated: line.entry_created,
            }));
            const logMessage = response.processed_lines
                .map(
                    (line) =>
                        `${line.payment_method_name}: ${_t("Current Balance")} ${this.env.utils.formatCurrency(
                            line.expected
                        )}, ${_t("Counted Balance")} ${this.env.utils.formatCurrency(
                            line.counted
                        )}, ${_t("Difference")} ${this.env.utils.formatCurrency(line.difference)}`
                )
                .join(" | ");
            await this.pos.logEmployeeMessage(
                `${_t("POS cash in / out")} - ${logMessage}`,
                "CASH_DRAWER_ACTION"
            );
            await this.printer.print(MultiCashMoveReceipt, {
                headerData: this.pos.getReceiptHeaderData(),
                date: new Date().toLocaleString(),
                lines: receiptLines,
            });
        }

        this.notification.add(response.message, 3000);
        this.props.close();
    }
}
