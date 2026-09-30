import { getCSRFToken } from '../../site/js/csrf.js';

const dialog = document.getElementById('chatDialog');
const button = document.getElementById('buttonChat');

if (dialog && button) {
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

    function showError(message = '') {
        error.textContent = message;
        error.hidden = !message;
    }

    function unread(value) {
        dot.hidden = !value;
        button.setAttribute('aria-label', value ? 'Чат: есть новые сообщения' : 'Чат');
    }

    async function request(url, payload) {
        const options = { credentials: 'same-origin', cache: 'no-store' };
        if (payload !== undefined) {
            options.method = 'POST';
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
            throw new Error(data.error || 'Не удалось выполнить запрос. Попробуйте ещё раз.');
        }
        return response.json();
    }

    function append(message) {
        const item = document.createElement('article');
        item.className = 'chat-message';
        if (message.is_own) item.classList.add('chat-message--own');
        const sender = document.createElement('strong');
        sender.textContent = message.sender;
        const text = document.createElement('p');
        text.textContent = message.text;
        const time = document.createElement('time');
        const date = new Date(message.created_at);
        time.dateTime = message.created_at;
        time.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        time.title = date.toLocaleString();
        item.append(sender, text, time);
        history.append(item);
        empty.hidden = true;
    }

    async function load() {
        const initial = cursor === null;
        const nearBottom = history.scrollHeight - history.scrollTop - history.clientHeight < 60;
        const url = new URL(dialog.dataset.messagesUrl, location.origin);
        if (!initial) url.searchParams.set('after_id', cursor);
        const data = await request(url);
        for (const message of data.messages) {
            if (cursor === null || message.id > cursor) {
                append(message);
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

    button.addEventListener('click', () => {
        dialog.showModal();
        input.focus();
        clearTimeout(timer);
        poll();
    });
    dialog.addEventListener('close', () => {
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
        sending = true;
        send.disabled = true;
        input.readOnly = true;
        showError();
        pollError = false;
        try {
            await request(dialog.dataset.messagesUrl, { text: value });
            input.value = '';
            // Read in ID order; appending the POST response could skip other senders.
            clearTimeout(timer);
            schedule(0);
        } catch (failure) {
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

    const emojis = ['😀', '😃', '😂', '😊', '🙂', '😉', '😍', '😎', '🤔', '😢', '😭', '😡', '👍', '👎', '❤️', '🔥', '🎉', '✅', '🚀'];
    for (const emoji of emojis) {
        const choice = document.createElement('button');
        choice.type = 'button';
        choice.className = 'button-6';
        choice.textContent = emoji;
        choice.setAttribute('aria-label', `Вставить ${emoji}`);
        choice.addEventListener('click', () => {
            if (input.readOnly) return;
            const start = input.selectionStart;
            const end = input.selectionEnd;
            if (input.value.length - (end - start) + emoji.length <= input.maxLength) {
                input.setRangeText(emoji, start, end, 'end');
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
    poll();
}
