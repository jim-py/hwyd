const switcher = document.getElementById('trackerViewSwitch');
const tableView = document.getElementById('trackerTableView');
const calendarView = document.getElementById('trackerYearView');
const monthsRoot = document.getElementById('yearCalendarMonths');
const status = document.getElementById('yearCalendarStatus');
const retry = document.getElementById('yearCalendarRetry');
const yearSelect = document.getElementById('calendarYear');
const previous = document.getElementById('yearPrevious');
const next = document.getElementById('yearNext');
const detailText = document.getElementById('yearCalendarDetailText');
const detail = document.getElementById('yearCalendarDetail');
const monthLink = document.getElementById('yearCalendarMonthLink');
const viewButtons = [...switcher.querySelectorAll('[data-tracker-view]')];
const monthNames = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
const weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const minYear = 2020;
const maxYear = 2030;
const viewKey = `habitus.tracker.view.${switcher.dataset.user}`;
const cache = new Map(); // Only this page's summaries; never store habit data in localStorage.
let year = Number(switcher.dataset.year);
let mode = 'table';
let generation = 0;
let controller;
let selectedDate = '';

function storedView() {
    try { return localStorage.getItem(viewKey); } catch { return null; }
}
function rememberView(value) {
    try { localStorage.setItem(viewKey, value); } catch { /* Storage may be disabled. */ }
}
function updateUrl() {
    const url = new URL(location.href);
    url.searchParams.set('view', mode);
    if (mode === 'year') url.searchParams.set('year', String(year));
    else url.searchParams.delete('year');
    history.replaceState(null, '', url);
}
function monthUrl(month) {
    const key = `${year}-${String(month).padStart(2, '0')}`;
    return `${switcher.dataset.monthUrl.replace('2020-01', key)}?view=table`;
}
function resetDetail() {
    selectedDate = '';
    detail.hidden = true;
    detailText.textContent = 'Выберите день, чтобы посмотреть результат.';
    monthLink.hidden = true;
}
function dateLabel(key) {
    return new Intl.DateTimeFormat('ru-RU', {day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC'})
        .format(new Date(`${key}T12:00:00Z`));
}
function describeDay(key, completed, total) {
    if (!total) return `${dateLabel(key)} · Нет привычек на этот день`;
    return `${dateLabel(key)} · Выполнено ${completed} из ${total} · ${Math.round(completed / total * 100)}%`;
}
function render(data) {
    const now = new Date(); // Today's outline follows the browser's local calendar.
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const fragment = document.createDocumentFragment();
    for (const month of data.months) {
        const section = document.createElement('section');
        section.className = 'year-calendar__month';
        const heading = document.createElement('h2');
        heading.id = `yearMonth${month.month}`;
        heading.textContent = monthNames[month.month - 1];
        section.setAttribute('aria-labelledby', heading.id);
        const week = document.createElement('div');
        week.className = 'year-calendar__weekdays';
        week.setAttribute('aria-hidden', 'true');
        for (const [index, name] of weekdays.entries()) {
            const label = document.createElement('span');
            label.textContent = name;
            if (index >= 5) label.className = 'year-calendar__weekend';
            week.append(label);
        }
        const days = document.createElement('div');
        days.className = 'year-calendar__days';
        const offset = (new Date(Date.UTC(year, month.month - 1, 1)).getUTCDay() + 6) % 7;
        for (let index = 0; index < offset; index++) {
            const blank = document.createElement('span');
            blank.setAttribute('aria-hidden', 'true');
            days.append(blank);
        }
        for (const [index, counts] of month.days.entries()) {
            const key = `${year}-${String(month.month).padStart(2, '0')}-${String(index + 1).padStart(2, '0')}`;
            const button = document.createElement('button');
            const percentage = counts.total ? counts.completed / counts.total * 100 : 0;
            button.type = 'button';
            button.tabIndex = -1;
            button.className = 'year-calendar__day';
            button.textContent = String(index + 1);
            button.dataset.date = key;
            button.dataset.month = String(month.month);
            button.dataset.total = String(counts.total);
            button.dataset.completed = String(counts.completed);
            button.dataset.full = String(counts.total > 0 && counts.completed === counts.total);
            button.dataset.future = String(key > today);
            button.style.setProperty('--fill', `${percentage}%`);
            button.title = describeDay(key, counts.completed, counts.total);
            button.setAttribute('aria-label', button.title);
            button.setAttribute('aria-pressed', 'false');
            if (key === today) button.setAttribute('aria-current', 'date');
            if ((offset + index) % 7 >= 5) button.classList.add('year-calendar__weekend');
            days.append(button);
        }
        section.append(heading, week, days);
        fragment.append(section);
    }
    monthsRoot.replaceChildren(fragment);
    const initialDay = monthsRoot.querySelector('[aria-current=date]') || monthsRoot.querySelector('button');
    initialDay.tabIndex = 0;
    monthsRoot.hidden = false;
    status.textContent = data.months.some(month => month.days.some(day => day.total)) ? '' : 'За этот год пока нет привычек.';
    resetDetail();
}
async function loadYear(force = false) {
    const request = ++generation;
    const requestedYear = year;
    controller?.abort();
    controller = new AbortController();
    previous.disabled = year === minYear;
    next.disabled = year === maxYear;
    yearSelect.value = String(year);
    document.getElementById('yearCalendarTitle').textContent = `Год в привычках · ${year}`;
    retry.hidden = true;
    if (force) cache.delete(year);
    const cached = cache.get(year);
    if (cached && Date.now() - cached.savedAt < 30000) {
        render(cached.data);
        calendarView.removeAttribute('aria-busy');
        return;
    }
    monthsRoot.hidden = true;
    resetDetail();
    calendarView.setAttribute('aria-busy', 'true');
    status.textContent = 'Загрузка календаря…';
    try {
        const url = switcher.dataset.summaryUrl.replace('/2020/', `/${requestedYear}/`);
        const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
        if (!response.ok || response.redirected) throw new Error();
        const data = await response.json();
        if (request !== generation) return;
        if (data.year !== requestedYear || data.months?.length !== 12) throw new Error();
        cache.set(requestedYear, {data, savedAt: Date.now()});
        render(data);
    } catch (error) {
        if (request !== generation || error.name === 'AbortError') return;
        status.textContent = 'Не удалось загрузить календарь. Попробуйте ещё раз.';
        retry.hidden = false;
    } finally {
        if (request === generation) calendarView.removeAttribute('aria-busy');
    }
}
function setView(value) {
    mode = value === 'year' ? 'year' : 'table';
    document.documentElement.classList.toggle('habitus-year-view', mode === 'year');
    tableView.hidden = mode === 'year';
    calendarView.hidden = mode !== 'year';
    for (const button of viewButtons) button.setAttribute('aria-pressed', String(button.dataset.trackerView === mode));
    rememberView(mode);
    updateUrl();
    if (mode === 'year') loadYear();
    else {
        generation++;
        controller?.abort();
        // The mobile table may have been hidden during a viewport resize.
        window.dispatchEvent(new Event('resize'));
    }
}
function changeYear(value) {
    if (!Number.isInteger(value) || value < minYear || value > maxYear || value === year) return;
    year = value;
    updateUrl();
    loadYear();
}
for (let value = minYear; value <= maxYear; value++) {
    const option = document.createElement('option');
    option.value = String(value);
    option.textContent = String(value);
    yearSelect.append(option);
}
for (const button of viewButtons) button.addEventListener('click', () => setView(button.dataset.trackerView));
switcher.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const button = viewButtons.find(item => item !== event.target);
    button.focus();
    setView(button.dataset.trackerView);
});
yearSelect.addEventListener('change', () => changeYear(Number(yearSelect.value)));
previous.addEventListener('click', () => changeYear(year - 1));
next.addEventListener('click', () => changeYear(year + 1));
retry.addEventListener('click', () => loadYear(true));
monthsRoot.addEventListener('click', event => {
    const button = event.target.closest('button[data-date]');
    if (!button) return;
    if (selectedDate) monthsRoot.querySelector(`[data-date="${selectedDate}"]`)?.setAttribute('aria-pressed', 'false');
    selectedDate = button.dataset.date;
    button.setAttribute('aria-pressed', 'true');
    detailText.textContent = button.title;
    detail.hidden = false;
    monthLink.href = monthUrl(Number(button.dataset.month));
    monthLink.hidden = false;
});
monthsRoot.addEventListener('focusin', event => {
    if (!event.target.matches('button[data-date]')) return;
    monthsRoot.querySelector('button[tabindex="0"]')?.setAttribute('tabindex', '-1');
    event.target.tabIndex = 0;
});
monthsRoot.addEventListener('keydown', event => {
    const steps = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7};
    if (steps[event.key] === undefined || !event.target.matches('button[data-date]')) return;
    event.preventDefault();
    const buttons = [...monthsRoot.querySelectorAll('button[data-date]')];
    const index = buttons.indexOf(event.target);
    buttons[Math.max(0, Math.min(buttons.length - 1, index + steps[event.key]))].focus();
});
monthLink.addEventListener('click', () => rememberView('table'));
function invalidateCurrentYear(refresh) {
    const changedYear = Number(switcher.dataset.year);
    cache.delete(changedYear);
    if (refresh && mode === 'year' && year === changedYear) loadYear(true);
}
window.addEventListener('habitus:activity-marked', () => invalidateCurrentYear(false));
window.addEventListener('habitus:activities-saved', () => invalidateCurrentYear(true));
window.addEventListener('habitus:rows-changed', () => invalidateCurrentYear(true));
const params = new URLSearchParams(location.search);
const requestedYear = Number(params.get('year'));
if (Number.isInteger(requestedYear) && requestedYear >= minYear && requestedYear <= maxYear) year = requestedYear;
setView(params.get('view') || storedView() || 'table');
