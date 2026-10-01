import { appleEmojiIds } from '../emoji/apple/index.js';

const base = new URL('../emoji/apple/', import.meta.url);
const graphemes = typeof Intl.Segmenter === 'function'
    ? new Intl.Segmenter('und', { granularity: 'grapheme' }) : null;
// Only FE0F (emoji presentation) is optional. Preserve ZWJ, modifiers, flags,
// tags and keycaps. FE0E explicitly requests text and never matches an asset.
const normalize = id => id.split('-').filter(point => point !== 'fe0f').join('-');
const available = new Map(appleEmojiIds.map(id => [normalize(id), id]));

export function emojiPreview(text, limit = 160) {
    // Older engines keep original text rather than cutting a Unicode sequence.
    // API previews and messages remain bounded by the existing server contract.
    if (!graphemes) return text;
    let end = 0, count = 0;
    for (const { segment, index } of graphemes.segment(text)) {
        count += Array.from(segment).length;
        if (count > limit) break;
        end = index + segment.length;
    }
    return text.slice(0, end);
}

// Match whole graphemes so unknown compound emoji cannot become partial images.
// User text never passes through an HTML API; image alt retains its Unicode.
export function renderEmojiText(element, text) {
    if (!graphemes) { element.textContent = text; return; }
    const fragment = document.createDocumentFragment();
    let literal = '';
    for (const { segment } of graphemes.segment(text)) {
        const id = Array.from(segment, point => point.codePointAt(0).toString(16)).join('-');
        const asset = available.get(normalize(id));
        if (!asset) { literal += segment; continue; }
        if (literal) { fragment.append(document.createTextNode(literal)); literal = ''; }
        const image = document.createElement('img');
        image.className = 'chat-emoji';
        image.alt = segment;
        image.width = image.height = 144;
        image.draggable = false;
        image.decoding = 'async';
        image.loading = 'lazy';
        image.addEventListener('error', () => {
            image.replaceWith(document.createTextNode(segment));
        }, { once: true });
        image.src = new URL(`${asset}.png`, base).href;
        fragment.append(image);
    }
    if (literal) fragment.append(document.createTextNode(literal));
    element.replaceChildren(fragment);
}
