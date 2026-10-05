/** @odoo-module **/

import { useExternalListener, useState } from "@odoo/owl";
import { ListRenderer } from "@web/views/list/list_renderer";
import { ListController } from "@web/views/list/list_controller";
import { PurchaseOrderLineCompareListRenderer } from "@purchase_requisition/views/list/purchase_order_line_compare_list_renderer";
import { PurchaseOrderLineCompareListView } from "@purchase_requisition/views/list/purchase_order_line_compare_list_view";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

PurchaseOrderLineCompareListRenderer.recordRowTemplate =
    "hosny_purchase_requisition_name.PurchaseOrderLineCompareListRenderer.RecordRow";

export class HosnyPurchaseOrderLineCompareListController extends ListController {
    get lowestPriceSearchItemId() {
        const searchItems = this.env.searchModel?.searchItems || {};
        const item = Object.values(searchItems).find((searchItem) => searchItem.name === "hosny_lowest_price");
        return item?.id;
    }

    get isLowestPriceFilterActive() {
        const itemId = this.lowestPriceSearchItemId;
        if (!itemId) {
            return false;
        }
        return this.env.searchModel.query.some((queryElement) => queryElement.searchItemId === itemId);
    }

    toggleLowestPriceFilter() {
        const itemId = this.lowestPriceSearchItemId;
        if (itemId) {
            this.env.searchModel.toggleSearchItem(itemId);
        }
    }
}

HosnyPurchaseOrderLineCompareListController.template =
    "hosny_purchase_requisition_name.PurchaseOrderLineCompareListView";

registry.category("views").add("purchase_order_line_compare", {
    ...PurchaseOrderLineCompareListView,
    Controller: HosnyPurchaseOrderLineCompareListController,
    Renderer: PurchaseOrderLineCompareListRenderer,
}, { force: true });

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.hosnyActionService = useService("action");
        this.hosnyOrmService = useService("orm");
        this.hosnyLastPriceHistoryClickTarget = null;
        useExternalListener(
            document,
            "click",
            (ev) => {
                const button = ev.target.closest?.(".o_hosny_price_history_line_button");
                if (button) {
                    this.hosnyLastPriceHistoryClickTarget = ev.target;
                }
            },
            { capture: true }
        );
    },

    isHosnyPriceHistoryButton(button) {
        return button?.clickParams?.name === "action_hosny_open_price_history";
    },

    getHosnyRecordProductId(record) {
        const product = record.data.product_id;
        if (Array.isArray(product)) {
            return product[0];
        }
        return product?.resId || product?.id || product || false;
    },

    getHosnyRecordCurrencyId(record) {
        const currency = record.data.currency_id || record.model?.root?.data?.currency_id;
        if (Array.isArray(currency)) {
            return currency[0];
        }
        return currency?.resId || currency?.id || currency || false;
    },

    getHosnyPriceHistoryRecordFromClick() {
        const target = this.hosnyLastPriceHistoryClickTarget || document.activeElement;
        const button = target?.closest?.(".o_hosny_price_history_line_button");
        const row = button?.closest?.("tr.o_data_row");
        if (!row) {
            return false;
        }
        return this.props.list.records.find((record) => record.id === row.dataset.id) || false;
    },

    async openHosnyPriceHistoryForRecord(record) {
        const productId = this.getHosnyRecordProductId(record);
        if (!productId) {
            super.displaySaveNotification(...arguments);
            return;
        }
        const action = await this.hosnyOrmService.call(
            "purchase.order.line",
            "action_hosny_open_price_history_for_product",
            [productId, this.getHosnyRecordCurrencyId(record)],
            { context: record.context }
        );
        await this.hosnyActionService.doAction(action);
    },

    async displaySaveNotification() {
        const record = this.getHosnyPriceHistoryRecordFromClick();
        if (record?.isNew) {
            await this.openHosnyPriceHistoryForRecord(record);
            this.hosnyLastPriceHistoryClickTarget = null;
            return;
        }
        this.hosnyLastPriceHistoryClickTarget = null;
        return super.displaySaveNotification(...arguments);
    },
});

patch(PurchaseOrderLineCompareListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.purchaseInvoiceHistory = useState({ byProductId: {} });
    },

    async updateBestFields() {
        await super.updateBestFields(...arguments);
        await this.updatePurchaseInvoiceHistory();
    },

    async updatePurchaseInvoiceHistory() {
        const purchaseOrderId = this.props.list.context.purchase_order_id || this.props.list.context.active_id;
        if (!purchaseOrderId) {
            this.purchaseInvoiceHistory.byProductId = {};
            return;
        }
        this.purchaseInvoiceHistory.byProductId = await this.props.list.model.orm.call(
            "purchase.order",
            "get_compare_line_purchase_invoice_price_history",
            [purchaseOrderId],
            { context: this.props.list.context }
        );
    },

    getCompareLineProductId(record) {
        const product = record.data.product_id;
        if (Array.isArray(product)) {
            return product[0];
        }
        return product?.resId || product?.id || product || false;
    },

    hasCompareLineProduct(record) {
        return Boolean(this.getCompareLineProductId(record));
    },

    getPurchaseInvoiceHistory(record) {
        const productId = this.getCompareLineProductId(record);
        return this.purchaseInvoiceHistory.byProductId[productId] || [];
    },
});
