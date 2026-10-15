import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const bootstrap = readFileSync(new URL('../../general_app/templates/general_app/includes/public_theme_init.html', import.meta.url), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const script = readFileSync(new URL('../../general_app/static/general_app/js/public-theme.js', import.meta.url), 'utf8');
const css = readFileSync(new URL('../../general_app/static/general_app/css/public.css', import.meta.url), 'utf8');
const key = 'productivum.publicTheme';

function page({ dark = false, stored, readFails = false, writeFails = false, propertyFails = false, storage } = {}) {
    const values = storage ?? new Map(stored === undefined ? [] : [[key, stored]]);
    const writes = [];
    const clicks = [];
    const changes = [];
    const events = new Map();
    const root = { dataset: { publicTheme: 'auto' } };
    const label = { textContent: '' };
    const button = {
        hidden: false, attrs: {}, title: '',
        closest(selector) { assert.equal(selector, '[data-public-theme-item]'); return this; },
        querySelector(selector) { assert.equal(selector, '[data-public-theme-label]'); return label; },
        setAttribute(name, value) { this.attrs[name] = value; },
        addEventListener(name, callback) { assert.equal(name, 'click'); clicks.push(callback); },
    };
    const system = { matches: dark, addEventListener(name, callback) {
        assert.equal(name, 'change'); changes.push(callback);
    } };
    const context = {
        document: { documentElement: root, querySelectorAll() { return []; }, querySelector(selector) {
            assert.equal(selector, '[data-public-theme-control]'); return button;
        } },
        window: { matchMedia(query) { assert.equal(query, '(prefers-color-scheme: dark)'); return system; },
            addEventListener(name, callback) { assert.equal(name, 'storage'); events.set(name, callback); } },
    };
    Object.defineProperty(context, 'localStorage', { get() {
        if (propertyFails) throw new Error('Storage is unavailable');
        return {
            getItem(name) { assert.equal(name, key); if (readFails) throw new Error('Read denied'); return values.get(name) ?? null; },
            setItem(name, value) { assert.equal(name, key); if (writeFails) throw new Error('Write denied'); writes.push([name, value]); values.set(name, value); },
        };
    } });
    vm.createContext(context);
    vm.runInContext(bootstrap, context);
    const initial = root.dataset.publicTheme;
    vm.runInContext(script, context);
    return {
        root, button, label, writes, values, initial, clicks,
        click() { assert.equal(clicks.length, 1); clicks[0](); },
        systemChange(value) { system.matches = value; for (const change of changes) change(); },
        storageEvent(event) { events.get('storage')(event); },
    };
}

test('a new or invalid preference starts in auto before styles without a storage write', () => {
    for (const dark of [false, true]) {
        for (const stored of [undefined, '', 'invalid', 'system', '__proto__']) {
            const p = page({ dark, stored });
            assert.equal(p.initial, 'auto');
            assert.equal(p.root.dataset.publicTheme, 'auto');
            assert.deepEqual(p.writes, []);
            assert.equal(p.button.hidden, false);
            assert.match(p.button.attrs['aria-label'], dark ? /Системная \(тёмная\).*светлую/ : /Системная \(светлая\).*тёмную/);
        }
    }
});

test('the single button cycles auto-dark-light-auto for a light system', () => {
    const p = page();
    for (const mode of ['dark', 'light', 'auto']) {
        p.click();
        assert.equal(p.root.dataset.publicTheme, mode);
        assert.equal(p.values.get(key), mode);
    }
    assert.equal(p.clicks.length, 1);
    assert.equal(p.writes.length, 3);
    assert.equal(p.label.textContent, 'Авто');
});

test('the single button cycles auto-light-dark-auto for a dark system', () => {
    const p = page({ dark: true });
    for (const mode of ['light', 'dark', 'auto']) {
        p.click();
        assert.equal(p.root.dataset.publicTheme, mode);
        assert.equal(p.values.get(key), mode);
    }
    assert.match(p.button.title, /Системная \(тёмная\).*светлую/);
});

test('OS changes update auto labeling and never overwrite a manual choice', () => {
    const p = page();
    p.systemChange(true);
    assert.equal(p.root.dataset.publicTheme, 'auto');
    assert.match(p.button.title, /Системная \(тёмная\)/);
    p.click();
    assert.equal(p.root.dataset.publicTheme, 'light');
    p.systemChange(false);
    assert.equal(p.root.dataset.publicTheme, 'light');
    assert.equal(p.label.textContent, 'Светлая');
    p.click();
    assert.equal(p.root.dataset.publicTheme, 'auto');
    assert.match(p.button.title, /Системная \(светлая\)/);
    assert.equal(p.writes.length, 2);
});

test('manual preference survives navigation and reload independently of the OS', () => {
    const first = page();
    first.click();
    const next = page({ dark: true, storage: first.values });
    assert.equal(next.initial, 'dark');
    assert.equal(next.root.dataset.publicTheme, 'dark');
    assert.deepEqual(next.writes, []);
});

test('denied reads, writes and access to storage do not break switching', () => {
    for (const options of [{ readFails: true }, { writeFails: true }, { propertyFails: true },
                           { readFails: true, writeFails: true }]) {
        const p = page(options);
        assert.equal(p.initial, 'auto');
        p.click();
        assert.equal(p.root.dataset.publicTheme, 'dark');
        assert.equal(p.label.textContent, 'Тёмная');
        p.click();
        assert.equal(p.root.dataset.publicTheme, 'light');
    }
});

test('cross-tab events update only the public key without recursive writes', () => {
    const values = new Map([['theme', 'light'], ['productivum.publicTheme', 'dark']]);
    const p = page({ storage: values });
    p.storageEvent({ key: 'theme', newValue: 'auto' });
    assert.equal(p.root.dataset.publicTheme, 'dark');
    p.storageEvent({ key, newValue: 'light' });
    assert.equal(p.root.dataset.publicTheme, 'light');
    p.storageEvent({ key, newValue: '__proto__' });
    assert.equal(p.root.dataset.publicTheme, 'auto');
    p.storageEvent({ key: null });
    assert.equal(p.root.dataset.publicTheme, 'auto');
    assert.deepEqual(p.writes, []);
    assert.equal(values.get('theme'), 'light');
});

function rules(selector) {
    const marker = selector + ' {';
    const start = css.indexOf(marker);
    assert.notEqual(start, -1);
    return css.slice(start + marker.length, css.indexOf('}', start));
}
function palette(selector) {
    return Object.fromEntries([...rules(selector).matchAll(/--public-([\w-]+):\s*(#[\da-f]{6});/g)].map(match => [match[1], match[2]]));
}

test('CSS makes auto follow the OS without JS and keeps manual light and dark isolated', () => {
    assert.deepEqual(palette('html[data-public-theme="auto"]'), palette('html[data-public-theme="dark"]'));
    assert.match(css, /@media \(prefers-color-scheme: dark\)\s*{\s*html\[data-public-theme="auto"\]/);
    assert.match(rules('html[data-public-theme]'), /color-scheme: light;/);
    assert.match(rules('html[data-public-theme="dark"]'), /color-scheme: dark;/);
    assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
    assert.doesNotMatch(css, /@import|!important/);
    assert.doesNotMatch(script, /getItem\(|setItem\(['"]theme['"]/);
});

function luminance(hex) {
    const channels = hex.slice(1).match(/../g).map(part => parseInt(part, 16) / 255)
        .map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}
function contrast(a, b) {
    const [lighter, darker] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (lighter + 0.05) / (darker + 0.05);
}

test('both palettes meet 4.5:1 for ordinary text, muted text, links, errors and buttons', () => {
    for (const selector of ['html[data-public-theme]', 'html[data-public-theme="dark"]']) {
        const p = palette(selector);
        for (const foreground of ['text', 'muted', 'accent', 'accent-hover']) {
            for (const background of ['bg', 'surface', 'panel', 'selection']) {
                const ratio = contrast(p[foreground], p[background]);
                assert.ok(ratio >= 4.5, `${selector}: ${foreground}/${background} = ${ratio.toFixed(2)}`);
            }
        }
        for (const [foreground, background] of [['on-accent', 'accent'], ['on-accent', 'accent-hover'], ['error', 'error-bg']]) {
            assert.ok(contrast(p[foreground], p[background]) >= 4.5, `${selector}: ${foreground}/${background}`);
        }
    }
});

test('navigation glass has an opaque fallback and honors reduced transparency and contrast', () => {
    assert.match(css, /\.public-page \.nav-menu \{ background: var\(--public-surface\)/);
    assert.match(css, /@supports \(/);
    assert.match(css, /prefers-reduced-transparency: reduce/);
    assert.match(css, /prefers-contrast: more/);
    assert.match(css, /forced-colors: active/);
});
