import {requestJSON} from './api.js?v=20261109-summary';
import {isViewAs} from './view-as.js';

export function createHabitSummary(dialog, request = requestJSON) {
    if (!dialog) return {open() {}};
    const node = name => document.getElementById(`habitSummary${name}`);
    const retry = node('Retry');
    dialog.addEventListener('keydown', event => {
        if (event.key !== 'Tab') return;
        const controls = [...dialog.querySelectorAll('button:not([disabled])')];
        const first = controls[0], last = controls.at(-1);
        if (!first) return;
        if ((!event.shiftKey && document.activeElement === last)
            || (event.shiftKey && document.activeElement === first)) {
            event.preventDefault();
            (event.shiftKey ? last : first).focus();
        }
    });
    let revision = 0, busy = false, cached = null, retryAt = 0, timer;
    const day = () => new Date().toLocaleDateString('sv-SE');
    const key = () => `${dialog.dataset.month}:${day()}:${revision}`;
    const status = (state, text) => {
        node('Status').dataset.state = state;
        node('Status').textContent = text;
    };
    function buttons() {
        clearTimeout(timer);
        const remaining = Math.max(0, Math.ceil((retryAt - Date.now()) / 1000));
        retry.disabled = busy || remaining > 0;
        if (retry.disabled && document.activeElement === retry) dialog.querySelector('[data-dialog-close]')?.focus();
        retry.textContent = remaining ? `Повтор через ${remaining} с` : 'Обновить';
        if (remaining) timer = setTimeout(buttons, 1000);
    }
    function hideResult() {
        node('Stats').hidden = true;
        node('Result').hidden = true;
    }
    function render(result) {
        const stats = result.stats;
        if (stats) {
            node('Period').textContent = `Месяц: ${stats.month}. ` + (stats.through
                ? `Оценка: ${stats.start} — ${stats.through} (включительно).`
                : 'Все дни этого месяца ещё впереди.');
            node('Count').textContent = String(stats.habit_count);
            node('Marks').textContent = `${stats.completed} / ${stats.available}`;
            node('Percent').textContent = stats.percent === null ? 'Нет доступных дней' : `${stats.percent}%`;
            node('Stats').hidden = false;
        }
        const messages = {
            success: 'Сводка готова.', empty: 'В выбранном месяце нет привычек.',
            no_days: 'Нет доступных дней выполнения для оценки.',
        };
        status(result.state, result.error || messages[result.state] || 'Не удалось получить сводку.');
        if (result.state === 'success') {
            node('Text').textContent = result.text;
            node('Time').textContent = `Получено: ${new Date(result.received_at).toLocaleString('ru-RU')}.`
                + (result.truncated ? ' Ответ достиг ограничения длины.' : '');
            node('Result').hidden = false;
        }
    }
    function invalidate() {
        revision++;
        cached = null;
        if (dialog.open) {
            hideResult();
            status('stale', 'Данные изменились. Обновите сводку после сохранения отметок.');
        }
    }
    for (const event of ['habitus:activity-marked', 'habitus:rows-changed']) window.addEventListener(event, invalidate);
    // A submitted calendar navigates to a new document; invalidate before a late response can render.
    document.getElementById('chooseDate')?.addEventListener('submit', invalidate);
    window.addEventListener('pagehide', invalidate);
    async function load(force = false) {
        if (isViewAs || busy || Date.now() < retryAt) return;
        hideResult();
        node('Period').textContent = `Выбранный месяц: ${dialog.dataset.month}.`;
        if (!force && cached?.key === key()) {
            render(cached.result);
            return;
        }
        busy = true;
        buttons();
        dialog.setAttribute('aria-busy', 'true');
        let snapshotKey;
        try {
            status('loading', 'Ждём завершения сохранения отметок…');
            // Synchronize first: marks may change while the timezone POST is pending.
            const timezone = await window.habitusTimezoneReady;
            if (!timezone && window.habitusSyncTimezone) await window.habitusSyncTimezone();
            while (document.querySelector('[data-mark-pending]')) {
                await new Promise(resolve => window.addEventListener('habitus:marks-settled', resolve, {once: true}));
            }
            if (!dialog.open) return;
            snapshotKey = key();
            status('loading', 'Готовим сводку… Генерация может занять несколько минут.');
            const result = await request(dialog.dataset.summaryUrl, {json: true, data: {month: dialog.dataset.month}});
            if (key() !== snapshotKey) {
                status('stale', 'Период или данные изменились. Обновите сводку.');
                return;
            }
            if (['success', 'empty', 'no_days'].includes(result?.state)) cached = {key: snapshotKey, result};
            if (dialog.open) render(result);
        } catch (error) {
            const seconds = Number(error.retryAfter ?? error.result?.retry_after);
            if (Number.isFinite(seconds) && seconds > 0) retryAt = Date.now() + seconds * 1000;
            if (dialog.open && (!snapshotKey || key() === snapshotKey)) {
                render(error.result || {state: 'error', error: error.message});
            }
        } finally {
            busy = false;
            dialog.removeAttribute('aria-busy');
            buttons();
        }
    }
    retry.addEventListener('click', () => load(true));
    return {open: () => load()};
}
