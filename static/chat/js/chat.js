import { getCSRFToken } from '../../site/js/csrf.js';
import { createChatWindow } from './window.js';
import { createMessageList } from './messages.js';
import { createMessageActions } from './actions.js';
import { renderEmojiText } from './emoji.js';

const dialog = document.getElementById('chatDialog');
const button = document.getElementById('buttonChat');

if (dialog && button) {
    const chatWindow = createChatWindow(dialog, button);
    const history = document.getElementById('chatMessages');
    const empty = document.getElementById('chatEmpty');
    const composer = document.getElementById('chatComposer');
    const input = document.getElementById('chatText');
    const send = document.getElementById('chatSend');
    const error = document.getElementById('chatError');
    const dot = document.getElementById('chatUnreadDot');
    const emojiToggle = document.getElementById('chatEmojiToggle');
    const picker = document.getElementById('chatEmojiPicker');
    let cursor = null;
    let timer;
    let loading = false;
    let sending = false;
    let expired = false;
    let pollError = false;
    const list = createMessageList(history, empty);
    let refreshOffset = 0;
    const actions = createMessageActions({ dialog, history, input, send, list, request, showError,
        resizeInput, onMutation: applyMessage });

    function resizeInput() {
        // CSS caps the height; longer drafts scroll inside the textarea.
        input.style.height = 'auto';
        input.style.height = `${input.scrollHeight}px`;
    }

    function showError(message = '') {
        error.textContent = message;
        error.hidden = !message;
    }

    function unread(value) {
        dot.hidden = !value;
        button.setAttribute('aria-label', value ? 'Чат: есть новые сообщения' : 'Чат');
    }

    async function request(url, payload, method = 'POST') {
        const options = { credentials: 'same-origin', cache: 'no-store' };
        if (payload !== undefined) {
            options.method = method;
            options.headers = {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken() || composer.querySelector('[name=csrfmiddlewaretoken]').value
            };
            options.body = JSON.stringify(payload);
        }
        const response = await fetch(url, options);
        if (response.status === 401) expired = true;
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            const failure = new Error(data.error || 'Не удалось выполнить запрос. Попробуйте ещё раз.');
            failure.status = response.status;
            throw failure;
        }
        return response.json();
    }

    function applyMessage(message) {
        const current = list.get(message.id);
        // A poll started before a local mutation must not resurrect deleted text
        // or overwrite a newer edit when its response arrives later.
        if (!message.is_deleted && (list.isDeleted(message.id) ||
            (current?.edited_at && (!message.edited_at || current.edited_at > message.edited_at)))) return false;
        if (message.reply_to && list.isDeleted(message.reply_to.id)) {
            message = { ...message, reply_to: { ...message.reply_to, text: '', is_deleted: true } };
        }
        const changed = list.upsert(message);
        const repliesChanged = list.updateReplies(message);
        if (changed) actions.onUpdate(message);
        if (changed || repliesChanged) actions.closeMenu();
        return changed || repliesChanged;
    }

    async function load() {
        const initial = cursor === null;
        const nearBottom = history.scrollHeight - history.scrollTop - history.clientHeight < 60;
        const url = new URL(dialog.dataset.messagesUrl, location.origin);
        if (!initial) url.searchParams.set('after_id', cursor);
        const ids = list.ids();
        if (ids.length) {
            refreshOffset %= ids.length;
            const refresh = ids.slice(refreshOffset, refreshOffset + 50);
            url.searchParams.set('refresh_ids', refresh.join(','));
            refreshOffset = (refreshOffset + refresh.length) % ids.length;
        }
        const data = await request(url);
        for (const message of data.updated_messages || []) applyMessage(message);
        for (const id of data.missing_ids || []) applyMessage({ id, text: '', sender: '', is_deleted: true });
        for (const message of data.messages) {
            if (cursor === null || message.id > cursor) {
                applyMessage(message);
                cursor = message.id;
            }
        }
        if (cursor === null) cursor = 0;
        if (initial || nearBottom) history.scrollTop = history.scrollHeight;
        if (dialog.open && document.visibilityState === 'visible') {
            await request(dialog.dataset.readUrl, { last_read_message_id: cursor });
            if (!data.has_more) unread(false);
        }
        return data.has_more;
    }

    function schedule(delay = dialog.open ? 2500 : 5000) {
        clearTimeout(timer);
        if (!expired && document.visibilityState === 'visible') timer = setTimeout(poll, delay);
    }

    async function poll() {
        if (loading || expired || document.visibilityState !== 'visible') return;
        loading = true;
        let more = false;
        try {
            if (dialog.open) more = await load();
            else unread((await request(dialog.dataset.statusUrl)).has_unread);
            if (pollError && !sending) showError();
            pollError = false;
        } catch (failure) {
            pollError = true;
            showError(failure.message);
        } finally {
            loading = false;
            schedule(more ? 100 : undefined);
        }
    }

    function openChat() {
        chatWindow.open();
        input.focus();
        resizeInput();
        clearTimeout(timer);
        poll();
    }
    button.addEventListener('click', openChat);
    dialog.addEventListener('close', () => {
        // A responsive mode switch closes and immediately reopens the dialog.
        if (dialog.open) return;
        picker.hidden = true;
        emojiToggle.setAttribute('aria-expanded', 'false');
        schedule();
    });
    document.addEventListener('visibilitychange', () => {
        clearTimeout(timer);
        if (document.visibilityState === 'visible') poll();
    });

    composer.addEventListener('submit', async event => {
        event.preventDefault();
        if (sending) return;
        const value = input.value;
        if (!value.trim()) { showError('Введите текст сообщения.'); return; }
        if (value.length > input.maxLength) { showError('Максимум 2000 символов.'); return; }
        const mode = actions.getMode();
        sending = true;
        send.disabled = true;
        input.readOnly = true;
        showError();
        pollError = false;
        try {
            if (mode?.type === 'edit') {
                applyMessage((await request(actions.endpoint(mode.message.id), { text: value }, 'PATCH')).message);
            } else {
                await request(dialog.dataset.messagesUrl, { text: value,
                    ...(mode?.type === 'reply' ? { reply_to: mode.message.id } : {}) });
            }
            actions.resetMode(false);
            input.value = '';
            resizeInput();
            // Read in ID order; appending the POST response could skip other senders.
            clearTimeout(timer);
            schedule(0);
        } catch (failure) {
            if (failure.status === 404) actions.resetMode(false);
            showError(failure.message);
        } finally {
            sending = false;
            send.disabled = false;
            input.readOnly = false;
            input.focus();
        }
    });
    input.addEventListener('keydown', event => {
        if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            composer.requestSubmit();
        }
    });
    input.addEventListener('input', resizeInput);

    const emojis = ['😀', '😃', '😂', '😊', '🙂', '😉', '😍', '😎', '🤔', '😢', '😭', '😡', '👍', '👎', '❤️', '🔥', '🎉', '✅', '🚀'];
    for (const emoji of emojis) {
        const choice = document.createElement('button');
        choice.type = 'button';
        choice.className = 'button-6';
        renderEmojiText(choice, emoji);
        choice.setAttribute('aria-label', `Вставить ${emoji}`);
        choice.addEventListener('click', () => {
            if (input.readOnly) return;
            const start = input.selectionStart;
            const end = input.selectionEnd;
            if (input.value.length - (end - start) + emoji.length <= input.maxLength) {
                input.setRangeText(emoji, start, end, 'end');
                resizeInput();
            }
            picker.hidden = true;
            emojiToggle.setAttribute('aria-expanded', 'false');
            input.focus();
        });
        picker.append(choice);
    }
    emojiToggle.addEventListener('click', () => {
        picker.hidden = !picker.hidden;
        emojiToggle.setAttribute('aria-expanded', String(!picker.hidden));
    });
    if (chatWindow.restoreOpen) openChat();
    else poll();
}
