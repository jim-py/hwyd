import { post } from './api.js';
import { createVisibilityControls } from './visibility.js';
import { showToast } from './toast.js';
import { enableDialogDrag } from './dialog-drag.js?v=20261004-4';
import { loadTop } from './top.js?v=20261005-roles';
import {isViewAs, viewAsURL} from './view-as.js';

const visibility = createVisibilityControls(document.getElementById('myTable'), post, showToast);
const openers = new WeakMap();
// Each section controls only its own checkboxes; radio modes and selects stay independent.
for (const section of document.querySelectorAll('#settingsGlobal .settings-section')) {
    const toggle = section.querySelector('[data-settings-toggle]');
    if (!toggle) continue;
    const options = [...section.querySelectorAll('.settings-dialog__options input[type="checkbox"]')];
    const label = section.querySelector('[data-settings-toggle-label]');
    const title = section.querySelector('h4').textContent;
    const refresh = () => {
        const count = options.filter(option => option.checked).length;
        toggle.checked = count === options.length;
        toggle.indeterminate = count > 0 && count < options.length;
        label.textContent = toggle.checked ? 'Выключить всё' : 'Включить всё';
        toggle.setAttribute('aria-label', `${label.textContent} в разделе «${title}»`);
    };
    toggle.addEventListener('change', () => {
        const checked = toggle.checked;
        for (const option of options) {
            option.checked = checked;
            option.dispatchEvent(new Event('change', {bubbles: true}));
        }
        refresh();
    });
    for (const option of options) option.addEventListener('change', refresh);
    section.closest('form').addEventListener('reset', () => requestAnimationFrame(refresh));
    refresh();
}
for (const dialog of document.querySelectorAll('#feedbackModal, #topModal, .toolbar-dialog[data-desktop-drag]')) {
    enableDialogDrag(dialog);
}
for (const button of document.querySelectorAll('[data-dialog]')) {
    button.addEventListener('click', () => {
        const dialog = document.getElementById(button.dataset.dialog);
        if (!dialog || dialog.open) return;
        openers.set(dialog, button);
        dialog.showModal();
        document.body.classList.add('toolbar-modal-open');
        if (dialog.id === 'calendarModal') resetPicker();
        if (dialog.id === 'topModal') loadTop();
        const focus = dialog.querySelector('[data-initial-focus]') || dialog.querySelector('[data-month][aria-pressed="true"]');
        focus?.focus({ preventScroll: true });
    });
}
for (const dialog of document.querySelectorAll('.toolbar-dialog')) {
    let backdropPress = false;
    const outside = event => {
        const rect = dialog.getBoundingClientRect();
        return event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom;
    };
    dialog.addEventListener('pointerdown', event => {
        backdropPress = event.target === dialog && outside(event);
    });
    dialog.addEventListener('pointercancel', () => { backdropPress = false; });
    dialog.addEventListener('click', event => {
        if (dialog.querySelector('form')?.dataset.busy) return;
        if (event.target.closest('[data-dialog-close]')) dialog.close();
        // Native backdrop clicks target the dialog, but padding clicks do not close it.
        // Releasing a touch/selection that started inside is not a backdrop click.
        if (event.target === dialog && backdropPress && outside(event)) {
            dialog.close();
        }
        backdropPress = false;
    });
    dialog.addEventListener('cancel', event => {
        if (dialog.querySelector('form')?.dataset.busy) event.preventDefault();
    });
    dialog.addEventListener('close', () => {
        if (!document.querySelector('.toolbar-dialog[open]')) document.body.classList.remove('toolbar-modal-open');
        openers.get(dialog)?.focus({ preventScroll: true });
    });
}

// Native form submission preserves the existing creation endpoints and Enter behavior.
for (const input of document.querySelectorAll('.toolbar-dialog input[type="text"], #feedbackMessage')) {
    input.addEventListener('input', () => input.setCustomValidity(''));
    input.form.addEventListener('submit', event => {
        if (!input.value.trim()) {
            event.preventDefault();
            input.setCustomValidity('Введите текст.');
            input.reportValidity();
        }
    });
}

const monthForm = document.getElementById('chooseDate');
const dateField = monthForm.elements.chooseDate;
const initialDate = dateField.value;
const monthButtons = [...monthForm.querySelectorAll('[data-month]')];
let pickerYear, pickerMonth;
function renderPicker() {
    document.getElementById('pickerYear').textContent = pickerYear;
    document.getElementById('previousYear').disabled = pickerYear <= 2020;
    document.getElementById('nextYear').disabled = pickerYear >= 2030;
    dateField.value = `${pickerYear}-${String(pickerMonth).padStart(2, '0')}`;
    for (const button of monthButtons) button.setAttribute('aria-pressed', String(Number(button.dataset.month) === pickerMonth));
    document.getElementById('pickerSelection').textContent = `Выбрано: ${monthButtons[pickerMonth - 1].textContent.toLowerCase()} ${pickerYear}`;
}
function resetPicker() {
    [pickerYear, pickerMonth] = initialDate.split('-').map(Number);
    renderPicker();
}
document.getElementById('previousYear').addEventListener('click', () => {
    pickerYear = Math.max(2020, pickerYear - 1);
    renderPicker();
});
document.getElementById('nextYear').addEventListener('click', () => {
    pickerYear = Math.min(2030, pickerYear + 1);
    renderPicker();
});
for (const button of monthButtons) {
    button.addEventListener('click', () => {
        pickerMonth = Number(button.dataset.month);
        renderPicker();
    });
    button.addEventListener('keydown', event => {
        const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -3, ArrowDown: 3 }[event.key];
        if (delta === undefined) return;
        event.preventDefault();
        const index = (monthButtons.indexOf(button) + delta + 12) % 12;
        monthButtons[index].focus();
    });
}
monthForm.addEventListener('submit', event => {
    const valid = /^(202[0-9]|2030)-(0[1-9]|1[0-2])$/.test(dateField.value);
    if (!valid || isViewAs) event.preventDefault();
    if (valid && isViewAs) {
        const path = document.getElementById('trackerViewSwitch').dataset.monthUrl.replace('2020-01', dateField.value);
        location.assign(viewAsURL(`${path}?view=table`));
    }
});
resetPicker();

function busy(form, value) {
    if (value) form.dataset.busy = 'true';
    else delete form.dataset.busy;
    for (const button of form.closest('dialog').querySelectorAll('button')) button.disabled = value;
}
function bindAsyncForm(form, success) {
    if (!form) return;
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (!form.checkValidity() || form.dataset.busy) return;
        const message = form.elements.message;
        if (message && !message.value.trim()) return;
        const errorBox = form.querySelector('.toolbar-dialog__error');
        errorBox.hidden = true;
        busy(form, true);
        try {
            await post(form.action, new FormData(form));
            success();
            form.closest('dialog').close();
        } catch (error) {
            errorBox.textContent = error.message || 'Не удалось отправить сообщение. Попробуйте ещё раз.';
            errorBox.hidden = false;
        } finally {
            busy(form, false);
        }
    });
}
const feedbackForm = document.getElementById('feedbackForm');
bindAsyncForm(feedbackForm, () => {
    feedbackForm.reset();
    showToast('Спасибо, сообщение отправлено.');
});
bindAsyncForm(document.getElementById('deleteAllForm'), () => {
    document.querySelectorAll('#myTable tbody tr').forEach(row => row.remove());
    document.getElementById('deleteAll').style.display = 'none';
    document.getElementById('openAll').style.display = 'none';
    document.getElementById('createLastMonthActivitiesForm').style.display = 'inline';
    visibility.refresh();
    window.dispatchEvent(new Event('habitus:rows-changed'));
    showToast('Все привычки и группы за выбранный месяц удалены.');
});
