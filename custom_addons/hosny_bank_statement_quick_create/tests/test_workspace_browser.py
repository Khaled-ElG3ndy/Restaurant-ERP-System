import json

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged("post_install", "-at_install", "-standard", "hosny_workspace_browser")
class TestBankStatementWorkspaceBrowser(HttpCase):
    def test_arabic_workspace_renders_without_dialog(self):
        login = "hosny_workspace_browser"
        self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Hosny Workspace Browser",
            "login": login,
            "password": login,
            "lang": "ar_001",
            "company_id": self.env.company.id,
            "company_ids": [Command.set(self.env.company.ids)],
            "group_ids": [Command.set([self.env.ref("account.group_account_user").id])],
        })
        journal = self.env["account.journal"].browse(81)
        account = self.env["account.account"].search([
            ("company_ids", "parent_of", self.env.company.id),
            ("account_type", "in", ("expense", "income", "asset_current")),
            ("id", "not in", (journal.default_account_id.id, journal.suspense_account_id.id)),
        ], limit=1)
        browser_code = """
            (async () => {
            const accountCode = __ACCOUNT_CODE__;
            const label = "اختبار متصفح الحركة البنكية";
            const waitFor = async (selector, timeout = 15000) => {
                const started = Date.now();
                while (Date.now() - started < timeout) {
                    const element = document.querySelector(selector);
                    if (element) return element;
                    await new Promise((resolve) => setTimeout(resolve, 100));
                }
                throw new Error(`Missing browser element: ${selector}`);
            };
            const waitForAbsent = async (selector, timeout = 15000) => {
                const started = Date.now();
                while (Date.now() - started < timeout) {
                    if (!document.querySelector(selector)) return;
                    await new Promise((resolve) => setTimeout(resolve, 100));
                }
                throw new Error(`Browser element did not disappear: ${selector}`);
            };
            const waitForText = async (selector, value, timeout = 15000) => {
                const started = Date.now();
                while (Date.now() - started < timeout) {
                    const element = [...document.querySelectorAll(selector)]
                        .find((candidate) => candidate.innerText.includes(value));
                    if (element) return element;
                    await new Promise((resolve) => setTimeout(resolve, 100));
                }
                throw new Error(`Missing browser text: ${value}`);
            };
            const setInputValue = (input, value) => {
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
                setter.call(input, value);
                input.dispatchEvent(new Event("input", { bubbles: true }));
            };
            await waitFor(".o_account_kanban .o_kanban_record");
            const journalCard = [...document.querySelectorAll(".o_account_kanban .o_kanban_record")]
                .find((card) => card.innerText.includes("البنك الاهلي"));
            if (!journalCard) throw new Error("Al Ahli journal card is missing");
            const transactionsButton = journalCard.querySelector("#all_transactions_btn");
            if (!transactionsButton) throw new Error("Transactions button is missing");
            transactionsButton.click();
            await waitFor(".o_list_view");
            await waitForAbsent(".o_account_kanban");
            const listButton = await waitFor("button[name='action_quick_create_statement_line']");
            listButton.click();
            const workspace = await waitFor(".o_hosny_bank_workspace");
            const text = workspace.innerText;
            if (!text.includes("الرصيد الحالي")) throw new Error("Arabic current balance is missing");
            if (!text.includes("الحساب")) throw new Error("Arabic account field is missing");
            if (!text.includes("إضافة وجديد")) throw new Error("Arabic Add & New is missing");
            if (!text.includes("إضافة وإغلاق")) throw new Error("Arabic Add & Close is missing");
            if (!text.includes("الشريك")) throw new Error("Arabic partner field is missing");
            if (!text.includes("الحساب / الحالة")) throw new Error("Arabic account/status header is missing");
            for (const englishText of ["Current Balance", "Partner", "Account / Status", "Add & New", "Add & Close"]) {
                if (text.includes(englishText)) throw new Error(`English label remains: ${englishText}`);
            }
            if (document.querySelector(".modal.show")) throw new Error("Workspace opened in a dialog");
            if (!workspace.querySelector("input[type='date']")) throw new Error("Date input is missing");
            if (!workspace.querySelector("input[type='number']")) throw new Error("Amount input is missing");
            if (workspace.querySelectorAll(".o_input_dropdown input").length < 2) {
                throw new Error("Partner or account autocomplete is missing");
            }

            const labelInput = workspace.querySelector(".o_hosny_quick_entry input[type='text'].form-control");
            const amountInput = workspace.querySelector(".o_hosny_quick_entry input[type='number']");
            const accountInput = workspace.querySelectorAll(".o_hosny_quick_entry .o_input_dropdown input")[1];
            setInputValue(labelInput, label);
            setInputValue(amountInput, "321");
            accountInput.focus();
            setInputValue(accountInput, accountCode);
            const accountOption = await waitForText(".o-autocomplete--dropdown-item", accountCode);
            accountOption.click();
            const addNewButton = [...workspace.querySelectorAll("button")]
                .find((button) => button.innerText.includes("إضافة وجديد"));
            if (!addNewButton) throw new Error("Add & New button is missing");
            addNewButton.click();
            const savedRow = await waitForText(".o_hosny_transaction_table tbody tr", label);
            if (!savedRow.innerText.includes(accountCode)) throw new Error("Saved account is missing from row");
            if (!savedRow.innerText.includes("تعيين الشريك")) throw new Error("Set Partner is missing");
            if (!savedRow.innerText.includes("تمت المعالجة")) throw new Error("Arabic processed status is missing");
            if (!savedRow.querySelector(".fa-check-circle.text-success")) {
                throw new Error("Real processed indicator is missing");
            }
            if (workspace.querySelector(".o_hosny_quick_entry input[type='text'].form-control").value) {
                throw new Error("Add & New did not reset the quick row");
            }
            console.log("test successful");
            })();
            """
        self.browser_js(
            "/odoo/accounting",
            browser_code.replace("__ACCOUNT_CODE__", json.dumps(account.code)),
            ready="odoo.isReady === true",
            login=login,
            timeout=90,
        )
