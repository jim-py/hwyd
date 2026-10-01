export function createMessageActions({ dialog, history, input, send, list, request, showError, resizeInput, onMutation }) {
    const narrow = window.matchMedia('(max-width: 1023px)');
    const menu = dialog.querySelector('#chatActionMenu');
    const choices = dialog.querySelector('#chatActionChoices');
    const confirm = dialog.querySelector('#chatDeleteConfirm');
    const modeBox = dialog.querySelector('#chatMode');
    const modeTitle = dialog.querySelector('#chatModeTitle');
    const modeText = dialog.querySelector('#chatModeText');
    const sendLabel = dialog.querySelector('#chatSendLabel');
    let selected = null, mode = null, draft = '', moved = false, origin = null;

    const endpoint = id => `${dialog.dataset.messagesUrl}${id}/`;
    function closeMenu(focus = false) {
        menu.hidden = true;
        document.removeEventListener('pointerdown', outside);
        if (focus && selected) list.node(selected.id)?.focus({ preventScroll: true });
        selected = null;
    }
    function outside(event) { if (!menu.contains(event.target)) closeMenu(); }

    function position(x, y) {
        const rect = dialog.getBoundingClientRect(), size = menu.getBoundingClientRect();
        const composerTop = dialog.querySelector('#chatComposer').getBoundingClientRect().top;
        const left = narrow.matches ? rect.left + (rect.width - size.width) / 2 : x;
        const top = narrow.matches ? composerTop - size.height - 8 : y;
        menu.style.left = `${Math.max(8, Math.min(left - rect.left, rect.width - size.width - 8))}px`;
        menu.style.top = `${Math.max(8, Math.min(top - rect.top, rect.height - size.height - 8))}px`;
    }

    function openMenu(message, x, y) {
        closeMenu();
        if (!message || input.readOnly) return;
        selected = message;
        choices.hidden = false;
        confirm.hidden = true;
        for (const action of ['edit', 'delete']) menu.querySelector(`[data-action="${action}"]`).hidden = !message.is_own;
        menu.hidden = false;
        position(x, y);
        document.addEventListener('pointerdown', outside);
        menu.querySelector('[data-action="reply"]').focus({ preventScroll: true });
    }

    function resetMode(restoreDraft = true) {
        if (mode?.type === 'edit' && restoreDraft) input.value = draft;
        mode = null;
        modeBox.hidden = true;
        send.classList.remove('chat-send--editing');
        sendLabel.hidden = true;
        send.setAttribute('aria-label', 'Отправить сообщение');
        send.title = 'Отправить';
        resizeInput();
    }
    function setMode(type, message) {
        resetMode();
        mode = { type, message };
        if (type === 'edit') { draft = input.value; input.value = message.text; }
        modeTitle.textContent = type === 'edit' ? 'Редактирование сообщения' : `Ответ: ${message.sender}`;
        modeText.textContent = Array.from(message.text).slice(0, 160).join('');
        modeBox.hidden = false;
        send.classList.toggle('chat-send--editing', type === 'edit');
        sendLabel.hidden = type !== 'edit';
        send.setAttribute('aria-label', type === 'edit' ? 'Сохранить изменения' : 'Отправить сообщение');
        send.title = type === 'edit' ? 'Сохранить изменения' : 'Отправить';
        input.focus();
        resizeInput();
    }

    history.addEventListener('contextmenu', event => {
        const node = event.target.closest('[data-message-id]');
        if (!node || narrow.matches) return;
        event.preventDefault();
        openMenu(list.get(Number(node.dataset.messageId)), event.clientX, event.clientY);
    });
    history.addEventListener('pointerdown', event => { origin = [event.clientX, event.clientY]; moved = false; });
    history.addEventListener('pointermove', event => {
        if (origin && Math.hypot(event.clientX - origin[0], event.clientY - origin[1]) > 8) moved = true;
    });
    history.addEventListener('pointerup', () => { origin = null; });
    history.addEventListener('pointercancel', () => { origin = null; moved = true; });
    history.addEventListener('click', event => {
        const node = event.target.closest('[data-message-id]');
        if (narrow.matches && node && !moved && !window.getSelection()?.toString()) {
            openMenu(list.get(Number(node.dataset.messageId)), event.clientX, event.clientY);
        }
    });
    history.addEventListener('keydown', event => {
        if (event.key !== 'ContextMenu' && !(event.shiftKey && event.key === 'F10')) return;
        const node = event.target.closest('[data-message-id]');
        if (!node) return;
        event.preventDefault();
        const rect = node.getBoundingClientRect();
        openMenu(list.get(Number(node.dataset.messageId)), rect.left + 20, rect.top + 20);
    });
    history.addEventListener('scroll', () => closeMenu());
    dialog.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !menu.hidden) {
            event.preventDefault(); event.stopPropagation(); closeMenu(true);
        }
    }, true);
    menu.addEventListener('keydown', event => {
        if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
        const buttons = [...menu.querySelectorAll('button')].filter(e => !e.hidden && !e.closest('[hidden]'));
        const index = buttons.indexOf(document.activeElement);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 :
            (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
        event.preventDefault(); buttons[next]?.focus();
    });
    menu.addEventListener('click', async event => {
        const action = event.target.closest('[data-action]')?.dataset.action;
        if (!action || !selected) return;
        if (action === 'delete') {
            choices.hidden = true; confirm.hidden = false;
            position(menu.getBoundingClientRect().left, menu.getBoundingClientRect().top);
            menu.querySelector('[data-action="cancel-delete"]').focus();
            return;
        }
        const message = selected;
        closeMenu();
        if (action === 'reply' || action === 'edit') { setMode(action, message); return; }
        if (action !== 'confirm-delete') return;
        try { onMutation((await request(endpoint(message.id), {}, 'DELETE')).message); }
        catch (failure) { showError(failure.message); }
    });
    dialog.querySelector('#chatModeCancel').addEventListener('click', () => {
        if (input.readOnly) return;
        resetMode(); input.focus();
    });
    dialog.addEventListener('close', () => { if (!dialog.open) closeMenu(); });
    window.addEventListener('resize', () => closeMenu());

    return {
        closeMenu, resetMode, endpoint, getMode: () => mode,
        onUpdate(message) {
            if (selected?.id === message.id) closeMenu();
            if (mode?.message.id !== message.id) return;
            if (message.is_deleted) {
                resetMode(); showError('Выбранное сообщение удалено.');
            } else if (mode.type === 'reply') {
                mode.message = message; modeText.textContent = Array.from(message.text).slice(0, 160).join('');
            }
        }
    };
}
