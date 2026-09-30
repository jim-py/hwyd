import { markViewed } from "../api.js";
import { forceShowHiddenButtons } from "../utils.js";

const GUIDE_SLUG = "main_toolbar";

const I18N = {
    next: "Далее",
    prev: "Назад",
    done: "Понятно",
    confirmClose: "Вы точно хотите прервать обучение?"
};

let onboardingStarted = false;
let onboardingLockActive = false;

const ONBOARDING_STEPS = [
    {
        popover: {
            title: '<i class="fa-solid fa-hand-sparkles onboarding-icon"></i> Добро пожаловать!',
            description: `
                Сейчас мы коротко покажем основные кнопки управления трекером привычек.

                <br><br>

                <i class="fa-solid fa-gear onboarding-icon"></i> Некоторые кнопки могут быть отключены в настройках.
                Во время обучения они временно отображаются, чтобы вы могли
                увидеть все возможности интерфейса.

                <br><br>

                Вы всегда можете включить или скрыть их позже в настройках.
            `,
            side: "center",
            align: "center"
        }
    },
    {
        element: "#loginStreak",
        popover: {
            title: '<i class="fa-solid fa-fire onboarding-icon"></i> Стрик посещений',
            description:
                "Показывает, сколько дней подряд вы заходите в приложение. Не прерывайте цепочку!",
            side: "bottom",
            align: "end"
        }
    },
    {
        element: '.calendar-button[title="Создать группу"]',
        popover: {
            title: '<i class="fa-solid fa-layer-group onboarding-icon"></i> Группа привычек',
            description:
                "Позволяет объединять привычки в группы для удобной организации.",
            side: "bottom",
            align: "center"
        }
    },
    {
        element: '.calendar-button[title="Создать активность"]',
        popover: {
            title: '<i class="fa-solid fa-plus onboarding-icon"></i> Новая привычка',
            description:
                "Создаёт новую привычку или задачу, которую вы хотите отслеживать.",
            side: "bottom",
            align: "center"
        }
    },
    {
        element: "#btnActLastMonth",
        popover: {
            title: '<i class="fa-solid fa-clock-rotate-left onboarding-icon"></i> Повтор прошлого месяца',
            description:
                "Автоматически создаёт привычки на основе прошлого месяца. Кнопка появляется только когда привычек ещё нет.",
            side: "bottom",
            align: "center"
        }
    },
    {
        element: '.calendar-button[onclick*="calendarModal"]',
        popover: {
            title: '<i class="fa-solid fa-calendar onboarding-icon"></i> Календарь',
            description:
                "Быстрый переход к любому месяцу. Можно просматривать прошлые периоды.",
            side: "bottom",
            align: "center"
        }
    },
    {
        element: "#openAll",
        popover: {
            title: '<i class="fa-solid fa-folder-open onboarding-icon"></i> Управление группами',
            description:
                "Позволяет раскрыть или свернуть сразу все группы привычек.",
            side: "bottom",
            align: "center"
        }
    },
    {
        element: "#deleteAll",
        popover: {
            title: '<i class="fa-solid fa-trash onboarding-icon"></i> Очистить привычки',
            description:
                "Удаляет все привычки выбранного периода. Кнопка появляется только когда очистка доступна.",
            side: "bottom",
            align: "center"
        }
    },
    {
        element: "#hideCompleteActivities",
        popover: {
            title: '<i class="fa-solid fa-eye onboarding-icon"></i> Выполненные привычки',
            description:
                "Позволяет скрыть выполненные привычки, чтобы сфокусироваться только на текущих.",
            side: "bottom",
            align: "center"
        }
    },
    {
        element: "#buttonSettings",
        popover: {
            title: '<i class="fa-solid fa-gear onboarding-icon"></i> Настройки',
            description:
                "Здесь находятся настройки отображения, поведения и внешний вид трекера привычек.",
            side: "bottom",
            align: "start"
        }
    },
    {
        popover: {
            title: 'Готово!',
            description: `
                <i class="fa-solid fa-heart onboarding-icon"></i>
                Спасибо, что прошли короткое обучение!

                <br><br>

                Теперь вы знаете основные элементы управления
                трекером привычек и можете начать пользоваться
                приложением максимально эффективно.

                <br><br>

                <i class="fa-solid fa-gear onboarding-icon"></i>
                Помните — большинство кнопок можно включать
                или отключать в настройках под себя.

                <br><br>

                Желаем стабильных привычек,
                длинных стриков
                <i class="fa-solid fa-fire onboarding-icon"></i>
                и отличных результатов!
            `,
            side: "center",
            align: "center"
        }
    }
];

// --- Вспомогательные функции ---
function validateSteps(steps) {
    return steps.filter(step => !step.element || document.querySelector(step.element));
}

function enableOnboardingLock() {
    document.body.classList.add("onboarding-lock");
    onboardingLockActive = true;
}

function disableOnboardingLock() {
    document.body.classList.remove("onboarding-lock");
    onboardingLockActive = false;
}

function blockToolbarEvents(e) {
    if (!onboardingLockActive) return;
    const toolbar = e.target.closest("#divButtons");
    if (!toolbar) return;

    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    return false;
}

// глобальный перехват событий toolbar
document.addEventListener("click", blockToolbarEvents, true);
document.addEventListener("submit", blockToolbarEvents, true);
document.addEventListener("mousedown", blockToolbarEvents, true);
document.addEventListener("touchstart", blockToolbarEvents, true);

// --- Основная функция запуска ---
export async function start() {
    if (onboardingStarted) return;
    onboardingStarted = true;

    const driver = window.driver?.js?.driver;
    if (!driver) {
        console.error("Driver.js не найден");
        return;
    }

    // временно показываем скрытые кнопки
    const restoreButtons = forceShowHiddenButtons([
        "#deleteAll",
        "#openAll",
        "#createLastMonthActivitiesForm",
        "#createActivityButton",
        "#createGroupButton",
        "#calendarButton"
    ]);

    const tour = driver({
        showProgress: false,
        allowClose: false,
        nextBtnText: I18N.next,
        prevBtnText: I18N.prev,
        doneBtnText: I18N.done,
        overlayOpacity: 0.65,
        stagePadding: 8,
        stageRadius: 10,
        popoverClass: "onboarding-popover",
        popoverOffset: window.innerWidth < 640 ? 20 : 12,
        onHighlightStarted: () => {
            if (!onboardingLockActive) enableOnboardingLock();
        },
        onDestroyed: async () => {
            restoreButtons();
            try {
                await markViewed(GUIDE_SLUG);
            } catch (e) {
                console.error("Ошибка сохранения просмотра:", e);
            }
            disableOnboardingLock();
        },
        onCloseClick: () => {
            if (confirm(I18N.confirmClose)) {
                tour.destroy();
            }
        }
    });

    const validSteps = validateSteps([...ONBOARDING_STEPS]);
    if (!validSteps.length) {
        console.warn("Нет доступных шагов onboarding");
        return;
    }

    tour.setSteps(validSteps);
    tour.drive();
}

// --- Автостарт при наличии window.PENDING_GUIDES ---
document.addEventListener("DOMContentLoaded", () => {
    if (window.PENDING_GUIDES?.includes(GUIDE_SLUG)) {
        requestAnimationFrame(() => requestAnimationFrame(start));
    }
});