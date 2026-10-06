import { renderEmojiText, emojiPreview } from './emoji.js';
import { renderUserName } from '../../site/js/user-name.js';
import { messagePreview, configureChatWebm } from './photos.js?v=20261006-stickers';

// Server IDs are the only message identity. User markup stays literal text.
export function createMessageList(history, empty, { openPhoto = () => {} } = {}) {
    const items = new Map();
    const deleted = new Set();

    function render(node, message) {
        node.replaceChildren();
        const attachments = message.attachments?.length ? message.attachments : (message.photo ? [{...message.photo, kind: 'image'}] : []);
        const mediaOnly = attachments.length > 0 && !(message.text || '').trim();
        node.className = `chat-message${message.is_own ? ' chat-message--own' : ''}${mediaOnly ? ' chat-message--media-only' : ''}`;
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
            renderEmojiText(preview, message.reply_to.is_deleted ? '' : emojiPreview(messagePreview({
                ...message.reply_to, text: message.reply_to.preview_text ?? message.reply_to.text })));
            quote.append(author, preview);
            node.append(quote);
        }
        const gallery = document.createElement('div');
        gallery.className = 'chat-attachments';
        for (const [index, attachment] of attachments.entries()) {
            const isVideo = attachment.kind === 'video';
            const photo = document.createElement(isVideo ? 'div' : 'button');
            photo.className = `chat-photo-thumb${isVideo ? ' chat-video-inline' : ''}`;
            if (!isVideo) {
                photo.type = 'button';
                photo.setAttribute('aria-label', `Открыть фотографию${attachments.length > 1 ? ` ${index + 1} из ${attachments.length}` : ''}`);
                photo.addEventListener('click', () => openPhoto(attachment, photo));
            }
            const image = document.createElement(isVideo ? 'video' : 'img');
            if (isVideo) { configureChatWebm(image); image.setAttribute('aria-label', 'Видео WebM в сообщении'); }
            else { image.alt = 'Фотография в сообщении'; image.loading = 'lazy'; image.decoding = 'async'; }
            image.src = attachment.url;
            photo.append(image);
            gallery.append(photo);
        }
        if (attachments.length) node.append(gallery);
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
                is_deleted: target.is_deleted,
                has_photo: !target.is_deleted && Boolean(target.photo),
                attachment_count: target.is_deleted ? 0 : (target.attachments?.length || 0),
                has_video: !target.is_deleted && Boolean(target.attachments?.some(item => item.kind === 'video')) } }) || changed;
        }
        return changed;
    }

    return { upsert, remove, updateReplies, isDeleted: id => deleted.has(id), get: id => items.get(id)?.data,
        ids: () => [...items.keys()], node: id => items.get(id)?.node };
}
