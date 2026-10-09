import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const script = readFileSync(new URL('../../assets/site/admin/theme.js', import.meta.url), 'utf8');
const css = readFileSync(new URL('../../assets/site/admin/admin.css', import.meta.url), 'utf8');

function page(store = new Map(), { readFails = false, writeFails = false, storageUnavailable = false } = {}) {
    const clicks = [];
    const events = new Map();
    const root = { dataset: {} };
    const context = {
        document: { documentElement: root, addEventListener: (name, fn) => {
            if (name === 'click') clicks.push(fn);
        } },
        window: { addEventListener: (name, fn) => events.set(name, fn) },
    };
    Object.defineProperty(context, 'localStorage', { get() {
        if (storageUnavailable) throw new Error('SecurityError');
        return {
            getItem(key) { if (readFails) throw new Error('SecurityError'); return store.get(key) ?? null; },
            setItem(key, value) { if (writeFails) throw new Error('QuotaExceededError'); store.set(key, value); },
        };
    } });
    vm.runInNewContext(script, context);
    return {
        root, clicks, events,
        click(toggle = true) { for (const fn of clicks) fn({ target: { closest: () => toggle ? {} : null } }); },
    };
}

test('new and invalid preferences start in system mode without writing storage', () => {
    for (const value of [null, 'invalid']) {
        const store = new Map(value === null ? [] : [['theme', value]]);
        const view = page(store);
        assert.equal(view.root.dataset.theme, 'auto');
        assert.equal(store.get('theme'), value === null ? undefined : value);
    }
});

test('one click handler cycles all modes and persists across navigation/reload', () => {
    const store = new Map();
    const view = page(store);
    assert.equal(view.clicks.length, 1);
    for (const mode of ['light', 'dark', 'auto']) {
        view.click();
        assert.equal(view.root.dataset.theme, mode);
        assert.equal(store.get('theme'), mode);
        assert.equal(page(store).root.dataset.theme, mode);
    }
    view.click(false);
    assert.equal(view.root.dataset.theme, 'auto');
});

test('blocked reads, writes or storage property do not prevent switching', () => {
    for (const options of [{ readFails: true }, { writeFails: true }, { storageUnavailable: true }]) {
        const view = page(new Map(), options);
        assert.equal(view.root.dataset.theme, 'auto');
        for (const mode of ['light', 'dark', 'auto']) {
            assert.doesNotThrow(() => view.click());
            assert.equal(view.root.dataset.theme, mode);
        }
    }
});

test('Django theme storage events update this page without writing back', () => {
    const store = new Map([['theme', 'light']]);
    const view = page(store);
    view.events.get('storage')({ key: 'theme', newValue: 'dark' });
    assert.equal(view.root.dataset.theme, 'dark');
    assert.equal(store.get('theme'), 'light');
    view.events.get('storage')({ key: 'other', newValue: 'auto' });
    assert.equal(view.root.dataset.theme, 'dark');
    view.events.get('storage')({ key: 'theme', newValue: null });
    assert.equal(view.root.dataset.theme, 'auto');
});

function variables(block) {
    return Object.fromEntries([...block.matchAll(/--([a-z-]+):\s*([^;]+);/g)].map(m => [m[1], m[2]]));
}
const light = variables(css.match(/:root, html\[data-theme="light"\] \{([^}]+)\}/)[1]);
const dark = variables(css.match(/html\[data-theme="dark"\] \{([^}]+)\}/)[1]);

test('system dark palette matches manual dark and excludes both manual modes', () => {
    const media = css.match(/@media \(prefers-color-scheme: dark\) \{([\s\S]*?)\n\}/)[1];
    assert.match(media, /:root:not\(\[data-theme="light"\]\):not\(\[data-theme="dark"\]\)/);
    assert.deepEqual(variables(media), dark);
    assert.match(media, /color-scheme: dark/);
});

function luminance(hex) {
    const full = hex.length === 4 ? '#' + [...hex.slice(1)].map(c => c + c).join('') : hex;
    const rgb = [1, 3, 5].map(i => parseInt(full.slice(i, i + 2), 16) / 255)
        .map(c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}
function color(palette, key) {
    const value = palette[key];
    const reference = value.match(/^var\(--([a-z-]+)\)$/);
    return reference ? color(palette, reference[1]) : value;
}
function contrast(a, b) {
    const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (values[0] + 0.05) / (values[1] + 0.05);
}

test('normal text, secondary text, links, errors and buttons meet 4.5:1 in both palettes', () => {
    for (const [mode, palette] of [['light', light], ['dark', { ...light, ...dark }]]) {
        for (const bg of ['body-bg', 'pv-panel', 'darkened-bg', 'selected-bg', 'selected-row']) {
            for (const fg of ['body-fg', 'body-quiet-color', 'body-medium-color', 'body-loud-color', 'link-fg', 'error-fg']) {
                assert.ok(contrast(color(palette, fg), color(palette, bg)) >= 4.5, `${mode} ${fg}/${bg}`);
            }
        }
        for (const bg of ['button-bg', 'button-hover-bg', 'default-button-bg', 'default-button-hover-bg',
                          'close-button-bg', 'close-button-hover-bg', 'delete-button-bg', 'delete-button-hover-bg']) {
            assert.ok(contrast(color(palette, 'button-fg'), color(palette, bg)) >= 4.5, `${mode} button/${bg}`);
        }
    }
    const palette = { ...light, ...dark };
    for (const bg of ['message-debug-bg', 'message-info-bg', 'message-success-bg', 'message-warning-bg', 'message-error-bg']) {
        assert.ok(contrast(color(palette, 'body-fg'), color(palette, bg)) >= 4.5, `dark message/${bg}`);
    }
});
