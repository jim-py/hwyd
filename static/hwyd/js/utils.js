export function forceShowHiddenButtons(selectors) {
    const modified = [];

    selectors.forEach(selector => {
        const el = document.querySelector(selector);
        if (!el) return;

        const computed = getComputedStyle(el);

        if (computed.display === "none" || el.hidden) {
            modified.push({
                el,
                originalStyle: el.getAttribute('style'),
                originalHidden: el.getAttribute('hidden')
            });

            el.hidden = false;

            if (getComputedStyle(el).display === "none") {
                el.style.display = el.tagName === 'BUTTON' ? 'flex' : 'inline';
            }
        }
    });

    return () => {
        modified.forEach(item => {
            if (item.originalHidden === null) item.el.removeAttribute('hidden');
            else item.el.setAttribute('hidden', item.originalHidden);
            if (item.originalStyle === null) item.el.removeAttribute('style');
            else item.el.setAttribute('style', item.originalStyle);
        });
    };
}
