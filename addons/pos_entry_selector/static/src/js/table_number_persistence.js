/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

const FLOOR_PRIORITY_ORDER = {
    "أرضي": 0,
    "علوي": 1,
    "سفري": 2,
    "vip": 3,
};

function getFloorSortKey(floorName) {
    const name = String(floorName || "").trim();
    const key = name.toLowerCase();
    const priority = FLOOR_PRIORITY_ORDER[key] !== undefined ? FLOOR_PRIORITY_ORDER[key] : 99;
    return [priority, key];
}

function sortFloorList(floors) {
    if (!floors || !floors.length) {
        return floors;
    }
    return [...floors].sort((a, b) => {
        const aKey = getFloorSortKey(a.name);
        const bKey = getFloorSortKey(b.name);
        if (aKey[0] !== bKey[0]) {
            return aKey[0] - bKey[0];
        }
        return aKey[1].localeCompare(bKey[1], "ar", { sensitivity: "base" });
    });
}

function getTableLabel(table) {
    return table?.getName?.() || table?.table_number?.toString?.() || table?.name || "";
}

patch(PosStore.prototype, {
    async _processData(loadedData) {
        const result = await super._processData(...arguments);
        if (this.config.module_pos_restaurant && loadedData["restaurant.floor"]) {
            this.floors = sortFloorList(this.floors);
        }
        return result;
    },

    /**
     * Override updateModelsData to refresh table data from database
     * This ensures table names/numbers are always correct after refresh
     */
    async updateModelsData(models_data) {
        // If we have restaurant floors, reload them fresh from database
        if (this.config.module_pos_restaurant && models_data["restaurant.floor"]) {
            try {
                console.log("Reloading restaurant floors from database...");
                const floors = await this.orm.read(
                    "restaurant.floor",
                    [],
                    ["name", "background_color", "table_ids"],
                    { order: "name" }
                );

                if (floors && floors.length > 0) {
                    // Get all table IDs
                    const allTableIds = floors.reduce((acc, floor) => {
                        return acc.concat(floor.table_ids || []);
                    }, []);

                    if (allTableIds.length > 0) {
                        // Load all tables fresh from database
                        const tables = await this.orm.read(
                            "restaurant.table",
                            allTableIds,
                            ["table_number", "shape", "position_h", "position_v", "width", "height", "seats", "color", "floor_id"],
                            { order: "table_number" }
                        );

                        if (tables) {
                            // Create a lookup map for quick access
                            const tableById = {};
                            for (const table of tables) {
                                tableById[table.id] = table;
                            }

                            // Update floors with fresh table data
                            for (const floor of floors) {
                                floor.tables = (floor.table_ids || [])
                                    .map(tableId => tableById[tableId])
                                    .filter(t => t != null);
                            }

                            models_data["restaurant.floor"] = floors;
                            console.log("Restaurant floors reloaded successfully", floors.length, "floors");
                        }
                    }
                }
            } catch (error) {
                console.warn("Error reloading restaurant floors:", error);
                // Continue with default behavior if reload fails
            }
        }

        const result = await super.updateModelsData(models_data);
        if (this.config.module_pos_restaurant && this.floors) {
            this.floors = sortFloorList(this.floors);
        }
        return result;
    },

    /**
     * Force refresh of restaurant floor data from server
     */
    async refreshTableNumbers() {
        if (!this.config.module_pos_restaurant) return;

        try {
            console.log("Forcing refresh of table numbers from database...");
            const floors = await this.orm.read(
                "restaurant.floor",
                [],
                ["name", "background_color", "table_ids"],
                { order: "name" }
            );

            if (floors && floors.length > 0) {
                const allTableIds = floors.reduce((acc, floor) => {
                    return acc.concat(floor.table_ids || []);
                }, []);

                if (allTableIds.length > 0) {
                    const tables = await this.orm.read(
                        "restaurant.table",
                        allTableIds,
                        ["table_number", "shape", "position_h", "position_v", "width", "height", "seats", "color", "floor_id"],
                        { order: "table_number" }
                    );

                    if (tables) {
                        const tableById = {};
                        for (const table of tables) {
                            tableById[table.id] = table;
                        }

                        // Update existing tables with fresh data from database
                        for (const floor of this.floors) {
                            for (const table of floor.tables || []) {
                                if (tableById[table.id]) {
                                    // Update table properties from database
                                    const freshData = tableById[table.id];
                                    table.table_number = freshData.table_number;
                                    table.shape = freshData.shape;
                                    table.position_h = freshData.position_h;
                                    table.position_v = freshData.position_v;
                                    table.width = freshData.width;
                                    table.height = freshData.height;
                                    table.seats = freshData.seats;
                                    table.color = freshData.color;
                                }
                            }
                        }

                        this.loadRestaurantFloor();
                        if (this.config.module_pos_restaurant && this.floors) {
                            this.floors = sortFloorList(this.floors);
                        }
                        console.log("Table numbers refreshed successfully", this.floors.flatMap((floor) => floor.tables || []).map(getTableLabel));
                    }
                }
            }
        } catch (error) {
            console.error("Error refreshing table numbers:", error);
        }
    }
});
