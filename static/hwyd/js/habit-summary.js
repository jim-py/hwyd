import {requestJSON} from './api.js?v=20261109-summary';
import {isViewAs} from './view-as.js';

export function createHabitSummary(dialog, request = requestJSON) {
    if (!dialog) return {open() {}};
    const node = name => document.getElementById(`habitSummary${name}`);
    const retry = node('Retry');
    let revision = 0, busy = false, stats = null, saved = null, retryAt = 0, timer, needsStats = false;
    const day = () => new Date().toLocaleDateString('sv-SE');
    const key = () => `${dialog.dataset.month}:${day()}:${revision}`;
    const date = value => value?.split('-').reverse().join('.') || '';
    const period = facts => facts.through ? `${date(facts.start)} — ${date(facts.through)}` : facts.month;
    function status(state, text = '') {
        node('Status').dataset.state = state;
        node('Status').textContent = text;
        node('Status').hidden = !text;
    }
    function selectTab(name, focus = false) {
        for (const tab of ['AI', 'Stats']) {
            const selected = tab === name;
            node(`Tab${tab}`).setAttribute('aria-selected', String(selected));
            node(`Tab${tab}`).tabIndex = selected ? 0 : -1;
            node(`Panel${tab}`).hidden = !selected;
        }
        if (focus) node(`Tab${name}`).focus();
    }
    for (const [index, name] of ['AI', 'Stats'].entries()) {
        const tab = node(`Tab${name}`);
        tab.addEventListener('click', () => selectTab(name));
        tab.addEventListener('keydown', event => {
            let target;
            if (['ArrowRight', 'ArrowLeft'].includes(event.key)) target = ['AI', 'Stats'][1 - index];
            if (event.key === 'Home') target = 'AI';
            if (event.key === 'End') target = 'Stats';
            if (target) { event.preventDefault(); selectTab(target, true); }
        });
    }
    dialog.addEventListener('keydown', event => {
        if (event.key !== 'Tab') return;
        const controls = [...dialog.querySelectorAll('button:not([disabled]):not([tabindex="-1"]), [role="tabpanel"]')]
            .filter(control => !control.closest('[hidden]'));
        const first = controls[0], last = controls.at(-1);
        if (!first) return;
        if ((!event.shiftKey && document.activeElement === last) || (event.shiftKey && document.activeElement === first)) {
            event.preventDefault();
            (event.shiftKey ? last : first).focus();
        }
    });
    function buttons() {
        clearTimeout(timer);
        const remaining = Math.max(0, Math.ceil((retryAt - Date.now()) / 1000));
        retry.disabled = busy || remaining > 0;
        if (retry.disabled && document.activeElement === retry) dialog.querySelector('[data-dialog-close]')?.focus();
        retry.textContent = remaining ? `Через ${remaining} с` : busy ? 'Обновляем…' : 'Обновить';
        if (remaining) timer = setTimeout(buttons, 1000);
    }
    function list(target, entries, value) {
        const items = entries.map(entry => {
            const row = document.createElement('li');
            const label = document.createElement('span');
            const number = document.createElement('span');
            label.textContent = entry.name;
            number.textContent = value(entry);
            row.append(label, number);
            return row;
        });
        target.replaceChildren(...items);
    }
    function renderChanges() {
        const changes = stats?.changes || {};
        const temporal = Boolean(changes.improvements?.length || changes.declines?.length);
        const categories = temporal ? {Improvements: changes.improvements, Declines: changes.declines}
            : {Most: stats?.regularity?.most_regular, Least: stats?.regularity?.least_regular};
        let visible = false;
        for (const name of ['Improvements', 'Declines', 'Most', 'Least']) {
            const entries = categories[name] || [];
            node(name).hidden = !entries.length;
            list(node(name).querySelector('ul'), entries, entry => temporal
                ? `${entry.delta_pp > 0 ? '+' : ''}${entry.delta_pp} п.п.` : `${entry.percent}%`);
            visible ||= entries.length > 0;
        }
        node('Changes').hidden = !visible;
        node('ChangesTitle').textContent = temporal ? 'Что изменилось' : 'В этом периоде';
        node('ComparisonPeriod').hidden = !temporal;
        if (temporal) {
            const p = stats.comparison_period;
            node('ComparisonPeriod').textContent = `${date(p.current_start)} — ${date(p.current_end)} к ${date(p.previous_start)} — ${date(p.previous_end)}`;
        }
    }
    function renderStats(facts) {
        stats = facts;
        node('Period').textContent = period(facts);
        node('Count').textContent = String(facts.habit_count);
        node('Marks').textContent = `${facts.completed} / ${facts.available}`;
        node('Percent').textContent = facts.percent === null ? '—' : `${facts.percent}%`;
        node('Stats').hidden = !facts.habit_count;
        node('StatsStatus').textContent = !facts.habit_count ? 'В этом месяце нет привычек.'
            : !facts.available ? 'Нет доступных дней выполнения.' : '';
        node('StatsStatus').hidden = Boolean(facts.habit_count && facts.available);
        list(node('Habits'), facts.habits || [], habit => `${habit.completed} / ${habit.available} · ${habit.percent === null ? '—' : `${habit.percent}%`}`);
        renderChanges();
    }
    function renderSaved() {
        const show = saved?.stats.month === dialog.dataset.month;
        node('Result').hidden = !show;
        node('Advice').hidden = !show;
        const stale = show && (saved.key !== key() || (stats && saved.stats.snapshot !== stats.snapshot));
        node('SnapshotHint').hidden = !stale;
        if (show) {
            node('Text').textContent = saved.ai.summary;
            node('AdviceText').textContent = saved.ai.advice;
            node('SnapshotHint').textContent = `Сводка за ${period(saved.stats)}. Данные изменились — обнови её.`;
        }
    }
    function invalidate() {
        revision++;
        stats = null;
        needsStats = true;
        node('Stats').hidden = true;
        node('Changes').hidden = true;
        node('StatsStatus').textContent = 'Данные изменились. Обнови статистику.';
        node('StatsStatus').hidden = false;
        renderSaved();
        if (dialog.open) status('stale', 'Данные изменились.');
    }
    window.addEventListener('habitus:activity-marked', invalidate);
    window.addEventListener('habitus:rows-changed', () => {
        invalidate();
        if (dialog.open && !busy) load(false);
    });
    window.addEventListener('habitus:marks-settled', () => { if (dialog.open && !busy) load(false); });
    document.getElementById('chooseDate')?.addEventListener('submit', invalidate);
    window.addEventListener('pagehide', () => { revision++; });
    async function load(generate) {
        if (isViewAs || busy || (generate && Date.now() < retryAt)) return;
        busy = true;
        needsStats = false;
        buttons();
        let snapshotKey;
        try {
            if (generate) status('loading', 'Обновляем AI-сводку…');
            else if (!saved) status('loading', 'Загрузка…');
            if (!stats) {
                node('StatsStatus').textContent = 'Загрузка…';
                node('StatsStatus').hidden = false;
            }
            const tz = await window.habitusTimezoneReady;
            if (!tz && window.habitusSyncTimezone) await window.habitusSyncTimezone();
            while (document.querySelector('[data-mark-pending]')) {
                await new Promise(resolve => window.addEventListener('habitus:marks-settled', resolve, {once: true}));
            }
            if (!dialog.open) return;
            needsStats = false;
            snapshotKey = key();
            const result = await request(dialog.dataset.summaryUrl, {json: true, data: {month: dialog.dataset.month, generate}});
            if (key() !== snapshotKey) { status('stale', 'Данные изменились. Обнови сводку.'); return; }
            if (result.stats) renderStats(result.stats);
            if (generate && result.state === 'success' && result.ai) saved = {...result, key: snapshotKey};
            renderSaved();
            const messages = {empty: 'В этом месяце нет привычек.', no_days: 'Нет доступных дней для сводки.'};
            status(result.state, messages[result.state] || (saved ? '' : 'Нажми «Обновить», чтобы получить сводку.'));
        } catch (error) {
            const seconds = Number(error.retryAfter ?? error.result?.retry_after);
            if (Number.isFinite(seconds) && seconds > 0) retryAt = Date.now() + seconds * 1000;
            if (!snapshotKey || key() === snapshotKey) {
                if (error.result?.stats) renderStats(error.result.stats);
                renderSaved();
                status(error.result?.state || 'error', typeof error.result?.error === 'string'
                    ? error.result.error : 'Не удалось обновить сводку. Попробуй позже.');
                if (!stats) {
                    node('StatsStatus').textContent = 'Не удалось загрузить статистику. Попробуй обновить.';
                    node('StatsStatus').hidden = false;
                }
            }
        } finally {
            busy = false;
            buttons();
            // Only a data change can schedule this follow-up read; it never calls AI.
            if (needsStats && dialog.open) load(false);
        }
    }
    retry.addEventListener('click', () => load(true));
    return {open() { selectTab('AI'); renderSaved(); return load(false); }};
}
