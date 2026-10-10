/** @odoo-module **/

/**
 * القوائم المنسدلة في نقطة البيع (قائمة ☰ وغيرها) لا تظهر إلا في مكانها
 * النهائي (2026-10-10): كانت قائمة ☰ تظهر لحظة على اليسار ثم تقفز تحت الزر.
 * القائمة تبقى شفافة حتى يثبت موضعها ومقاسها إطاراً كاملاً، ثم تظهر
 * (skin.css «hosny-pop-settled»). أقصى انتظار 12 إطاراً أو 250ms — ما يأتي أولاً،
 * فلا تبقى مخفية أبداً حتى لو أبطأ المتصفح الإطارات.
 */
import { onMounted, onWillUnmount } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { Popover } from "@web/core/popover/popover";

const SETTLED_CLASS = "hosny-pop-settled";
const MAX_FRAMES = 12;
const MAX_WAIT_MS = 250;

patch(Popover.prototype, {
    setup() {
        super.setup(...arguments);
        let frames = 0;
        let lastBox = null;
        let handle = null;
        let timer = null;
        const reveal = () => {
            cancelAnimationFrame(handle);
            clearTimeout(timer);
            this.popoverRef.el?.classList.add(SETTLED_CLASS);
        };
        const settle = () => {
            const el = this.popoverRef.el;
            if (!el) {
                return;
            }
            const box = el.getBoundingClientRect();
            const key = [box.left, box.top, box.width, box.height].map(Math.round).join(",");
            if (key === lastBox || ++frames >= MAX_FRAMES) {
                reveal();
                return;
            }
            lastBox = key;
            handle = requestAnimationFrame(settle);
        };
        onMounted(() => {
            // قوائم الـ Dropdown فقط (props.class قد يكون نصاً أو كائناً، فنقرأ العنصر نفسه)
            if (!this.popoverRef.el?.classList.contains("o-dropdown--menu")) {
                return;
            }
            handle = requestAnimationFrame(settle);
            timer = setTimeout(reveal, MAX_WAIT_MS);
        });
        onWillUnmount(() => {
            cancelAnimationFrame(handle);
            clearTimeout(timer);
        });
    },
});
