import {requestJSON} from './api.js';
import {showToast} from './toast.js';
import {applyThemeColors} from './theme-colors.js';
import {enableDialogDrag} from './dialog-drag.js?v=20261004-4';
import {isViewAs, viewAsURL} from './view-as.js';

const dialog = document.getElementById('themeScheduleModal');
enableDialogDrag(dialog);
const colorDialog = document.getElementById('dialogHead');
const form = document.getElementById('themeScheduleForm');
const list = document.getElementById('themeScheduleList');
const empty = document.getElementById('themeScheduleEmpty');
const status = document.getElementById('themeScheduleStatus');
const errorBox = document.getElementById('themeScheduleError');
const confirmation = document.getElementById('themeDeleteConfirmation');
const addButton = document.getElementById('saveCurrentTheme');
let state = JSON.parse(document.getElementById('themeScheduleInitial').textContent);
let editingId = null, deletingId = null, timer = null, syncing = false, revision = 0;
let wallClock = Date.now(), monotonicClock = performance.now();
const MAX_CHECK_DELAY = 5 * 60 * 1000;

function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}
function actionButton(icon, label, callback) {
    const button = node('button');
    button.type = 'button';
    button.title = label;
    button.setAttribute('aria-label', label);
    const glyph = node('i', `fa-solid ${icon}`);
    glyph.setAttribute('aria-hidden', 'true');
    button.append(glyph);
    button.addEventListener('click', callback);
    return button;
}
function showError(error) {
    errorBox.textContent = error.message || 'Не удалось выполнить запрос.';
    errorBox.hidden = false;
}
function render() {
    list.replaceChildren();
    empty.hidden = state.themes.length > 0;
    document.getElementById('themeScheduleHeading').hidden = !state.themes.length;
    document.getElementById('themeScheduleTimezone').textContent = state.timezone
        ? `${isViewAs ? 'Часовой пояс пользователя' : 'Время вашего часового пояса'}: ${state.timezone}.`
        : isViewAs ? 'Часовой пояс пользователя ещё не сохранён.' : 'Уточняем часовой пояс браузера…';
    const active = state.themes.find(theme => theme.id === state.active_id);
    status.textContent = state.manual_override ? 'Ручные цвета действуют до следующего переключения.'
        : active ? `Сейчас: ${active.name}` : 'Автоматическое переключение выключено.';
    for (const theme of state.themes) {
        const row = node('div', 'theme-schedule__row');
        row.setAttribute('role', 'listitem');
        const name = node('div', 'theme-schedule__name', theme.name);
        if (theme.id === state.active_id) name.append(node('span', 'theme-schedule__badge', 'Сейчас'));
        const palette = node('div', 'theme-schedule__palette');
        palette.setAttribute('aria-hidden', 'true');
        for (const value of Object.values(theme.colors)) {
            const swatch = node('span', 'theme-schedule__swatch');
            if (/^#[\da-f]{6}$/i.test(value)) swatch.style.backgroundColor = value;
            palette.append(swatch);
        }
        name.append(palette);
        const time = node('span', 'theme-schedule__time', theme.activation_time);
        const enabled = node('input');
        enabled.type = 'checkbox';
        enabled.checked = theme.is_enabled;
        enabled.disabled = isViewAs;
        enabled.setAttribute('aria-label', `Активна: ${theme.name}`);
        enabled.addEventListener('change', () => mutate(urlFor('update', theme.id), 'PATCH', {is_enabled: enabled.checked},
            enabled.checked ? 'Автоматическое включение настроено.' : 'Автоматическое включение отключено.'));
        const actions = node('div', 'theme-schedule__row-actions');
        actions.append(actionButton('fa-pen', `Изменить тему «${theme.name}»`, () => edit(theme)),
            actionButton('fa-trash-can', `Удалить тему «${theme.name}»`, () => askDelete(theme)));
        if (isViewAs) for (const button of actions.querySelectorAll('button')) button.disabled = true;
        row.append(name, time, enabled, actions);
        list.append(row);
    }
}
function urlFor(action, id) {
    return dialog.dataset[`${action}Url`].replace('/0/', `/${id}/`);
}
function scheduleCheck() {
    clearTimeout(timer);
    const delay = state.next_change_at ? Date.parse(state.next_change_at) - Date.parse(state.server_now) : MAX_CHECK_DELAY;
    // The five-minute ceiling also picks up schedules edited in another device.
    timer = setTimeout(sync, Math.max(100, Math.min(delay, MAX_CHECK_DELAY)));
    wallClock = Date.now();
    monotonicClock = performance.now();
}
function accept(next) {
    state = next;
    // A response started before the editor opened must not overwrite its draft.
    if (!colorDialog?.open) applyThemeColors(state.colors);
    render();
    scheduleCheck();
}
async function sync() {
    if (document.hidden || syncing || form.dataset.busy || colorDialog?.open) {
        clearTimeout(timer);
        timer = setTimeout(sync, MAX_CHECK_DELAY);
        return;
    }
    syncing = true;
    const version = revision;
    try {
        let next = await requestJSON(viewAsURL(isViewAs ? dialog.dataset.listUrl : dialog.dataset.applyUrl),
            {method: isViewAs ? 'GET' : 'POST'});
        if (!isViewAs && !next.timezone && window.habitusSyncTimezone) {
            // Reuse the existing browser timezone sender after an offline first load.
            await window.habitusSyncTimezone();
            next = await requestJSON(dialog.dataset.applyUrl);
        }
        if (version === revision) {
            accept(next);
            if (next.changed) {
                const active = next.themes.find(theme => theme.id === next.active_id);
                if (active) showToast(`Включена тема «${active.name}».`);
            }
        }
    } catch (error) {
        if (dialog.open) showError(error);
        clearTimeout(timer);
        timer = setTimeout(sync, 30000);
    } finally {
        syncing = false;
    }
}
function busy(value) {
    if (value) form.dataset.busy = 'true';
    else delete form.dataset.busy;
    for (const control of dialog.querySelectorAll('button, input')) control.disabled = value;
}
async function mutate(url, method, data, message) {
    if (isViewAs) return;
    if (form.dataset.busy) return;
    revision++;
    errorBox.hidden = true;
    busy(true);
    let completed = false;
    try {
        const next = await requestJSON(url, {method, data, json: true});
        accept(next);
        form.hidden = true;
        confirmation.hidden = true;
        addButton.hidden = false;
        showToast(message);
        completed = true;
    } catch (error) {
        render(); // Restore the persisted checkbox state on failure.
        showError(error);
    } finally {
        busy(false);
        if (completed) addButton.focus({preventScroll: true});
    }
}
function edit(theme = null) {
    editingId = theme?.id ?? null;
    deletingId = null;
    confirmation.hidden = true;
    errorBox.hidden = true;
    form.reset();
    form.elements.name.setCustomValidity('');
    form.elements.name.value = theme?.name ?? '';
    form.elements.activation_time.value = theme?.activation_time ?? '08:00';
    form.elements.is_enabled.checked = theme?.is_enabled ?? true;
    document.getElementById('themeScheduleFormTitle').textContent = theme ? 'Изменить расписание' : 'Сохранить текущую тему';
    form.hidden = false;
    addButton.hidden = true;
    form.elements.name.focus();
}
function askDelete(theme) {
    deletingId = theme.id;
    form.hidden = true;
    addButton.hidden = false;
    errorBox.hidden = true;
    document.getElementById('themeDeleteQuestion').textContent = `Удалить тему «${theme.name}»?`;
    confirmation.hidden = false;
    document.getElementById('cancelThemeDelete').focus();
}
addButton.addEventListener('click', () => edit());
document.getElementById('cancelThemeEdit').addEventListener('click', () => {
    form.hidden = true;
    addButton.hidden = false;
    errorBox.hidden = true;
    addButton.focus();
});
document.getElementById('cancelThemeDelete').addEventListener('click', () => {
    confirmation.hidden = true;
    addButton.focus();
});
document.getElementById('confirmThemeDelete').addEventListener('click', () => {
    if (deletingId !== null) mutate(urlFor('delete', deletingId), 'DELETE', {}, 'Тема удалена.');
});
form.addEventListener('submit', event => {
    event.preventDefault();
    if (!form.elements.name.value.trim()) {
        form.elements.name.setCustomValidity('Введите название темы.');
        form.elements.name.reportValidity();
        return;
    }
    if (!form.checkValidity() || form.dataset.busy) return;
    const data = {name: form.elements.name.value.trim(), activation_time: form.elements.activation_time.value,
        is_enabled: form.elements.is_enabled.checked};
    mutate(editingId === null ? dialog.dataset.createUrl : urlFor('update', editingId),
        editingId === null ? 'POST' : 'PATCH', data, editingId === null ? 'Тема сохранена.' : 'Расписание обновлено.');
});
document.getElementById('themeScheduleButton').addEventListener('click', async () => {
    errorBox.hidden = true;
    const version = revision;
    try {
        const next = await requestJSON(viewAsURL(dialog.dataset.listUrl), {method: 'GET'});
        if (version === revision) accept(next);
    } catch (error) {
        showError(error);
    }
});
document.addEventListener('visibilitychange', () => { if (!document.hidden) sync(); });
// Focus returns from the native color picker too. Resume only after the editor closes.
colorDialog?.addEventListener('close', sync);
window.addEventListener('focus', sync);
window.addEventListener('online', sync);
window.addEventListener('habitus:timezone-ready', sync);
// Only a local clock check: no server request on each tick.
setInterval(() => {
    const drift = (Date.now() - wallClock) - (performance.now() - monotonicClock);
    if (Math.abs(drift) > 1500 && !document.hidden) sync();
}, 30000);
render();
Promise.resolve(window.habitusTimezoneReady).then(sync);
