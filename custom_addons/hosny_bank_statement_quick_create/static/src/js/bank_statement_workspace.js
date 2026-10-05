/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { Many2XAutocomplete } from "@web/views/fields/relational_utils";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Component, onWillStart, useState } from "@odoo/owl";


export class BankStatementWorkspace extends Component {
    static template = "hosny_bank_statement_quick_create.BankStatementWorkspace";
    static props = { ...standardActionServiceProps };
    static components = { ControlPanel, Many2XAutocomplete };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.journalId = this.props.action.params?.journal_id || this.props.action.context?.default_journal_id;
        this.relationActions = { create: false, createEdit: false, write: false };
        const isArabic = (user.lang || user.context?.lang || "").toLowerCase().startsWith("ar");
        this.labels = isArabic ? {
            account: "الحساب",
            accountError: "خطأ محاسبي",
            accountStatus: "الحساب / الحالة",
            addClose: "إضافة وإغلاق",
            addNew: "إضافة وجديد",
            amount: "المبلغ",
            assignedPending: "مُعيّن - قيد الانتظار",
            credit: "الدائن",
            currentBalance: "الرصيد الحالي",
            date: "التاريخ",
            debit: "المدين",
            details: "التفاصيل",
            discard: "تجاهل",
            label: "البيان",
            loading: "جارٍ التحميل...",
            new: "جديد",
            noTransactions: "لا توجد حركات بنكية حتى الآن.",
            openJournalEntry: "فتح القيد اليومي",
            partner: "الشريك",
            pending: "قيد الانتظار",
            processed: "تمت المعالجة",
            reconciled: "تمت التسوية",
            reconciledProcessed: "تمت التسوية / المعالجة",
            setAccount: "تعيين الحساب",
            setPartner: "تعيين الشريك",
            writeLabel: "اكتب بيانًا...",
        } : {
            account: "Account", accountError: "Accounting Error", accountStatus: "Account / Status",
            addClose: "Add & Close", addNew: "Add & New", amount: "Amount",
            assignedPending: "Assigned - Pending", credit: "Credit", currentBalance: "Current Balance",
            date: "Date", debit: "Debit", details: "Details", discard: "Discard", label: "Label",
            loading: "Loading...", new: "New", noTransactions: "No bank transactions yet.",
            openJournalEntry: "Open Journal Entry", partner: "Partner", pending: "Pending",
            processed: "Processed", reconciled: "Reconciled", reconciledProcessed: "Reconciled / Processed",
            setAccount: "Set Account", setPartner: "Set Partner", writeLabel: "Write a label...",
        };
        this.state = useState({
            loading: true,
            saving: false,
            entryOpen: this.props.action.params?.open_entry !== false,
            journal: {},
            currentBalance: 0,
            lines: [],
            date: "",
            label: "",
            partnerId: false,
            partnerName: "",
            accountId: false,
            accountName: "",
            amount: "",
        });
        onWillStart(() => this.loadData(true));
    }

    async loadData(initializeEntry = false) {
        const data = await this.orm.call(
            "account.journal",
            "get_quick_statement_workspace_data",
            [[this.journalId]]
        );
        this.state.journal = data.journal;
        this.state.currentBalance = data.current_balance;
        this.state.lines = data.lines.map((line) => ({
            ...line,
            expanded: false,
            editPartner: false,
            editAccount: false,
            editPartnerId: line.partner_id,
            editPartnerName: line.partner_name,
            editAccountId: line.account_id,
            editAccountName: line.account_name,
        }));
        if (initializeEntry || !this.state.date) {
            this.state.date = data.today;
        }
        this.state.loading = false;
    }

    get relationContext() {
        return {
            allowed_company_ids: [this.state.journal.company_id],
            default_company_id: this.state.journal.company_id,
        };
    }

    getPartnerDomain() {
        return [
            "|",
            ["company_id", "=", false],
            ["company_id", "=", this.state.journal.company_id],
        ];
    }

    getAccountDomain() {
        const excludedIds = [
            this.state.journal.default_account_id,
            this.state.journal.suspense_account_id,
        ].filter(Boolean);
        return [
            ["company_ids", "parent_of", this.state.journal.company_id],
            ["id", "not in", excludedIds],
        ];
    }

    updateEntryPartner(records) {
        const record = records?.[0];
        this.state.partnerId = record?.id || false;
        this.state.partnerName = record?.display_name || "";
    }

    updateEntryAccount(records) {
        const record = records?.[0];
        this.state.accountId = record?.id || false;
        this.state.accountName = record?.display_name || "";
    }

    onAmountInput(event) {
        this.state.amount = event.target.value;
    }

    newEntry() {
        this.resetEntry();
        this.state.entryOpen = true;
    }

    resetEntry() {
        this.state.label = "";
        this.state.partnerId = false;
        this.state.partnerName = "";
        this.state.accountId = false;
        this.state.accountName = "";
        this.state.amount = "";
    }

    discardEntry() {
        this.resetEntry();
        this.state.entryOpen = false;
    }

    async saveEntry(addAnother) {
        const amount = Number(this.state.amount);
        if (!this.state.date || !this.state.label.trim() || !Number.isFinite(amount) || amount === 0) {
            this.notification.add(
                _t("Date, label, and a non-zero amount are required."),
                { type: "warning" }
            );
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call(
                "account.bank.statement.line",
                "quick_create_transaction",
                [{
                    journal_id: this.journalId,
                    date: this.state.date,
                    label: this.state.label,
                    partner_id: this.state.partnerId || false,
                    account_id: this.state.accountId || false,
                    amount,
                    token: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
                }]
            );
            this.resetEntry();
            this.state.entryOpen = addAnother;
            await this.loadData(false);
        } finally {
            this.state.saving = false;
        }
    }

    toggleDetails(line) {
        line.expanded = !line.expanded;
    }

    startPartnerEdit(line) {
        line.editPartner = true;
        line.editPartnerId = line.partner_id;
        line.editPartnerName = line.partner_name;
    }

    updateLinePartner(line, records) {
        const record = records?.[0];
        line.editPartnerId = record?.id || false;
        line.editPartnerName = record?.display_name || "";
    }

    async saveLinePartner(line) {
        await this.orm.call(
            "account.bank.statement.line",
            "quick_set_partner",
            [[line.id], line.editPartnerId || false]
        );
        await this.loadData(false);
    }

    startAccountEdit(line) {
        line.editAccount = true;
        line.editAccountId = line.account_id;
        line.editAccountName = line.account_name;
    }

    updateLineAccount(line, records) {
        const record = records?.[0];
        line.editAccountId = record?.id || false;
        line.editAccountName = record?.display_name || "";
    }

    async saveLineAccount(line) {
        if (!line.editAccountId) {
            this.notification.add(_t("Select an account first."), { type: "warning" });
            return;
        }
        await this.orm.call(
            "account.bank.statement.line",
            "quick_set_account",
            [[line.id], line.editAccountId]
        );
        await this.loadData(false);
    }

    openJournalEntry(line) {
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            name: _t("Journal Entry"),
            res_model: "account.move",
            res_id: line.move_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    formatAmount(amount, currencyId = false) {
        return formatMonetary(amount, {
            currencyId: currencyId || this.state.journal.currency_id,
        });
    }
}

registry.category("actions").add(
    "hosny_bank_statement_quick_create.workspace",
    BankStatementWorkspace
);
