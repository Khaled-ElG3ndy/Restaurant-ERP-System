/** @odoo-module **/

function movePaymentNumpad() {
    const screen = document.querySelector(".payment-screen");
    if (!screen) return;

    const leftContent = screen.querySelector(".left-content");
    const paymentMethodsContainer = screen.querySelector(".left-content .paymentmethods-container");
    const validationButton = screen.querySelector(".left-content .validation");
    const numpad = screen.querySelector(".center-content .numpad");

    if (!leftContent || !paymentMethodsContainer || !numpad) {
        return;
    }

    let wrapper = screen.querySelector(".left-content .pos-payment-left-numpad");
    if (!wrapper) {
        wrapper = document.createElement("div");
        wrapper.className = "pos-payment-left-numpad";
    }

    if (numpad.parentElement !== wrapper) {
        wrapper.appendChild(numpad);
    }

    if (validationButton) {
        if (wrapper.parentElement !== leftContent || wrapper.nextElementSibling !== validationButton) {
            leftContent.insertBefore(wrapper, validationButton);
        }
    } else if (wrapper.parentElement !== leftContent) {
        leftContent.appendChild(wrapper);
    }
}

function startObserver() {
    const target = document.body;
    if (!target) {
        setTimeout(startObserver, 100);
        return;
    }

    movePaymentNumpad();

    const observer = new MutationObserver(() => {
        movePaymentNumpad();
    });

    observer.observe(target, {
        childList: true,
        subtree: true,
    });

    document.addEventListener("click", () => {
        setTimeout(movePaymentNumpad, 0);
    });

    window.addEventListener("load", () => {
        setTimeout(movePaymentNumpad, 0);
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startObserver);
} else {
    startObserver();
}
