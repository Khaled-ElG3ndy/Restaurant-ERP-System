/** @odoo-module **/

/**
 * «نقل الطلبات» بتقسيمة FERP: نافذة واحدة خلف زر «تحويل» تغني عن «تحويل
 * جزئي» و«دمج الطاولات».
 *
 *   1) الأصناف: جدول (تحديد، الاسم، الكمية، الكمية للنقل −/+). تحديد الكل
 *      = تحويل كلي، بعضها أو جزء من الكمية = تحويل جزئي.
 *   2) الطاولة: الأدوار والطاولات؛ الفارغة تنتقل إليها، والمشغولة يُضاف
 *      المنقول إلى طلبها (دمج).
 *
 * التحويل الكلي بدالة أودو transferOrder (تنقل الطلب أو تدمجه وتحفظ حالة
 * المطبخ)، والجزئي بـ partialTransferOrderLines من hosny_pos_partial_transfer.
 */
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";

const EPS = 0.00001;

function money(pos, amount) {
    const number = (Number(amount) || 0).toFixed(pos.currency?.decimal_places ?? 2);
    const symbol = pos.currency?.symbol || "SR";
    return `⁦${number} ${symbol}⁩`;
}

function qtyText(qty) {
    const n = Math.round((Number(qty) || 0) * 1000) / 1000;
    return String(n);
}

/** العدد مع «صنف» بصيغته الصحيحة. */
function itemsText(n) {
    if (n === 1) {
        return "صنف واحد";
    }
    if (n === 2) {
        return "صنفين";
    }
    return n >= 3 && n <= 10 ? `${n} أصناف` : `${n} صنف`;
}

function tableLabel(table) {
    return String(table?.table_number ?? table?.name ?? table?.id ?? "");
}

function lineName(line) {
    return line.getFullProductName?.() || line.full_product_name || line.product_id?.display_name || "";
}

export class HosnyTransferDialog extends Component {
    static template = "hosny_pos_payment.TransferDialog";
    static components = { Dialog };
    static props = { order: Object, close: Function };

    setup() {
        this.pos = usePos();
        this.notification = useService("notification");
        const sel = {};
        for (const line of this.lines) {
            sel[line.uuid] = 0;
        }
        const floors = this.floors;
        const sourceFloorId = this.sourceTable?.floor_id?.id;
        this.state = useState({
            step: 1,
            sel,
            floorId: floors.find((f) => f.id === sourceFloorId)?.id || floors[0]?.id || null,
            tableId: null,
            busy: false,
            error: "",
        });
    }

    // ── البيانات ────────────────────────────────────────────────────────
    get order() {
        return this.props.order;
    }
    /** الأصناف الرئيسية فقط؛ مكوّنات الوجبة تنتقل مع وجبتها. */
    get lines() {
        return (this.order.lines || []).filter((line) => !line.combo_parent_id && line.qty > EPS);
    }
    get sourceTable() {
        return this.order.table_id || null;
    }
    get sourceTitle() {
        return this.sourceTable ? `طاولة ${tableLabel(this.sourceTable)}` : "طلب بدون طاولة";
    }
    get floors() {
        return (this.pos.models["restaurant.floor"]?.getAll?.() || [])
            .filter((floor) => (floor.table_ids || []).length)
            .sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
    }
    get floorTables() {
        const floor = this.floors.find((f) => f.id === this.state.floorId);
        return [...(floor?.table_ids || [])]
            .filter((table) => table.active !== false && !table.parent_id)
            .sort((a, b) => (a.table_number || 0) - (b.table_number || 0));
    }
    tableOrders(table) {
        return (this.pos.getActiveOrdersOnTable?.(table) || []).filter((o) => o.uuid !== this.order.uuid);
    }
    tableAmount(table) {
        return this.tableOrders(table).reduce((sum, o) => sum + (o.priceIncl ?? o.amount_total ?? 0), 0);
    }
    isSource(table) {
        return this.sourceTable && (this.sourceTable.id === table.id || this.sourceTable.rootTable?.id === table.id);
    }
    floorBusyCount(floor) {
        return (floor.table_ids || []).filter((t) => !this.isSource(t) && this.tableOrders(t).length).length;
    }
    get pickedTable() {
        return this.pos.models["restaurant.table"]?.get?.(this.state.tableId) || null;
    }

    // ── التحديد ─────────────────────────────────────────────────────────
    selQty(line) {
        return this.state.sel[line.uuid] || 0;
    }
    isFull(line) {
        return Math.abs(this.selQty(line) - line.qty) < EPS;
    }
    get allFull() {
        return this.lines.length > 0 && this.lines.every((line) => this.isFull(line));
    }
    get anySelected() {
        return this.lines.some((line) => this.selQty(line) > EPS);
    }
    get isFullTransfer() {
        return this.allFull;
    }
    toggleLine(line) {
        this.state.sel[line.uuid] = this.selQty(line) > EPS ? 0 : line.qty;
    }
    toggleAll() {
        const full = !this.allFull;
        for (const line of this.lines) {
            this.state.sel[line.uuid] = full ? line.qty : 0;
        }
    }
    stepQty(line, direction) {
        const next = Math.round((this.selQty(line) + direction) * 1000) / 1000;
        this.state.sel[line.uuid] = Math.max(0, Math.min(line.qty, next));
    }
    typeQty(line, ev) {
        const value = parseFloat(String(ev.target.value).replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d)).replace(",", "."));
        const qty = Number.isFinite(value) ? Math.max(0, Math.min(line.qty, value)) : 0;
        this.state.sel[line.uuid] = qty;
        if (qty !== value) {
            ev.target.value = qty ? qtyText(qty) : "";
        }
    }
    lineAmount(line, qty) {
        const unit = line.qty ? (line.priceIncl ?? 0) / line.qty : 0;
        return unit * qty;
    }
    get summary() {
        const picked = this.lines.filter((line) => this.selQty(line) > EPS);
        return {
            items: picked.length,
            pieces: picked.reduce((sum, line) => sum + this.selQty(line), 0),
            amount: picked.reduce((sum, line) => sum + this.lineAmount(line, this.selQty(line)), 0),
        };
    }
    money(amount) {
        return money(this.pos, amount);
    }
    qtyText(qty) {
        return qtyText(qty);
    }
    lineName(line) {
        return lineName(line);
    }
    tableLabel(table) {
        return tableLabel(table);
    }
    itemsText(n) {
        return itemsText(n);
    }

    // ── الخطوات ─────────────────────────────────────────────────────────
    next() {
        this.state.error = "";
        if (!this.anySelected) {
            this.state.error = "حدد صنفاً واحداً على الأقل، أو علّم على الكل للتحويل الكلي.";
            return;
        }
        this.state.step = 2;
    }
    back() {
        this.state.error = "";
        this.state.step = 1;
    }
    pickFloor(floor) {
        this.state.floorId = floor.id;
    }
    pickTable(table) {
        if (!this.isSource(table)) {
            this.state.tableId = table.id;
        }
    }

    pickAndGo(table) {
        if (!this.isSource(table)) {
            this.state.tableId = table.id;
            this.confirm();
        }
    }

    async confirm() {
        const table = this.pickedTable;
        if (!table || this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        try {
            if (this.isFullTransfer) {
                await this.pos.transferOrder(this.order.uuid, table);
            } else {
                if (typeof this.pos.partialTransferOrderLines !== "function") {
                    throw new Error("موديول التحويل الجزئي (hosny_pos_partial_transfer) غير مثبت.");
                }
                await this.pos.partialTransferOrderLines(this.order, table.id, this.transfers);
            }
            this.notification.add(
                this.isFullTransfer
                    ? `تم نقل الطلب إلى طاولة ${tableLabel(table)}`
                    : `تم نقل ${itemsText(this.summary.items)} إلى طاولة ${tableLabel(table)}`,
                { type: "success" }
            );
            this.props.close();
        } catch (error) {
            this.state.error = error?.message || error?.data?.message || "تعذر إتمام النقل، حاول مرة أخرى.";
        } finally {
            this.state.busy = false;
        }
    }

    /** الكميات للجزئي، ومكوّنات كل وجبة بنفس نسبة وجبتها. */
    get transfers() {
        const result = [];
        for (const line of this.lines) {
            const qty = this.selQty(line);
            if (qty <= EPS) {
                continue;
            }
            result.push({ lineId: line.uuid, quantity: qty });
            for (const child of line.combo_line_ids || []) {
                const share = line.qty ? (child.qty * qty) / line.qty : 0;
                if (share > EPS) {
                    result.push({ lineId: child.uuid, quantity: Math.min(child.qty, share) });
                }
            }
        }
        return result;
    }
}

patch(ControlButtons.prototype, {
    /** التحويل لطلبات الطاولات فقط: السفري لا طاولة له ينتقل منها. */
    get hpCanTransfer() {
        const order = this.pos.getOrder();
        return Boolean(
            order &&
                !order.finalized &&
                order.table_id &&
                !this.pos.isTakeawayOrder?.(order) &&
                (order.lines || []).some((line) => line.qty > EPS)
        );
    },
    clickTransferOrder() {
        if (!this.hpCanTransfer) {
            return;
        }
        this.dialog.closeAll();
        this.dialog.add(HosnyTransferDialog, { order: this.pos.getOrder() });
    },
});
