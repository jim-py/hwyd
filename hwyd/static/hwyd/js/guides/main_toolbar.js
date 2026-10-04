import { markViewed } from '../api.js';
import { forceShowHiddenButtons } from '../utils.js';
import { showToast } from '../toast.js';

let active = null;
const controls = [
    ['#buttonSettings', 'Настройки Habitus', 'Выберите видимые кнопки, шрифт, звуки и поведение таблицы. Здесь же можно повторно открыть обучение.'],
    ['#buttonTheme', 'Тема', 'Переключает тему интерфейса.'],
    ['#themeScheduleButton', 'Расписание тем', 'Сохраните текущие цвета под своим названием и назначьте время автоматического включения в вашем часовом поясе. Можно хранить несколько тем, менять время и выключать расписание.'],
    ['#createActivityButton', 'Новая привычка', 'Создайте привычку для отслеживания в выбранном месяце.'],
    ['#createGroupButton', 'Группа привычек', 'Создайте группу, затем добавьте в неё привычки через настройки группы.'],
    ['#calendarButton', 'Выбор месяца', 'Откройте календарь, выберите месяц и перейдите к его таблице.'],
    ['#hideCompleteActivities', 'Выполненные привычки', 'Показывает или скрывает привычки, выполненные сегодня. Свёрнутые группы сохраняют своё состояние.'],
    ['#openAll', 'Управление группами', 'Раскрывает все свёрнутые группы или сворачивает все раскрытые.'],
    ['#loginStreak', 'Стрик посещений', 'Число последовательных дней посещения приложения в последней цепочке. Посещение после пропущенного дня начинает новую цепочку.'],
    ['#topStreak', 'Top по стрику', 'Число рядом с Top — ваше место по текущему стрику посещений. Нажмите, чтобы увидеть Top-10. При равном стрике порядок определяется именем пользователя. Кнопку можно скрыть в настройках.'],
    ['#buttonChat', 'Общий чат', 'Общайтесь, отвечайте на сообщения и редактируйте свои. На компьютере окно можно перемещать и менять его размер, на телефоне оно занимает весь экран.'],
    ['#buttonFeedback', 'Обратная связь', 'Сообщите об ошибке, предложите улучшение или оставьте отзыв.'],
    ['#btnActLastMonth', 'Привычки прошлого месяца', 'Копирует привычки и группы прошлого месяца без отметок. Обычно кнопка доступна, когда таблица выбранного месяца пуста.'],
    ['#deleteAll', 'Очистить месяц', 'Открывает подтверждение удаления всех привычек, групп, отметок и комментариев выбранного месяца. До подтверждения ничего не удаляется.'],
    ['#trackerViewSwitch', 'Вид привычек: Таблица / Год', '«Таблица» — привычная таблица месяца, в которой можно отмечать выполнение. «Год» заменяет её календарём за весь год: заполненность кружка показывает процент выполненных привычек среди доступных в этот день. Выберите день, чтобы увидеть результат и перейти к его месяцу. Переключатель можно скрыть в настройках.'],
];

function controlsInVisualOrder() {
    const positioned = controls.flatMap(control => {
        const element = document.querySelector(control[0]);
        if (!element || !element.getClientRects().length) return [];
        const rect = element.getBoundingClientRect();
        if (!rect.width || !rect.height || getComputedStyle(element).visibility === 'hidden') return [];
        return [{ control, rect }];
    }).sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);

    // Flex rows can wrap on mobile, and buttons in one row can differ in height.
    // Group overlapping vertical bounds before ordering each row left to right.
    const rows = [];
    for (const item of positioned) {
        const row = rows[rows.length - 1];
        if (row && item.rect.top < row.bottom && item.rect.bottom > row.top) {
            row.items.push(item);
            row.top = Math.max(row.top, item.rect.top);
            row.bottom = Math.min(row.bottom, item.rect.bottom);
        } else {
            rows.push({ top: item.rect.top, bottom: item.rect.bottom, items: [item] });
        }
    }
    return rows.flatMap(row => row.items.sort((a, b) => a.rect.left - b.rect.left).map(item => item.control));
}

export function start() {
    if (active) return active;
    const driver = window.driver?.js?.driver;
    if (!driver) return Promise.reject(new Error('Driver.js не загружен'));
    let resolve;
    active = new Promise(done => { resolve = done; });
    const result = active;
    const focus = document.activeElement;
    const scroll = { left: window.scrollX, top: window.scrollY };
    const wasLocked = document.body.classList.contains('onboarding-lock');
    let restore = () => {};
    let cleaned = false;
    let completed = false;
    let dismissed = false;
    let started = false;
    let tour = null;
    const eventTypes = ['click', 'submit', 'pointerdown', 'contextmenu', 'keydown'];
    function blockActions(event) {
        if (!event.target.closest('#divButtons, .nav-menu, #myTable, #trackerViewSwitch')) return;
        if (event.type === 'keydown' && !['Enter', ' ', 'ContextMenu'].includes(event.key)) return;
        event.preventDefault();
        event.stopImmediatePropagation();
    }
    function cleanup() {
        if (cleaned) return;
        cleaned = true;
        restore();
        if (!wasLocked) document.body.classList.remove('onboarding-lock');
        for (const type of eventTypes) document.removeEventListener(type, blockActions, true);
        window.scrollTo(scroll);
        focus?.focus({ preventScroll: true });
        active = null;
        resolve();
        if (started && !completed) {
            showToast('Повторить гайд можно через «Настройки → Обучение».');
        }
        if (completed || dismissed) {
            markViewed('main_toolbar').catch(error => {
                console.error('Guide progress:', error);
                showToast('Не удалось сохранить просмотр гайда. После обновления обучение может открыться снова.', 'error');
            });
        }
    }
    try {
        // The navbar is already expanded on mobile. Reveal existing controls
        // and containers only; no fake buttons and no settings requests.
        restore = forceShowHiddenButtons([...controls.map(([selector]) => selector), '#createLastMonthActivitiesForm']);
        document.body.classList.add('onboarding-lock');
        for (const type of eventTypes) document.addEventListener(type, blockActions, true);
        const steps = [
            { popover: { title: 'Добро пожаловать в Habitus', description: 'Отмечайте привычки в таблице и объединяйте их в группы. Пройдём по кнопкам сверху вниз, в каждом ряду — слева направо. Скрытые кнопки временно показаны; ваши настройки сохранятся.' } },
            ...controlsInVisualOrder().map(([element, title, description]) => ({
                element, popover: { title, description, side: 'bottom', align: 'center' },
            })),
            { popover: { title: 'Можно начинать', description: 'Создайте привычку и отмечайте её выполнение. Повторить этот обзор можно через «Настройки → Обучение».' } },
        ];
        const finish = () => {
            // Driver can omit onDestroyed when closed mid-transition, before
            // its first active element is committed. Always restore explicitly.
            try { tour.destroy(); } finally { cleanup(); }
        };
        tour = driver({
            steps, showProgress: true, progressText: '{{current}} из {{total}}',
            nextBtnText: 'Далее', prevBtnText: 'Назад', doneBtnText: 'Готово',
            allowClose: true, disableActiveInteraction: true,
            overlayClickBehavior: () => {},
            animate: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
            overlayOpacity: 0.65, stagePadding: 6, stageRadius: 10,
            popoverClass: 'onboarding-popover', popoverOffset: 12,
            onNextClick: () => {
                if (tour.hasNextStep()) tour.moveNext();
                else { completed = true; finish(); }
            },
            onCloseClick: () => { dismissed = true; finish(); },
            // Ignore implicit dismissal (Escape); the cross calls finish directly.
            onDestroyStarted: () => {},
            onDestroyed: cleanup,
        });
        tour.drive();
        started = true;
    } catch (error) {
        try { tour?.destroy(); } catch { /* cleanup also covers partial initialization */ }
        cleanup();
        return Promise.reject(error);
    }
    return result;
}
