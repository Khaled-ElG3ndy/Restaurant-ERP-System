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

    /*
     * السرعة: الأصناف والطاولات تُنسخ مرة واحدة عند الفتح إلى كائنات عادية.
     * قراءة أسطر الطلب من النموذج أثناء العرض كانت تعيد حساب الأسعار
     * والضرائب (priceIncl) عشرات المرات مع كل علامة، وتربط النافذة بتحديثات
     * الطلب والطاولات كلها. الآن العرض يقرأ النسخة و state.sel فقط.
     */
    setup() {
        this.pos = usePos();
        this.notification = useService("notification");
        this.currency = {
            symbol: this.pos.currency?.symbol || "SR",
            decimals: this.pos.currency?.decimal_places ?? 2,
        };
        const order = this.props.order;
        this.sourceTable = order.table_id || null;
        this.sourceTitle = this.sourceTable ? `طاولة ${tableLabel(this.sourceTable)}` : "طلب بدون طاولة";
        this.rows = (order.lines || [])
            .filter((line) => !line.combo_parent_id && line.qty > EPS)
            .map((line) => ({
                uuid: line.uuid,
                name: lineName(line),
                qty: line.qty,
                unit: line.qty ? (line.priceIncl ?? 0) / line.qty : 0,
                note: line.note || "",
                combo: Boolean(line.combo_line_ids?.length),
                children: (line.combo_line_ids || []).map((child) => ({ uuid: child.uuid, qty: child.qty })),
            }));
        this.floorsSnap = null;
        const sel = {};
        for (const row of this.rows) {
            sel[row.uuid] = 0;
        }
        this.state = useState({ step: 1, sel, floorId: null, tableId: null, busy: false, error: "" });
    }

    get order() {
        return this.props.order;
    }

    /** الأدوار والطاولات وحالتها، مرة واحدة عند الوصول للخطوة 2. */
    _snapshotFloors() {
        const sourceIds = new Set([this.sourceTable?.id, this.sourceTable?.rootTable?.id].filter(Boolean));
        const floors = (this.pos.models["restaurant.floor"]?.getAll?.() || [])
            .filter((floor) => (floor.table_ids || []).length)
            .sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
        return floors.map((floor) => {
            const tables = [...floor.table_ids]
                .filter((table) => table.active !== false && !table.parent_id)
                .sort((a, b) => (a.table_number || 0) - (b.table_number || 0))
                .map((table) => {
                    const orders = (this.pos.getActiveOrdersOnTable?.(table) || []).filter(
                        (o) => o.uuid !== this.order.uuid
                    );
                    return {
                        id: table.id,
                        record: table,
                        label: tableLabel(table),
                        source: sourceIds.has(table.id),
                        busy: orders.length > 0,
                        amount: orders.reduce((sum, o) => sum + (o.priceIncl ?? o.amount_total ?? 0), 0),
                    };
                });
            return {
                id: floor.id,
                name: floor.name,
                tables,
                busyCount: tables.filter((t) => t.busy && !t.source).length,
            };
        });
    }
    get floors() {
        return this.floorsSnap || [];
    }
    get floorTables() {
        return this.floors.find((f) => f.id === this.state.floorId)?.tables || [];
    }
    get pickedTable() {
        for (const floor of this.floors) {
            const table = floor.tables.find((t) => t.id === this.state.tableId);
            if (table) {
                return table;
            }
        }
        return null;
    }

    // ── التحديد ─────────────────────────────────────────────────────────
    selQty(row) {
        return this.state.sel[row.uuid] || 0;
    }
    isFull(row) {
        return Math.abs(this.selQty(row) - row.qty) < EPS;
    }
    /** كل ما يعرضه الجدول والملخص في مرور واحد. */
    get view() {
        let items = 0;
        let pieces = 0;
        let amount = 0;
        let full = 0;
        for (const row of this.rows) {
            const qty = this.selQty(row);
            if (qty > EPS) {
                items++;
                pieces += qty;
                amount += row.unit * qty;
                if (Math.abs(qty - row.qty) < EPS) {
                    full++;
                }
            }
        }
        const allFull = this.rows.length > 0 && full === this.rows.length;
        return { items, pieces, amount, any: items > 0, allFull };
    }
    toggleLine(row) {
        this.state.sel[row.uuid] = this.selQty(row) > EPS ? 0 : row.qty;
    }
    toggleAll() {
        const full = !this.view.allFull;
        for (const row of this.rows) {
            this.state.sel[row.uuid] = full ? row.qty : 0;
        }
    }
    stepQty(row, direction) {
        const next = Math.round((this.selQty(row) + direction) * 1000) / 1000;
        this.state.sel[row.uuid] = Math.max(0, Math.min(row.qty, next));
    }
    typeQty(row, ev) {
        const value = parseFloat(String(ev.target.value).replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d)).replace(",", "."));
        const qty = Number.isFinite(value) ? Math.max(0, Math.min(row.qty, value)) : 0;
        this.state.sel[row.uuid] = qty;
        if (qty !== value) {
            ev.target.value = qty ? qtyText(qty) : "";
        }
    }
    money(amount) {
        const number = (Number(amount) || 0).toFixed(this.currency.decimals);
        return `\u2066${number}\u00a0${this.currency.symbol}\u2069`;
    }
    qtyText(qty) {
        return qtyText(qty);
    }
    itemsText(n) {
        return itemsText(n);
    }

    // ── الخطوات ─────────────────────────────────────────────────────────
    next() {
        this.state.error = "";
        if (!this.view.any) {
            this.state.error = "حدد صنفاً واحداً على الأقل، أو علّم على الكل للتحويل الكلي.";
            return;
        }
        if (!this.floorsSnap) {
            this.floorsSnap = this._snapshotFloors();
            const sourceFloorId = this.sourceTable?.floor_id?.id;
            this.state.floorId =
                this.floorsSnap.find((f) => f.id === sourceFloorId)?.id || this.floorsSnap[0]?.id || null;
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
        if (!table.source) {
            this.state.tableId = table.id;
        }
    }
    pickAndGo(table) {
        if (!table.source) {
            this.state.tableId = table.id;
            this.confirm();
        }
    }

    async confirm() {
        const picked = this.pickedTable;
        if (!picked || this.state.busy) {
            return;
        }
        const view = this.view;
        this.state.busy = true;
        this.state.error = "";
        try {
            if (view.allFull) {
                await this.pos.transferOrder(this.order.uuid, picked.record);
            } else {
                if (typeof this.pos.partialTransferOrderLines !== "function") {
                    throw new Error("موديول التحويل الجزئي (hosny_pos_partial_transfer) غير مثبت.");
                }
                await this.pos.partialTransferOrderLines(this.order, picked.id, this.transfers);
            }
            this.notification.add(
                view.allFull
                    ? `تم نقل الطلب إلى طاولة ${picked.label}`
                    : `تم نقل ${itemsText(view.items)} إلى طاولة ${picked.label}`,
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
        for (const row of this.rows) {
            const qty = this.selQty(row);
            if (qty <= EPS) {
                continue;
            }
            result.push({ lineId: row.uuid, quantity: qty });
            for (const child of row.children) {
                const share = row.qty ? (child.qty * qty) / row.qty : 0;
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
