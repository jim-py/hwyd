import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const script = readFileSync(new URL('../../hwyd/static/hwyd/js/toolbar.js', import.meta.url), 'utf8')
    .replace(/^import .*;\r?\n/gm, '');

function toolbar({ sourceAvailable, fails = false }) {
    const listeners = new Map();
    const events = [];
    const error = { hidden: true };
    const rows = [{ removed: false, remove() { this.removed = true; } }];
    const element = () => ({ style: {}, addEventListener() {} });
    const dialog = { querySelectorAll: () => [], close() {} };
    const form = {
        action: '/habitus/delete_all/2026-10', dataset: {}, elements: {},
        addEventListener: (name, fn) => listeners.set(name, fn),
        checkValidity: () => true, querySelector: () => error, closest: () => dialog,
    };
    const copyForm = sourceAvailable ? { style: { display: 'none' } } : null;
    const monthButtons = Array.from({ length: 12 }, (_, index) => ({
        dataset: { month: String(index + 1) }, textContent: String(index + 1),
        setAttribute() {}, addEventListener() {},
    }));
    const elements = {
        deleteAllForm: form, createLastMonthActivitiesForm: copyForm,
        deleteAll: element(), openAll: element(), previousYear: element(), nextYear: element(),
        pickerYear: element(), pickerSelection: element(), 'some-modal-id': element(),
        chooseDate: {
            elements: { chooseDate: { value: '2026-10' } },
            querySelectorAll: () => monthButtons, addEventListener() {},
        },
    };
    vm.runInNewContext(script, {
        document: {
            getElementById: id => elements[id] ?? null,
            querySelectorAll: selector => selector === '#myTable tbody tr' ? rows : [],
        },
        window: { addEventListener() {}, dispatchEvent: event => events.push(event.type) },
        location: { hash: '' }, isViewAs: false,
        createVisibilityControls: () => ({ refresh() {} }), showToast() {},
        post: async () => { if (fails) throw new Error('Не удалось удалить привычки.'); },
        FormData: class {}, Event: class { constructor(type) { this.type = type; } },
    });
    return { copyForm, rows, error, events, submit: () => listeners.get('submit')({ preventDefault() {} }) };
}

test('clearing the current month reveals copying only when a source was confirmed', async () => {
    for (const sourceAvailable of [false, true]) {
        const view = toolbar({ sourceAvailable });
        await view.submit();
        assert.equal(view.rows[0].removed, true);
        assert.equal(view.error.hidden, true);
        assert.deepEqual(view.events, ['habitus:rows-changed']);
        if (sourceAvailable) assert.equal(view.copyForm.style.display, 'inline');
        else assert.equal(view.copyForm, null);
    }
});

test('failed clearing keeps the table and copy visibility unchanged and reports the error', async () => {
    for (const sourceAvailable of [false, true]) {
        const view = toolbar({ sourceAvailable, fails: true });
        await view.submit();
        assert.equal(view.rows[0].removed, false);
        assert.equal(view.error.hidden, false);
        assert.equal(view.error.textContent, 'Не удалось удалить привычки.');
        assert.deepEqual(view.events, []);
        if (sourceAvailable) assert.equal(view.copyForm.style.display, 'none');
    }
});
