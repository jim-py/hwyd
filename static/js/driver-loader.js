export async function loadDriver() {
    if (window.driver?.js?.driver) return;

    await new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "/static/js/driver.js.iife.js";
        script.async = true;

        script.onload = () => {
            const start = performance.now();
            const check = () => {
                if (window.driver?.js?.driver) return resolve();
                if (performance.now() - start > 2000) return reject(new Error("Driver.js загрузился, но driver не найден"));
                requestAnimationFrame(check);
            };
            check();
        };

        script.onerror = () => reject(new Error("Ошибка загрузки driver.js"));
        document.head.appendChild(script);
    });
}