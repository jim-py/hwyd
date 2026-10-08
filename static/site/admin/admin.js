function showAudience(link, tooltip) {
    const rect = link.getBoundingClientRect();
    tooltip.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - 254))}px`;
    tooltip.style.top = `${Math.max(8, Math.min(rect.bottom + 8, innerHeight - 270))}px`;
    tooltip.hidden = false;
    if (tooltip.dataset.loaded) return;
    tooltip.textContent = 'Загрузка…';
    const url = new URL(link.dataset.audienceUrl, location.href);
    url.searchParams.set('sample', '1');
    fetch(url, {credentials:'same-origin', cache:'no-store', headers:{Accept:'application/json'}}).then(async response => {
        if (!response.ok || response.redirected) throw new Error();
        const data = await response.json();
        tooltip.textContent = data.names.length ? data.names.join(', ') : 'Записей пока нет.';
        if (data.total > data.names.length) tooltip.append(document.createTextNode(` · ещё ${data.total - data.names.length}. Откройте счётчик для полного списка.`));
        tooltip.dataset.loaded = '1';
    }).catch(() => { tooltip.textContent = 'Не удалось загрузить имена. Откройте счётчик для повторной попытки.'; });
}
for (const link of document.querySelectorAll('[data-audience-url]')) {
    let tooltip = link.parentElement.querySelector('.pv-tooltip');
    if (!tooltip) { tooltip = document.createElement('span'); tooltip.className = 'pv-tooltip'; tooltip.hidden = true; tooltip.setAttribute('role','status'); link.parentElement.append(tooltip); }
    for (const event of ['mouseenter','focus']) link.addEventListener(event, () => showAudience(link, tooltip));
    for (const event of ['mouseleave','blur']) link.addEventListener(event, () => { tooltip.hidden = true; });
}
const preview = document.querySelector('[data-notification-preview]');
preview?.addEventListener('click', async () => {
    const status = document.getElementById('pv-preview-status');
    const frame = document.getElementById('pv-preview-frame');
    const form = preview.closest('form');
    const method = preview.dataset.method;
    preview.disabled = true; status.textContent = 'Подготовка предпросмотра…';
    try {
        const response = await fetch(preview.dataset.notificationPreview, {method, credentials:'same-origin', cache:'no-store',
            headers:{'X-CSRFToken':form.querySelector('[name=csrfmiddlewaretoken]').value, Accept:'application/json'},
            body:method === 'POST' ? new URLSearchParams({title:form.querySelector('[name=title]').value, message:form.querySelector('[name=message]').value}) : undefined});
        if (!response.ok || response.redirected) throw new Error('Не удалось открыть предпросмотр. Проверьте права и размер содержимого.');
        frame.srcdoc = (await response.json()).html; frame.hidden = false; preview.setAttribute('aria-expanded','true');
        status.textContent = 'Предпросмотр готов. Ничего не сохранено.';
    } catch(error) { status.textContent = error.message; } finally { preview.disabled = false; }
});
