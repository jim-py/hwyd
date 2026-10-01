import { getCSRFToken } from '../../site/js/csrf.js';
import { createVisibilityControls } from './visibility.js';
import { showToast } from './toast.js';
import { enableDialogDrag } from './dialog-drag.js';
import { loadTop } from './top.js';

async function post(url, data) {
    const body = data instanceof FormData ? data : new URLSearchParams(data);
    const token = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || getCSRFToken();
    let response;
    try {
        response = await fetch(url, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'X-CSRFToken': token, 'Accept': 'application/json' }, body
        });
    } catch {
        throw new Error('Не удалось связаться с сервером. Попробуйте ещё раз.');
    }
    let result = null;
    if (response.headers.get('Content-Type')?.includes('application/json')) result = await response.json();
    if (!response.ok || response.redirected) {
        throw new Error(result?.error || 'Не удалось выполнить запрос. Попробуйте ещё раз.');
    }
    return result;
}

const visibility = createVisibilityControls(document.getElementById('myTable'), post, showToast);
const openers = new WeakMap();
for (const dialog of document.querySelectorAll('#feedbackModal, #topModal')) {
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
    dialog.addEventListener('click', event => {
        if (dialog.querySelector('form')?.dataset.busy) return;
        if (event.target.closest('[data-dialog-close]')) dialog.close();
        // Native backdrop clicks target the dialog, but padding clicks do not close it.
        if (event.target === dialog) {
            const rect = dialog.getBoundingClientRect();
            if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) {
                if (!dialog.querySelector('form')?.dataset.busy) dialog.close();
            }
        }
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
    if (!/^(202[0-9]|2030)-(0[1-9]|1[0-2])$/.test(dateField.value)) event.preventDefault();
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
