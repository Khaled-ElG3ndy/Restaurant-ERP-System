/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

/* Keep one visual row free for the floating pager.  The remaining rows are
 * calculated from the actual screen, card and grid dimensions, so a smaller
 * till naturally gets fewer products on each page. */
const PAGER_VERTICAL_SPACE = 54;
const DEFAULT_PRODUCTS_PER_PAGE = 32;
const MAX_VISIBLE_PAGE_TABS = 3;

function getProductGroups(pos) {
    const groups = pos?.productToDisplayByCateg;
    if (!Array.isArray(groups)) {
        return [];
    }
    return groups
        .filter((group) => Array.isArray(group?.[1]) && group[1].length)
        .map(([categoryId, products]) => [categoryId, products]);
}

function getNumericStyleValue(style, property) {
    return Number.parseFloat(style?.[property] || "0") || 0;
}

patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);

        this.hosnyProductPager = useState({
            page: 0,
            perPage: DEFAULT_PRODUCTS_PER_PAGE,
        });
        this.hosnyProductScrollerRef = useRef("hosnyProductScroller");
        this._hosnyProductPagerSignature = null;
        this._hosnyProductPagerObserver = null;
        this._hosnyProductPagerResizeHandler = null;

        onMounted(() => {
            const scheduleMeasurement = () => {
                window.requestAnimationFrame(() => this.measureHosnyProductPage());
            };
            const scroller = this.getHosnyProductScroller();

            this._hosnyProductPagerResizeHandler = scheduleMeasurement;
            if (scroller && typeof ResizeObserver !== "undefined") {
                this._hosnyProductPagerObserver = new ResizeObserver(scheduleMeasurement);
                this._hosnyProductPagerObserver.observe(scroller);
            }
            window.addEventListener("resize", scheduleMeasurement);
            scheduleMeasurement();
        });

        onWillUnmount(() => {
            this._hosnyProductPagerObserver?.disconnect();
            if (this._hosnyProductPagerResizeHandler) {
                window.removeEventListener("resize", this._hosnyProductPagerResizeHandler);
            }
        });
    },

    getHosnyProductScroller() {
        return this.hosnyProductScrollerRef?.el || null;
    },

    /** Measure the page from the rendered grid instead of fixing a number of
     * cards. This makes the pager fit the catalogue on both desktop and POS
     * touch screens, including when the alphabetical rail takes a column. */
    measureHosnyProductPage() {
        const scroller = this.getHosnyProductScroller();
        const card = scroller?.querySelector(".product");
        if (!scroller || !card) {
            return;
        }

        const scrollerStyle = window.getComputedStyle(scroller);
        const cardBox = card.getBoundingClientRect();
        const cardWidth = cardBox.width;
        const cardHeight = cardBox.height;
        if (!cardWidth || !cardHeight) {
            return;
        }

        const horizontalGap = getNumericStyleValue(scrollerStyle, "columnGap");
        const verticalGap = getNumericStyleValue(scrollerStyle, "rowGap");
        const usableWidth = Math.max(
            1,
            scroller.clientWidth -
                getNumericStyleValue(scrollerStyle, "paddingLeft") -
                getNumericStyleValue(scrollerStyle, "paddingRight")
        );
        const usableHeight = Math.max(
            1,
            scroller.clientHeight -
                getNumericStyleValue(scrollerStyle, "paddingTop") -
                getNumericStyleValue(scrollerStyle, "paddingBottom") -
                PAGER_VERTICAL_SPACE
        );
        const columns = Math.max(1, Math.floor((usableWidth + horizontalGap) / (cardWidth + horizontalGap)));
        const rows = Math.max(1, Math.floor((usableHeight + verticalGap) / (cardHeight + verticalGap)));
        const perPage = columns * rows;

        if (perPage !== this.hosnyProductPager.perPage) {
            this.hosnyProductPager.perPage = perPage;
        }
    },

    getHosnyProductPagination() {
        const groups = getProductGroups(this.pos);
        const totalProducts = groups.reduce((total, [, products]) => total + products.length, 0);
        const perPage = Math.max(1, this.hosnyProductPager.perPage || DEFAULT_PRODUCTS_PER_PAGE);
        const totalPages = Math.max(1, Math.ceil(totalProducts / perPage));
        const signature = [
            this.pos?.selectedCategory?.id || 0,
            this.pos?.searchProductWord || "",
            this.pos?.hosnyProductLetterFilter || "",
            perPage,
            groups.flatMap(([, products]) => products.map((product) => product.id)).join(","),
        ].join("|");

        if (signature !== this._hosnyProductPagerSignature) {
            this._hosnyProductPagerSignature = signature;
            if (this.hosnyProductPager.page !== 0) {
                this.hosnyProductPager.page = 0;
            }
        } else if (this.hosnyProductPager.page >= totalPages) {
            this.hosnyProductPager.page = totalPages - 1;
        }

        return {
            groups,
            totalProducts,
            perPage,
            totalPages,
            page: Math.min(this.hosnyProductPager.page, totalPages - 1),
        };
    },

    /** The base template retains its category groups; only the current page's
     * portion of each group is rendered. This preserves existing product-card
     * behavior, search, letter filtering and click handlers. */
    get hosnyPagedProductGroups() {
        const { groups, perPage, page } = this.getHosnyProductPagination();
        let offset = page * perPage;
        let remaining = perPage;
        const pagedGroups = [];

        for (const [categoryId, products] of groups) {
            if (!remaining) {
                break;
            }
            if (offset >= products.length) {
                offset -= products.length;
                continue;
            }
            const pageProducts = products.slice(offset, offset + remaining);
            if (pageProducts.length) {
                pagedGroups.push([categoryId, pageProducts]);
                remaining -= pageProducts.length;
            }
            offset = 0;
        }
        return pagedGroups;
    },

    get hosnyTotalProductPages() {
        return this.getHosnyProductPagination().totalPages;
    },

    get hosnyCurrentProductPage() {
        return this.getHosnyProductPagination().page;
    },

    get hosnyVisibleProductPages() {
        const { totalPages, page } = this.getHosnyProductPagination();
        const tabCount = Math.min(MAX_VISIBLE_PAGE_TABS, totalPages);
        const firstPage = Math.max(0, Math.min(page - 1, totalPages - tabCount));
        return Array.from({ length: tabCount }, (_, index) => firstPage + index);
    },

    previousHosnyProductPage() {
        if (this.hosnyProductPager.page > 0) {
            this.hosnyProductPager.page -= 1;
        }
    },

    nextHosnyProductPage() {
        const { totalPages } = this.getHosnyProductPagination();
        if (this.hosnyProductPager.page < totalPages - 1) {
            this.hosnyProductPager.page += 1;
        }
    },

    goToHosnyProductPage(page) {
        const { totalPages } = this.getHosnyProductPagination();
        const safePage = Math.max(0, Math.min(Number(page) || 0, totalPages - 1));
        this.hosnyProductPager.page = safePage;
    },
});
