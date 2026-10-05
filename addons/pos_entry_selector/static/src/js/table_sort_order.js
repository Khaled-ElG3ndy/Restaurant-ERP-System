/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FloorScreen } from "@pos_restaurant/app/screens/floor_screen/floor_screen";

/**
 * Sort table names numerically
 * Handles mixed alphanumeric names (e.g., "Room 1", "Room 2", "Room 10")
 */
function getNumericTableSortKey(tableName) {
    if (!tableName) return [999999];
    
    // Extract all numbers and text parts
    const parts = String(tableName).match(/(\d+|[a-zA-Z]+)/g) || [];
    
    return parts.map(part => {
        const num = parseInt(part, 10);
        return isNaN(num) ? part.toLowerCase() : num;
    });
}

function getVIPTableSortKey(tableName) {
    const name = String(tableName || "").trim();
    const lowerName = name.toLowerCase();

    if (name === "الكبري") {
        return [0];
    }
    if (name === "الصغري") {
        return [1];
    }
    if (name === "200") {
        return [2];
    }

    const safariMatch = name.match(/^سفري\s*(\d+)$/u);
    if (safariMatch) {
        return [3, parseInt(safariMatch[1], 10)];
    }
    if (lowerName === "سفري") {
        return [3, 0];
    }

    return [4].concat(getNumericTableSortKey(name));
}

function getTableLabel(table) {
    return table?.getName?.() || table?.table_number?.toString?.() || table?.name || "";
}

function compareTableNames(a, b) {
    const aKey = getVIPTableSortKey(getTableLabel(a));
    const bKey = getVIPTableSortKey(getTableLabel(b));

    for (let i = 0; i < Math.max(aKey.length, bKey.length); i++) {
        const aVal = aKey[i] ?? (typeof bKey[i] === "number" ? 999999 : "zzz");
        const bVal = bKey[i] ?? (typeof aKey[i] === "number" ? 999999 : "zzz");

        if (typeof aVal === "number" && typeof bVal === "number") {
            if (aVal !== bVal) return aVal - bVal;
        } else if (typeof aVal === "string" && typeof bVal === "string") {
            if (aVal !== bVal) return aVal.localeCompare(bVal, "ar", { sensitivity: "base" });
        } else {
            const aIsNum = typeof aVal === "number";
            const bIsNum = typeof bVal === "number";
            if (aIsNum !== bIsNum) return aIsNum ? -1 : 1;
        }
    }

    return 0;
}

patch(FloorScreen.prototype, {
    get activeTables() {
        const tables = this.activeFloor?.table_ids?.filter((table) => table.active) || [];
        if (!tables || tables.length === 0) {
            return tables;
        }

        // Create a sorted copy to avoid mutating the original
        const sortedTables = [...tables].sort(compareTableNames);

        console.log("Tables sorted with VIP order:", sortedTables.map(getTableLabel));

        return sortedTables;
    },
});
