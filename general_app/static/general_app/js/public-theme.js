'use strict';
{
    const key = 'productivum.publicTheme';
    const root = document.documentElement;
    const button = document.querySelector('[data-public-theme-control]');
    const system = window.matchMedia('(prefers-color-scheme: dark)');
    const names = { auto: 'Системная', light: 'Светлая', dark: 'Тёмная' };
    const actions = { auto: 'системную', light: 'светлую', dark: 'тёмную' };
    const cycle = () => system.matches ? ['auto', 'light', 'dark'] : ['auto', 'dark', 'light'];
    const nextMode = () => {
        const modes = cycle();
        return modes[(modes.indexOf(root.dataset.publicTheme) + 1) % modes.length];
    };
    function updateButton() {
        if (!button) return;
        const mode = root.dataset.publicTheme;
        const actual = mode === 'auto' ? (system.matches ? 'тёмная' : 'светлая') : '';
        button.querySelector('[data-public-theme-label]').textContent = ({ auto: 'Авто', light: 'Светлая', dark: 'Тёмная' })[mode];
        const label = `Тема: ${names[mode]}${actual ? ` (${actual})` : ''}. Переключить на ${actions[nextMode()]} тему.`;
        button.setAttribute('aria-label', label);
        button.title = label;
    }
    function apply(mode, persist = false) {
        root.dataset.publicTheme = Object.hasOwn(names, mode) ? mode : 'auto';
        if (persist) {
            try { localStorage.setItem(key, root.dataset.publicTheme); } catch (_) { /* Choice works on this page. */ }
        }
        updateButton();
    }
    apply(root.dataset.publicTheme);
    if (button) {
        button.closest('[data-public-theme-item]').hidden = false;
        button.addEventListener('click', () => apply(nextMode(), true));
    }
    if (system.addEventListener) system.addEventListener('change', updateButton);
    else system.addListener(updateButton);
    document.querySelectorAll('[data-public-dismiss]').forEach(control => {
        control.hidden = false;
        control.addEventListener('click', () => { control.closest('[role=alert]').hidden = true; });
    });
    window.addEventListener('storage', event => {
        if (event.key === key || event.key === null) apply(event.key === null ? 'auto' : event.newValue);
    });
}
