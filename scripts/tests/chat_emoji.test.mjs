// Run: node --test scripts/tests/chat_emoji.test.mjs
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import test from 'node:test';
import { renderEmojiText, emojiPreview } from '../../chat/static/chat/js/emoji.js';

// Minimal DOM double: deliberately has no HTML-parsing API.
class Node {
    constructor(type, text = '') { this.type = type; this.text = text; this.children = []; }
    append(node) { node.parent = this; this.children.push(node); }
    replaceChildren(fragment) { this.children = fragment.children; this.children.forEach(n => n.parent = this); }
    addEventListener(type, listener) { this[type] = listener; }
    replaceWith(node) { this.parent.children.splice(this.parent.children.indexOf(this), 1, node); }
}
globalThis.document = {
    createDocumentFragment: () => new Node('fragment'),
    createTextNode: text => new Node('text', text),
    createElement: type => new Node(type),
};
const examples = ['😀', '😂', '❤️', '❤️‍🔥', '👍', '👍🏻', '👍🏿', '👩‍💻',
    '👨‍👩‍👧‍👦', '🇺🇦', '🇳🇱', '🏳️‍🌈', '1️⃣', '🔥', '🥰', '🏃🏽‍♀️'];
const render = text => { const node = new Node('div'); renderEmojiText(node, text); return node; };
const textOf = node => node.children.map(n => n.type === 'img' ? n.alt : n.text).join('');
const images = node => node.children.filter(n => n.type === 'img');

test('whole complex sequences resolve to one existing local PNG', () => {
    for (const emoji of examples) {
        const node = render(emoji);
        assert.equal(images(node).length, 1, emoji);
        assert.equal(textOf(node), emoji);
        const image = images(node)[0];
        assert.ok(image.src.includes('/chat/emoji/apple/'));
        assert.ok(existsSync(new URL(image.src)), emoji);
        assert.equal(image.loading, 'lazy');
        assert.equal(image.draggable, false);
    }
});

test('adjacent emoji and hostile markup preserve exact Unicode as text/alt', () => {
    const original = '😀Привет <img src=x onerror=alert(1)> ❤️‍🔥😂😂👍🏿 end🥰';
    const node = render(original);
    assert.equal(images(node).length, 6);
    assert.equal(textOf(node), original);
    assert.ok(node.children.some(n => n.type === 'text' && n.text.includes('<img')));
    assert.ok(node.children.every(n => ['text', 'img'].includes(n.type)));
});

test('optional FE0F aliases, text presentation, unknown compounds and tag flags', () => {
    for (const [qualified, unqualified] of [['❤️', '❤'], ['1️⃣', '1⃣'], ['❤️‍🔥', '❤‍🔥']]) {
        assert.equal(images(render(qualified))[0].src, images(render(unqualified))[0].src);
    }
    for (const original of ['❤︎', '😀‍🔥', '🇦🇦', 'a\u0301']) {
        assert.equal(images(render(original)).length, 0, original);
        assert.equal(textOf(render(original)), original);
    }
    const england = '\u{1f3f4}\u{e0067}\u{e0062}\u{e0065}\u{e006e}\u{e0067}\u{e007f}';
    assert.equal(images(render(england)).length, 1);
});

test('reply cutoff never splits a grapheme, including unknown sequences', () => {
    for (const emoji of [...examples, '😀‍🔥', 'a\u0301']) {
        const original = 'x'.repeat(159) + emoji + ' tail';
        const preview = emojiPreview(original);
        const expected = Array.from(emoji).length === 1 ? 'x'.repeat(159) + emoji : 'x'.repeat(159);
        assert.equal(preview, expected, emoji);
    }
    assert.equal(emojiPreview('x'.repeat(158) + '👍🏻tail'), 'x'.repeat(158) + '👍🏻');
});

test('failed image becomes original Unicode, without a broken image', () => {
    const node = render('before 👩‍💻 after');
    images(node)[0].error();
    assert.equal(images(node).length, 0);
    assert.equal(textOf(node), 'before 👩‍💻 after');
});

test('older engines degrade to intact native Unicode without breaking chat', async () => {
    const saved = Intl.Segmenter;
    try {
        Intl.Segmenter = undefined;
        const legacy = await import('../../chat/static/chat/js/emoji.js?legacy-test');
        const node = new Node('div');
        const original = '👨‍👩‍👧‍👦 <script>text</script>';
        legacy.renderEmojiText(node, original);
        assert.equal(node.textContent, original);
        assert.equal(legacy.emojiPreview(original, 1), original);
    } finally { Intl.Segmenter = saved; }
});
