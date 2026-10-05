import { renderEmojiText, emojiPreview } from './emoji.js';
import { renderUserName } from '../../site/js/user-name.js';

// Server IDs are the only message identity. User markup stays literal text.
export function createMessageList(history, empty) {
    const items = new Map();
    const deleted = new Set();

    function render(node, message) {
        node.replaceChildren();
        node.className = `chat-message${message.is_own ? ' chat-message--own' : ''}`;
        const sender = document.createElement('strong');
        sender.className = 'chat-message__sender';
        renderUserName(sender, message.sender, message.sender_role);
        node.append(sender);
        if (message.reply_to) {
            const quote = document.createElement('div');
            quote.className = 'chat-message__reply';
            const author = document.createElement('strong');
            if (message.reply_to.is_deleted) author.textContent = 'Сообщение удалено';
            else renderUserName(author, message.reply_to.sender, message.reply_to.sender_role);
            const preview = document.createElement('span');
            renderEmojiText(preview, message.reply_to.is_deleted ? '' : emojiPreview(message.reply_to.preview_text ?? message.reply_to.text));
            quote.append(author, preview);
            node.append(quote);
        }
        const text = document.createElement('p');
        text.className = 'chat-message__text';
        renderEmojiText(text, message.text);
        const date = new Date(message.created_at);
        const time = document.createElement('time');
        time.dateTime = message.created_at;
        time.textContent = `${message.edited_at ? 'изменено · ' : ''}${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
        time.title = message.edited_at ? `${date.toLocaleString()} · Изменено ${new Date(message.edited_at).toLocaleString()}` : date.toLocaleString();
        text.append(time);
        node.append(text);
    }

    function regroup() {
        let previous = null;
        for (const node of history.querySelectorAll('[data-message-id]')) {
            const message = items.get(Number(node.dataset.messageId)).data;
            const date = new Date(message.created_at);
            const earlier = previous && new Date(previous.created_at);
            const continued = previous && previous.sender_id === message.sender_id &&
                earlier.toDateString() === date.toDateString() && date - earlier >= 0 && date - earlier < 300000;
            node.classList.toggle('chat-message--continued', Boolean(continued));
            previous = message;
        }
        empty.hidden = items.size > 0;
    }

    function upsert(message) {
        const current = items.get(message.id);
        if (message.is_deleted) { deleted.add(message.id); return remove(message.id); }
        if (deleted.has(message.id)) return false;
        if (current && JSON.stringify(current.data) === JSON.stringify(message)) return false;
        const node = current?.node || document.createElement('article');
        node.dataset.messageId = message.id;
        node.id = `chat-message-${message.id}`;
        node.tabIndex = 0;
        node.setAttribute('aria-haspopup', 'menu');
        items.set(message.id, { data: message, node });
        render(node, message);
        if (!current) {
            const next = [...history.querySelectorAll('[data-message-id]')].find(e => Number(e.dataset.messageId) > message.id);
            history.insertBefore(node, next || null);
        }
        regroup();
        return true;
    }

    function remove(id) {
        const current = items.get(id);
        if (!current) return false;
        current.node.remove();
        items.delete(id);
        regroup();
        return true;
    }

    function updateReplies(target) {
        let changed = false;
        for (const { data } of [...items.values()]) {
            if (data.reply_to?.id !== target.id) continue;
            changed = upsert({ ...data, reply_to: { id: target.id, sender: target.sender,
                sender_role: target.sender_role,
                text: target.is_deleted ? '' : Array.from(target.text).slice(0, 160).join(''),
                preview_text: target.is_deleted ? '' : Array.from(target.text).slice(0, 224).join(''),
                is_deleted: target.is_deleted } }) || changed;
        }
        return changed;
    }

    return { upsert, remove, updateReplies, isDeleted: id => deleted.has(id), get: id => items.get(id)?.data,
        ids: () => [...items.keys()], node: id => items.get(id)?.node };
}
