export function messagePreview(message) {
    const count = message.attachments?.length || message.attachment_count || (message.photo || message.has_photo ? 1 : 0);
    const video = message.has_video || message.attachments?.some(item => item.kind === 'video');
    if (!count) return message.text || '';
    const label = count > 1 ? `${count} ${count < 5 ? 'вложения' : 'вложений'}` : (video ? 'Видео WebM' : 'Фотография');
    return `${video ? '🎞' : '📷'} ${count > 1 ? label + (message.text ? ': ' : '') : ''}${message.text || (count === 1 ? label : '')}`;
}

export function configureChatWebm(video) {
    video.muted = video.defaultMuted = true;
    video.autoplay = video.loop = video.playsInline = true;
    video.controls = false;
    video.preload = 'metadata';
    video.setAttribute('controlslist', 'nofullscreen');
    video.disablePictureInPicture = true;
    // Keep the message's context menu, without the browser's video/fullscreen menu.
    video.addEventListener('contextmenu', event => event.preventDefault());
}

export function createChatPhotos(dialog, { showError, onChange }) {
    const field = dialog.querySelector('#chatPhotoInput');
    const attach = dialog.querySelector('#chatPhotoAttach');
    const selection = dialog.querySelector('#chatPhotoSelection');
    const help = dialog.querySelector('#chatPhotoHelp');
    let entries = [], busy = false, editing = false, replacing = null;
    function sync() {
        if (field) {
            attach.hidden = editing;
            if (help) help.hidden = editing;
            attach.disabled = field.disabled = busy;
            selection.hidden = !entries.length || editing;
            for (const button of selection.querySelectorAll('button')) button.disabled = busy;
        }
        onChange();
    }
    function release(entry) {
        if (entry.kind === 'video') entry.preview.pause();
        entry.preview.removeAttribute('src');
        if (entry.kind === 'video') entry.preview.load();
        URL.revokeObjectURL(entry.url);
    }
    function clear() {
        const previous = entries;
        entries = [];
        for (const entry of previous) release(entry);
        if (field) { field.value = ''; selection.replaceChildren(); }
        replacing = null; sync();
    }
    function render() { selection.replaceChildren(...entries.map(entry => entry.card)); sync(); }
    function createEntry(file) {
        const kind = file.type === 'video/webm' || /\.webm$/i.test(file.name) ? 'video' : 'image';
        const card = document.createElement('div'); card.className = 'chat-attachment-draft';
        const preview = document.createElement(kind === 'video' ? 'video' : 'img');
        if (kind === 'video') configureChatWebm(preview);
        else preview.alt = 'Выбранная фотография';
        const entry = { file, kind, card, preview, url: URL.createObjectURL(file), invalid: false, pending: true };
        preview.addEventListener(kind === 'video' ? 'loadedmetadata' : 'load', () => {
            if (!entries.includes(entry)) return;
            entry.pending = false;
            const pixels = kind === 'video' ? preview.videoWidth * preview.videoHeight : preview.naturalWidth * preview.naturalHeight;
            entry.invalid = pixels > 20_000_000 || (kind === 'video' && (!Number.isFinite(preview.duration) || preview.duration > 10.1));
            if (entry.invalid) showError('Максимум 20 мегапикселей; WebM — до 10 секунд. Замените или уберите этот файл.');
        });
        preview.addEventListener('error', () => {
            if (!entries.includes(entry)) return;
            entry.invalid = true; entry.pending = false;
            showError('Не удалось прочитать вложение. Замените или уберите этот файл.');
        });
        const name = document.createElement('span'); name.textContent = file.name;
        const replace = document.createElement('button'); replace.type = 'button'; replace.textContent = 'Заменить';
        replace.setAttribute('aria-label', `Заменить ${file.name}`);
        replace.addEventListener('click', () => { replacing = entry; field.click(); });
        const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '×';
        remove.setAttribute('aria-label', `Убрать ${file.name}`);
        remove.addEventListener('click', () => {
            entries = entries.filter(item => item !== entry); release(entry); render(); showError();
        });
        card.append(preview, name, replace, remove); preview.src = entry.url;
        return entry;
    }
    if (field) {
        attach.addEventListener('click', () => { replacing = null; field.click(); });
        field.addEventListener('change', () => {
            const chosen = Array.from(field.files); field.value = '';
            if (!chosen.length) return;
            const replaceIndex = entries.indexOf(replacing);
            if (entries.length - (replaceIndex >= 0 ? 1 : 0) + chosen.length > 10) {
                showError('Можно прикрепить не больше 10 файлов.'); return;
            }
            if (chosen.some(file => file.size > 5 * 1024 * 1024)) {
                showError('Каждый файл должен быть не больше 5 МиБ.'); return;
            }
            if (chosen.some(file => !['image/jpeg', 'image/png', 'image/webp', 'video/webm'].includes(file.type) &&
                !/\.(jpe?g|png|webp|webm)$/i.test(file.name))) {
                showError('Разрешены только JPEG, PNG, WebP и WebM.'); return;
            }
            const additions = chosen.map(createEntry);
            if (replaceIndex >= 0) { release(entries[replaceIndex]); entries.splice(replaceIndex, 1, ...additions); }
            else entries.push(...additions);
            replacing = null; showError(); render();
        });
        window.addEventListener('pagehide', event => { if (!event.persisted) for (const entry of entries) release(entry); });
    }
    const viewer = document.getElementById('chatPhotoViewer');
    const full = document.getElementById('chatPhotoFull');
    const original = document.getElementById('chatPhotoOriginal');
    const viewerError = document.getElementById('chatPhotoViewerError');
    let returnFocus = null;
    function open(attachment, trigger) {
        if (attachment.kind === 'video') return;
        returnFocus = trigger; viewerError.hidden = true;
        original.href = attachment.url; full.src = attachment.url;
        viewer.showModal();
        document.getElementById('chatPhotoViewerClose').focus();
    }
    document.getElementById('chatPhotoViewerClose').addEventListener('click', () => viewer.close());
    full.addEventListener('error', () => { if (viewer.open) viewerError.hidden = false; });
    viewer.addEventListener('close', () => {
        full.removeAttribute('src'); original.removeAttribute('href');
        if (returnFocus?.isConnected && dialog.open) returnFocus.focus({ preventScroll: true });
        else if (dialog.open) document.getElementById('chatMessages').focus();
        returnFocus = null;
    });
    dialog.addEventListener('close', () => { if (!dialog.open && viewer.open) viewer.close(); });
    return { open, clear, files: () => editing ? [] : entries.map(entry => entry.file),
        validate() {
            if (!editing && entries.some(entry => entry.pending || entry.invalid)) {
                showError(entries.some(entry => entry.invalid) ? 'Замените или уберите некорректное вложение.' : 'Дождитесь загрузки превью.'); return false;
            }
            return true;
        }, setBusy(value) { busy = value; sync(); }, setEditing(value) { editing = value; sync(); } };
}
