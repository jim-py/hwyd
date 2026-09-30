export function forceShowHiddenButtons(selectors) {
    const modified = [];

    selectors.forEach(selector => {
        const el = document.querySelector(selector);
        if (!el) return;

        const computed = getComputedStyle(el);

        if (computed.display === "none" || el.hidden) {
            modified.push({
                el,
                originalDisplay: el.style.display,
                wasHidden: el.hidden
            });

            el.hidden = false;

            if (computed.display === "none") {
                el.style.display = "block";
            }
        }
    });

    return () => {
        modified.forEach(item => {
            item.el.hidden = item.wasHidden;
            item.el.style.display = item.originalDisplay;
        });
    };
}