// Colors are user data. Only opaque, six-digit HEX leaves this module.
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

export function normalizeHex(value) {
    if (typeof value !== 'string') return null;
    const match = /^#?([\da-f]{6})$/i.exec(value.trim());
    return match ? `#${match[1].toLowerCase()}` : null;
}

export function hexToHSV(value, previousHue = 0, previousSaturation = 0) {
    const hex = normalizeHex(value);
    if (!hex) throw new TypeError('Expected an opaque #RRGGBB color');
    const [r, g, b] = [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255);
    const max = Math.max(r, g, b), delta = max - Math.min(r, g, b);
    let h = previousHue;
    if (delta) {
        h = max === r ? ((g - b) / delta) % 6 : max === g ? (b - r) / delta + 2 : (r - g) / delta + 4;
        h = (h * 60 + 360) % 360;
    }
    // Retain hue for grays, and saturation for black, so the handles do not jump.
    return {h, s: max ? delta / max : previousSaturation, v: max};
}

export function hsvToHex({h, s, v}) {
    h = ((h % 360) + 360) % 360;
    s = clamp(s, 0, 1);
    v = clamp(v, 0, 1);
    const c = v * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = v - c;
    const rgb = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x]
        : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
    return '#' + rgb.map(channel => Math.round((channel + m) * 255).toString(16).padStart(2, '0')).join('');
}

export class ColorSelection {
    constructor(value) {
        this.hsv = {h: 0, s: 0, v: 0};
        this.sync(value);
    }

    setHex(value) {
        const hex = normalizeHex(value);
        if (!hex) return false;
        this.hsv = hexToHSV(hex, this.hsv.h, this.hsv.s);
        const changed = hex !== this.hex;
        this.hex = hex;
        return changed;
    }

    setHSV(channels) {
        const {h, s, v} = {...this.hsv, ...channels};
        this.hsv = {h: clamp(h, 0, 360), s: clamp(s, 0, 1), v: clamp(v, 0, 1)};
        const hex = hsvToHex(this.hsv), changed = hex !== this.hex;
        this.hex = hex;
        return changed;
    }

    sync(value) {
        this.setHex(value);
        this.committed = this.hex;
    }

    commit() {
        const changed = this.committed !== this.hex;
        this.committed = this.hex;
        return changed;
    }
}
