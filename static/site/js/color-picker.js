import {ColorSelection, hsvToHex, normalizeHex} from './color-picker-model.js';

const instances = new WeakMap();
let active = null, nextId = 0;
const selector = 'input[type="color"]';

function element(document, tag, className, text) {
    const node = document.createElement(tag);
    node.className = className;
    if (text) node.textContent = text;
    return node;
}

class ColorPicker {
    constructor(input) {
        this.input = input;
        this.document = input.ownerDocument;
        this.window = this.document.defaultView;
        this.selection = new ColorSelection(input.value);
        this.listeners = new AbortController();
        this.original = {hidden: input.hidden, tabIndex: input.getAttribute('tabindex'), ariaHidden: input.getAttribute('aria-hidden')};
        const id = `site-color-picker-${++nextId}`;
        const make = (tag, name, text) => element(this.document, tag, `color-picker__${name}`, text);
        this.wrapper = make('span', 'control');
        this.trigger = make('button', 'trigger');
        this.trigger.type = 'button';
        this.trigger.autofocus = input.autofocus;
        this.trigger.setAttribute('aria-haspopup', 'dialog');
        this.trigger.setAttribute('aria-controls', id);
        this.trigger.setAttribute('aria-expanded', 'false');
        this.swatch = make('span', 'swatch');
        this.swatch.setAttribute('aria-hidden', 'true');
        this.value = make('span', 'value');
        this.trigger.append(this.swatch, this.value);
        this.wrapper.append(this.trigger);

        this.panel = make('div', 'panel');
        this.panel.id = id;
        this.panel.setAttribute('popover', 'manual');
        this.panel.setAttribute('role', 'dialog');
        this.panel.setAttribute('aria-labelledby', `${id}-title`);
        this.title = make('div', 'title');
        this.title.id = `${id}-title`;
        this.sv = make('div', 'sv');
        this.sv.tabIndex = 0;
        this.sv.setAttribute('role', 'slider');
        this.sv.setAttribute('aria-label', 'Насыщенность и яркость');
        this.sv.setAttribute('aria-valuemin', '0');
        this.sv.setAttribute('aria-valuemax', '100');
        this.sv.setAttribute('aria-describedby', `${id}-hint`);
        this.cursor = make('span', 'cursor');
        this.cursor.setAttribute('aria-hidden', 'true');
        this.sv.append(this.cursor);
        this.hueLabel = make('label', 'hue-label', 'Оттенок');
        this.hue = make('input', 'hue');
        this.hue.type = 'range';
        this.hue.min = '0';
        this.hue.max = '360';
        this.hue.step = '1';
        this.hue.id = `${id}-hue`;
        this.hueLabel.htmlFor = this.hue.id;
        const row = make('div', 'hex-row');
        this.preview = make('span', 'preview');
        this.preview.setAttribute('aria-hidden', 'true');
        const hexLabel = make('label', 'hex-label', 'HEX');
        this.hex = make('input', 'hex');
        this.hex.type = 'text';
        this.hex.id = `${id}-hex`;
        this.hex.autocomplete = 'off';
        this.hex.spellcheck = false;
        this.hex.setAttribute('autocapitalize', 'off');
        this.hex.setAttribute('aria-describedby', `${id}-error`);
        hexLabel.htmlFor = this.hex.id;
        row.append(this.preview, hexLabel, this.hex);
        this.error = make('div', 'error');
        this.error.id = `${id}-error`;
        this.error.setAttribute('aria-live', 'polite');
        this.error.hidden = true;
        const hint = make('div', 'hint', '← → насыщенность · ↑ ↓ яркость');
        hint.id = `${id}-hint`;
        this.panel.append(this.title, this.sv, this.hueLabel, this.hue, row, this.error, hint);

        const on = (target, type, listener, options = {}) => target.addEventListener(type, listener,
            {...options, signal: this.listeners.signal});
        on(this.trigger, 'click', () => active === this ? this.close() : this.open());
        for (const label of input.labels || []) {
            on(label, 'click', event => {
                if (event.target.closest('button, a, input, select, textarea')) return;
                event.preventDefault();
                this.open();
            });
        }
        on(input, 'input', () => { if (!this.emitting) this.sync(); });
        on(input, 'change', () => { if (!this.emitting) this.sync(); });
        if (input.form) on(input.form, 'reset', () => {
            // A microtask can run before the native reset's default action when
            // Reset was clicked. Read the final native values in the next task.
            clearTimeout(this.resetTimer);
            this.resetTimer = setTimeout(() => { if (!this.destroyed) this.sync(); }, 0);
        });
        on(this.sv, 'pointerdown', event => this.startDrag(event));
        on(this.sv, 'pointermove', event => {
            if (this.drag === event.pointerId) this.move(event);
        });
        for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
            on(this.sv, type, event => { if (this.drag === event.pointerId) this.endDrag(); });
        }
        on(this.sv, 'keydown', event => this.keyColor(event));
        on(this.sv, 'keyup', () => this.commit());
        on(this.sv, 'blur', () => this.commit());
        on(this.hue, 'input', () => this.chooseHSV({h: Number(this.hue.value)}));
        on(this.hue, 'change', () => this.commit());
        on(this.hue, 'pointercancel', () => this.commit());
        on(this.hue, 'blur', () => this.commit());
        on(this.hex, 'input', () => {
            const value = normalizeHex(this.hex.value);
            this.setError(!value);
            if (value) this.publish(this.selection.setHex(value), {keepDraft: true});
        });
        on(this.hex, 'change', () => this.commit());
        on(this.hex, 'blur', () => {
            this.commit();
            if (normalizeHex(this.hex.value)) this.render();
        });
        on(this.hex, 'keydown', event => {
            if (event.key !== 'Enter') return;
            event.preventDefault(); // Never submit the owning form from the HEX editor.
            this.setError(!normalizeHex(this.hex.value));
            this.commit();
        });
        on(this.panel, 'keydown', event => {
            if (event.key !== 'Tab') return;
            const focus = this.document.activeElement;
            if ((!event.shiftKey && focus === this.hex) || (event.shiftKey && focus === this.sv)) {
                event.preventDefault();
                this.close();
            }
        });

        // Existing code assigns .value when opening habit/group dialogs and when
        // scheduled themes switch. Forward the native setter without firing events.
        this.valueDescriptor = Object.getOwnPropertyDescriptor(this.window.HTMLInputElement.prototype, 'value');
        this.ownsValue = !Object.hasOwn(input, 'value');
        if (this.ownsValue) Object.defineProperty(input, 'value', {
            configurable: true,
            get: () => this.valueDescriptor.get.call(input),
            set: value => {
                this.valueDescriptor.set.call(input, value);
                if (!this.writing && !this.destroyed) this.sync();
            },
        });
        this.observer = new this.window.MutationObserver(() => this.sync());
        this.observer.observe(input, {attributes: true, attributeFilter:
            ['disabled', 'readonly', 'value', 'aria-label', 'aria-labelledby', 'title']});
        const fieldset = input.closest('fieldset');
        if (fieldset) this.observer.observe(fieldset, {attributes: true, attributeFilter: ['disabled']});
        input.after(this.wrapper);
        input.hidden = true;
        input.classList.add('color-picker__source');
        input.tabIndex = -1;
        input.setAttribute('aria-hidden', 'true');
        this.sync();
    }

    label() {
        const labelledBy = this.input.getAttribute('aria-labelledby');
        const text = labelledBy?.split(/\s+/).map(id => this.document.getElementById(id)?.textContent || '').join(' ');
        return (text || this.input.getAttribute('aria-label') ||
            [...(this.input.labels || [])].map(label => label.textContent).join(' ') ||
            this.input.title || this.input.name || 'Цвет').trim().replace(/[:：]\s*$/, '');
    }

    sync() {
        this.selection.sync(this.input.value);
        this.trigger.disabled = this.input.matches(':disabled') || this.input.readOnly;
        this.title.textContent = this.label();
        this.setError(false);
        this.render();
        if (active === this && this.trigger.disabled) this.close();
    }

    render({keepDraft = false} = {}) {
        const {hex, hsv} = this.selection;
        this.swatch.style.backgroundColor = hex;
        this.preview.style.backgroundColor = hex;
        this.value.textContent = hex.toUpperCase();
        this.trigger.setAttribute('aria-label', `${this.label()}: ${hex}. Выбрать цвет`);
        if (!keepDraft) this.hex.value = hex.toUpperCase();
        this.hue.value = String(hsv.h);
        this.sv.style.backgroundColor = hsvToHex({h: hsv.h, s: 1, v: 1});
        this.cursor.style.left = `${hsv.s * 100}%`;
        this.cursor.style.top = `${(1 - hsv.v) * 100}%`;
        const s = Math.round(hsv.s * 100), v = Math.round(hsv.v * 100);
        this.sv.setAttribute('aria-valuenow', String(s));
        this.sv.setAttribute('aria-valuetext', `Насыщенность ${s}%, яркость ${v}%`);
    }

    setError(invalid) {
        this.hex.setAttribute('aria-invalid', String(invalid));
        this.error.textContent = invalid ? 'Введите 6 HEX-цифр, например #3A7BC2.' : '';
        this.error.hidden = !invalid;
        if (active === this) this.place();
    }

    emit(type) {
        this.emitting = true;
        try { this.input.dispatchEvent(new this.window.Event(type, {bubbles: true})); }
        finally { this.emitting = false; }
    }

    publish(changed, options) {
        this.writing = true;
        try { this.input.value = this.selection.hex; }
        finally { this.writing = false; }
        this.render(options);
        if (changed) this.emit('input');
    }

    chooseHSV(channels) {
        this.setError(false);
        this.publish(this.selection.setHSV(channels));
    }

    commit() {
        if (this.selection.commit()) this.emit('change');
    }

    move(event) {
        const rect = this.sv.getBoundingClientRect();
        if (rect.width && rect.height) this.chooseHSV({
            s: (event.clientX - rect.left) / rect.width,
            v: 1 - (event.clientY - rect.top) / rect.height,
        });
    }

    startDrag(event) {
        if (event.button !== 0 || !event.isPrimary || this.drag !== undefined) return;
        event.preventDefault();
        this.sv.focus({preventScroll: true});
        this.drag = event.pointerId;
        this.sv.setPointerCapture(event.pointerId);
        this.move(event);
    }

    endDrag() {
        const id = this.drag;
        this.drag = undefined;
        if (id !== undefined && this.sv.hasPointerCapture(id)) this.sv.releasePointerCapture(id);
        this.commit(); // Cancellation keeps the last previewed color, with one change.
    }

    keyColor(event) {
        const step = event.shiftKey ? 0.1 : 0.01;
        const {s, v} = this.selection.hsv;
        const channels = {ArrowLeft: {s: s - step}, ArrowRight: {s: s + step},
            ArrowDown: {v: v - step}, ArrowUp: {v: v + step},
            Home: {s: 0}, End: {s: 1}, PageDown: {v: 0}, PageUp: {v: 1}}[event.key];
        if (!channels) return;
        event.preventDefault();
        this.chooseHSV(channels);
    }

    place() {
        const viewport = this.window.visualViewport;
        const left = viewport?.offsetLeft || 0, top = viewport?.offsetTop || 0;
        const width = viewport?.width || this.document.documentElement.clientWidth;
        const height = viewport?.height || this.window.innerHeight;
        const anchor = this.trigger.getBoundingClientRect();
        this.panel.style.maxWidth = `${Math.max(0, width - 24)}px`;
        this.panel.style.maxHeight = `${Math.max(0, height - 24)}px`;
        const rect = this.panel.getBoundingClientRect();
        const x = Math.max(left + 12, Math.min(anchor.right - rect.width, left + width - rect.width - 12));
        const below = anchor.bottom + 8;
        const y = below + rect.height <= top + height - 12 ? below : anchor.top - rect.height - 8;
        this.panel.style.left = `${x}px`;
        this.panel.style.top = `${Math.max(top + 12, Math.min(y, top + height - rect.height - 12))}px`;
    }

    open() {
        this.sync();
        if (this.trigger.disabled || !this.input.isConnected || active === this) return;
        active?.close(false);
        this.dialog = this.input.closest('dialog');
        (this.dialog || this.document.body).append(this.panel);
        this.panel.showPopover(); // Top layer escapes overflow and stays above the owning dialog.
        active = this;
        this.trigger.setAttribute('aria-expanded', 'true');
        this.place();
        this.sv.focus({preventScroll: true});
        this.openListeners = new AbortController();
        const on = (target, type, fn, options = {}) => target?.addEventListener(type, fn,
            {...options, signal: this.openListeners.signal});
        on(this.document, 'keydown', event => {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            event.stopImmediatePropagation();
            this.close();
        }, {capture: true});
        on(this.document, 'pointerdown', event => {
            // Restore focus for a click on empty space. A focusable click target
            // receives focus normally in the pointer event's default action.
            if (!this.panel.contains(event.target) && !this.wrapper.contains(event.target)) this.close();
        }, {capture: true});
        on(this.document, 'focusin', event => {
            if (!this.panel.contains(event.target) && !this.wrapper.contains(event.target)) this.close(false);
        });
        on(this.document, 'scroll', () => this.place(), {capture: true, passive: true});
        on(this.window, 'resize', () => this.place());
        on(this.window.visualViewport, 'resize', () => this.place());
        on(this.window.visualViewport, 'scroll', () => this.place());
        on(this.dialog, 'close', () => this.close(false));
        on(this.dialog, 'cancel', event => {
            event.preventDefault();
            event.stopImmediatePropagation();
            this.close();
        }, {capture: true});
    }

    close(restoreFocus = true) {
        if (active !== this) return;
        this.endDrag();
        this.commit();
        this.openListeners.abort();
        active = null;
        this.panel.hidePopover();
        this.panel.remove();
        this.trigger.setAttribute('aria-expanded', 'false');
        this.setError(false);
        this.render();
        if (restoreFocus && this.trigger.isConnected && !this.trigger.disabled) this.trigger.focus({preventScroll: true});
    }

    destroy() {
        this.close(false);
        this.destroyed = true;
        clearTimeout(this.resetTimer);
        this.listeners.abort();
        this.observer.disconnect();
        if (this.ownsValue) delete this.input.value;
        this.input.hidden = this.original.hidden;
        this.input.classList.remove('color-picker__source');
        for (const [name, value] of [['tabindex', this.original.tabIndex], ['aria-hidden', this.original.ariaHidden]]) {
            if (value === null) this.input.removeAttribute(name);
            else this.input.setAttribute(name, value);
        }
        this.wrapper.remove();
        this.panel.remove();
        instances.delete(this.input);
    }
}

function inputs(root) {
    return [...(root.matches?.(selector) ? [root] : []), ...root.querySelectorAll(selector)];
}

export function initColorPickers(root = document) {
    // Leave the native control intact when the required browser APIs are absent.
    const view = (root.ownerDocument || root).defaultView;
    if (!view.HTMLElement.prototype.showPopover || !view.PointerEvent) return [];
    return inputs(root).map(input => {
        if (!instances.has(input)) instances.set(input, new ColorPicker(input));
        return instances.get(input);
    });
}

export function syncColorPickers(root = document) {
    for (const input of inputs(root)) instances.get(input)?.sync();
}

export function destroyColorPickers(root = document) {
    for (const input of inputs(root)) instances.get(input)?.destroy();
}
