'use strict';
{
    // Django's data-theme modes and localStorage key remain the single source
    // of preference. CSS handles live prefers-color-scheme changes in auto.
    // Unlike the stock 6.0 script, blocked storage must not stop the toggle.
    const modes = ['auto', 'light', 'dark'];

    function setTheme(mode, persist = false) {
        document.documentElement.dataset.theme = modes.includes(mode) ? mode : 'auto';
        if (persist) {
            try {
                localStorage.setItem('theme', document.documentElement.dataset.theme);
            } catch (_) {
                // The chosen mode still works for this page without storage.
            }
        }
    }

    let savedTheme;
    try {
        savedTheme = localStorage.getItem('theme');
    } catch (_) {
        // A new session with inaccessible storage starts in system mode.
    }
    // Synchronous head script: apply the preference before the first paint.
    setTheme(savedTheme);

    document.addEventListener('click', event => {
        if (!event.target.closest('.theme-toggle')) return;
        const current = modes.indexOf(document.documentElement.dataset.theme);
        setTheme(modes[(current + 1) % modes.length], true);
    });

    window.addEventListener('storage', event => {
        if (event.key === 'theme' || event.key === null) {
            setTheme(event.key === null ? 'auto' : event.newValue);
        }
    });
}
