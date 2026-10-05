/** @odoo-module **/

const serviceWorker = navigator.serviceWorker;

if (serviceWorker?.register) {
    const originalRegister = serviceWorker.register.bind(serviceWorker);

    try {
        serviceWorker.register = async (...args) => {
            try {
                return await originalRegister(...args);
            } catch (error) {
                console.warn("POS service worker registration skipped:", error);
                return {
                    installing: null,
                    waiting: null,
                    active: {
                        postMessage() {},
                    },
                };
            }
        };
    } catch (error) {
        console.warn("POS service worker guard could not be installed:", error);
    }
}
