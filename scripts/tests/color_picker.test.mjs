import assert from 'node:assert/strict';
import {setMaxListeners} from 'node:events';
import test from 'node:test';
import {ColorSelection, hexToHSV, hsvToHex, normalizeHex} from '../../assets/site/js/color-picker-model.js';
import {initColorPickers, syncColorPickers, destroyColorPickers} from '../../assets/site/js/color-picker.js';

test('HEX accepts six digits only and always returns opaque lowercase HEX', () => {
    for (const input of ['#12abEF', '12abEF', '  #12abef\n']) assert.equal(normalizeHex(input), '#12abef');
    for (const input of ['', '#', '#123', '#12345', '#1234567', '#12345678', 'transparent',
        'rgba(0,0,0,1)', '#gggggg', '#12 3456', null, 123456]) assert.equal(normalizeHex(input), null);
});

test('HSV conversion covers primaries, secondaries, grays and a sampled RGB cube', () => {
    for (const [hex, h] of [['#ff0000', 0], ['#ffff00', 60], ['#00ff00', 120],
        ['#00ffff', 180], ['#0000ff', 240], ['#ff00ff', 300]]) {
        assert.deepEqual(hexToHSV(hex), {h, s: 1, v: 1});
        assert.equal(hsvToHex({h, s: 1, v: 1}), hex);
    }
    for (let r = 0; r <= 255; r += 17) for (let g = 0; g <= 255; g += 17) for (let b = 0; b <= 255; b += 17) {
        const hex = '#' + [r, g, b].map(c => c.toString(16).padStart(2, '0')).join('');
        assert.equal(hsvToHex(hexToHSV(hex)), hex);
    }
    assert.equal(hsvToHex({h: 360, s: 1, v: 1}), '#ff0000');
    assert.equal(hsvToHex({h: -120, s: 2, v: 2}), '#0000ff');
});

test('gray/black retain useful hue state and invalid drafts never alter the selection', () => {
    const selection = new ColorSelection('#0000ff');
    selection.setHex('#808080');
    assert.equal(selection.hsv.h, 240);
    selection.setHSV({s: 1, v: 0});
    selection.setHex('#000000');
    assert.deepEqual(selection.hsv, {h: 240, s: 1, v: 0});
    assert.equal(selection.setHex('#bad'), false);
    assert.equal(selection.hex, '#000000');
    selection.setHSV({v: 1});
    assert.equal(selection.hex, '#0000ff');
    assert.equal(selection.commit(), false); // Returned to the committed color.
});

// Minimal DOM double for event/value lifecycle tests. Real layout, focus, native
// dialog and pointer behavior are checked separately in the browser.
class Node extends EventTarget {
    constructor(document, tag = '') {
        super();
        this.ownerDocument = document;
        this.tagName = tag.toUpperCase();
        this.children = [];
        this.attributes = new Map();
        this.style = {};
        this.className = '';
        this.classList = {
            add: name => { this.className += ` ${name}`; },
            remove: name => { this.className = this.className.split(' ').filter(item => item !== name).join(' '); },
        };
    }
    addEventListener(type, listener, options) {
        if (options?.signal) setMaxListeners(0, options.signal);
        super.addEventListener(type, listener, options);
    }
    append(...nodes) { for (const node of nodes) { node.remove(); node.parentNode = this; this.children.push(node); } }
    after(node) {
        node.remove(); node.parentNode = this.parentNode;
        this.parentNode.children.splice(this.parentNode.children.indexOf(this) + 1, 0, node);
    }
    remove() {
        if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(node => node !== this);
        this.parentNode = null;
    }
    get isConnected() { return this === this.ownerDocument?.body || Boolean(this.parentNode?.isConnected); }
    setAttribute(name, value) { this.attributes.set(name, String(value)); }
    getAttribute(name) { return this.attributes.get(name) ?? null; }
    removeAttribute(name) { this.attributes.delete(name); }
    contains(node) { return node === this || this.children.some(child => child.contains(node)); }
    matches(selector) {
        if (selector === 'input[type="color"]') return this.tagName === 'INPUT' && this.type === 'color';
        if (selector === ':disabled') return Boolean(this.disabled || this.closest('fieldset')?.disabled);
        return selector.split(',').some(tag => tag.trim().toUpperCase() === this.tagName);
    }
    closest(selector) { return this.matches(selector) ? this : this.parentNode?.closest(selector) ?? null; }
    querySelectorAll(selector) { return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]); }
    focus() { this.ownerDocument.activeElement = this; }
    getBoundingClientRect() { return this.rect || {left: 100, right: 372, top: 100, bottom: 138, width: 272, height: 330}; }
    showPopover() { this.shown = true; }
    hidePopover() { this.shown = false; }
    setPointerCapture(id) { this.capture = id; }
    hasPointerCapture(id) { return this.capture === id; }
    releasePointerCapture() { this.capture = undefined; }
}
class Input extends Node {
    get value() { return this._value || '#000000'; }
    set value(value) { this._value = this.type === 'color' ? /^#[\da-f]{6}$/i.test(value) ? value.toLowerCase() : '#000000' : String(value); }
}
function page({supported = true} = {}) {
    const document = new Node(null);
    document.defaultView = new Node(document);
    Object.assign(document.defaultView, {
        HTMLInputElement: Input, HTMLElement: supported ? Node : class {}, PointerEvent: Event, Event,
        MutationObserver: class { observe() {} disconnect() { this.disconnected = true; } },
        innerHeight: 800,
    });
    document.documentElement = {clientWidth: 1000};
    document.body = new Node(document, 'body');
    document.createElement = tag => tag === 'input' ? new Input(document, tag) : new Node(document, tag);
    document.querySelectorAll = selector => document.body.querySelectorAll(selector);
    const dialog = new Node(document, 'dialog'), form = new Node(document, 'form');
    document.body.append(dialog); dialog.append(form);
    const inputs = ['#123456', '#abcdef'].map((value, index) => {
        const input = new Input(document, 'input');
        input.type = 'color'; input.value = value; input.hidden = false;
        input.id = `original-${index}`; input.name = `color-${index}`; input.form = form;
        const label = new Node(document, 'label'); label.textContent = `Цвет ${index}`;
        input.labels = [label]; form.append(label, input);
        return input;
    });
    return {document, form, dialog, inputs};
}
const fire = (node, type, details = {}) => {
    const event = new Event(type, {cancelable: true});
    Object.assign(event, details);
    node.dispatchEvent(event);
    return event;
};

test('enhancement is idempotent, instances are independent, original form fields survive', () => {
    const p = page(), first = initColorPickers(p.document);
    assert.deepEqual(initColorPickers(p.document), first);
    assert.equal(p.form.querySelectorAll('button').length, 2);
    for (const [i, input] of p.inputs.entries()) {
        assert.equal(input.id, `original-${i}`); assert.equal(input.name, `color-${i}`);
        assert.equal(input.form, p.form); assert.equal(input.type, 'color');
        assert.equal(input.hidden, true); assert.equal(first[i].trigger.type, 'button');
    }
    p.inputs[0].value = '#998877';
    assert.equal(first[0].value.textContent, '#998877');
    assert.equal(first[1].value.textContent, '#ABCDEF');
    destroyColorPickers(p.document);
    assert.equal(p.inputs[0].hidden, false);
    assert.equal(Object.hasOwn(p.inputs[0], 'value'), false);
    assert.equal(p.form.querySelectorAll('button').length, 0);
    assert.notEqual(initColorPickers(p.inputs[0])[0], first[0]);
    destroyColorPickers(p.document);
});

test('valid HEX previews match the form, invalid/alpha drafts do not emit, change is deduplicated', () => {
    const p = page(), [picker] = initColorPickers(p.document), events = [];
    for (const type of ['input', 'change']) p.inputs[0].addEventListener(type, event => events.push([event.type, event.target.value]));
    picker.hex.value = '#ABC123'; fire(picker.hex, 'input');
    assert.equal(p.inputs[0].value, '#abc123');
    assert.equal(picker.preview.style.backgroundColor, '#abc123');
    assert.match(picker.trigger.getAttribute('aria-label'), /#abc123/);
    for (const value of ['#', '#123', '#abcd1234', 'rgba(1,2,3,1)']) {
        picker.hex.value = value; fire(picker.hex, 'input');
        assert.equal(p.inputs[0].value, '#abc123');
        assert.equal(picker.hex.getAttribute('aria-invalid'), 'true');
    }
    assert.equal(fire(picker.hex, 'keydown', {key: 'Enter'}).defaultPrevented, true);
    fire(picker.hex, 'change'); fire(picker.hex, 'blur');
    assert.deepEqual(events, [['input', '#abc123'], ['change', '#abc123']]);
    destroyColorPickers(p.document);
});

test('drag emits only changed input values and one change, including pointer cancellation', () => {
    const p = page(), [picker] = initColorPickers(p.document), events = [];
    for (const type of ['input', 'change']) p.inputs[0].addEventListener(type, event => events.push(event.type));
    picker.sv.rect = {left: 0, top: 0, width: 100, height: 100};
    const pointer = {button: 0, isPrimary: true, pointerType: 'touch', pointerId: 7, clientX: 40, clientY: 20};
    fire(picker.sv, 'pointerdown', pointer);
    fire(picker.sv, 'pointermove', pointer);
    fire(picker.sv, 'pointermove', {...pointer, clientX: 60});
    assert.deepEqual(events, ['input', 'input']);
    fire(picker.sv, 'pointercancel', pointer); fire(picker.sv, 'lostpointercapture', pointer);
    assert.deepEqual(events, ['input', 'input', 'change']);
    assert.equal(picker.preview.style.backgroundColor, p.inputs[0].value);
    assert.equal(picker.drag, undefined);
    destroyColorPickers(p.document);
});

test('programmatic values and reset synchronize silently; keyboard edits commit once', async () => {
    const p = page(), [picker] = initColorPickers(p.document), events = [];
    for (const type of ['input', 'change']) p.inputs[0].addEventListener(type, event => events.push(event.type));
    p.inputs[0].value = '#778899'; syncColorPickers(p.document);
    assert.equal(picker.hex.value, '#778899'); assert.deepEqual(events, []);
    fire(p.form, 'reset');
    // A browser can perform a microtask checkpoint before Reset's default action.
    await Promise.resolve();
    Object.getOwnPropertyDescriptor(Input.prototype, 'value').set.call(p.inputs[0], '#123456');
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(picker.hex.value, '#123456'); assert.deepEqual(events, []);
    fire(picker.sv, 'keydown', {key: 'ArrowRight', shiftKey: true});
    fire(picker.sv, 'keydown', {key: 'ArrowUp'});
    fire(picker.sv, 'keyup'); fire(picker.sv, 'blur');
    assert.deepEqual(events, ['input', 'input', 'change']);
    p.inputs[0].disabled = true; picker.sync(); assert.equal(picker.trigger.disabled, true);
    destroyColorPickers(p.document);
});

test('one popover opens inside its parent dialog; Escape consumes the key and restores focus', () => {
    const p = page(), [first, second] = initColorPickers(p.document);
    first.open(); assert.equal(first.panel.parentNode, p.dialog);
    second.open(); assert.equal(first.panel.shown, false); assert.equal(second.panel.shown, true);
    const event = fire(p.document, 'keydown', {key: 'Escape'});
    assert.equal(event.defaultPrevented, true);
    assert.equal(second.panel.shown, false); assert.equal(p.document.activeElement, second.trigger);
    assert.equal(second.trigger.getAttribute('aria-expanded'), 'false');
    first.open(); fire(p.document, 'pointerdown');
    assert.equal(first.panel.shown, false); assert.equal(p.document.activeElement, first.trigger);
    first.open(); first.hex.focus();
    assert.equal(fire(first.panel, 'keydown', {key: 'Tab', shiftKey: false}).defaultPrevented, true);
    assert.equal(first.panel.shown, false); assert.equal(p.document.activeElement, first.trigger);
    destroyColorPickers(p.document);
});

test('missing browser APIs preserve the native input fallback', () => {
    const p = page({supported: false});
    assert.deepEqual(initColorPickers(p.document), []);
    assert.equal(p.inputs[0].hidden, false);
    assert.equal(Object.hasOwn(p.inputs[0], 'value'), false);
});
