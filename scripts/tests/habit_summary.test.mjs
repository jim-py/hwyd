import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../../hwyd/static/hwyd/js/habit-summary.js', import.meta.url), 'utf8')
    .replace(/^import .*;\r?\n/gm, '').replace('export function', 'function');
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return {promise, resolve, reject};
};
const success = () => ({state: 'success', stats: {month: '2026-10', start: '2026-10-01', through: '2026-10-31',
    habit_count: 2, completed: 3, available: 4, percent: 75}, text: '<img src=x onerror=alert(1)>',
    received_at: '2026-11-01T00:30:00Z'});

function setup({preview = false, timezoneReady = Promise.resolve('UTC')} = {}) {
    const nodes = {};
    for (const name of ['Retry', 'Stats', 'Result', 'Status', 'Period', 'Count', 'Marks', 'Percent', 'Text', 'Time']) {
        nodes[name] = Object.assign(new EventTarget(), {dataset: {}, hidden: true, textContent: '', disabled: false});
    }
    const window = new EventTarget();
    window.habitusTimezoneReady = timezoneReady;
    const dialog = {open: true, dataset: {month: '2026-10', summaryUrl: '/habitus/habit-summary/'},
        addEventListener() {}, setAttribute() {}, removeAttribute() {}};
    const state = {pending: false, now: Date.now(), calls: [], timers: []};
    const calendar = new EventTarget();
    const context = vm.createContext({window, isViewAs: preview, requestJSON() { throw Error('Unexpected request'); },
        document: {getElementById: id => id === 'chooseDate' ? calendar : nodes[id.replace('habitSummary', '')],
            querySelector: () => state.pending},
        Date: class extends Date {
            constructor(...args) { super(...(args.length ? args : [state.now])); }
            static now() { return state.now; }
        },
        setTimeout: fn => { state.timers.push(fn); return fn; }, clearTimeout() {},
    });
    vm.runInContext(source, context);
    const view = context.createHabitSummary(dialog, (...args) => {
        const task = deferred();
        state.calls.push({args, ...task});
        return task.promise;
    });
    return {view, nodes, state, dialog, calendar, event: name => window.dispatchEvent(new Event(name)),
        retry: () => nodes.Retry.dispatchEvent(new Event('click'))};
}

test('generates on open only, sends the selected month once and caches the page snapshot', async () => {
    const ui = setup();
    assert.equal(ui.state.calls.length, 0);
    const opened = ui.view.open();
    await tick();
    assert.equal(ui.nodes.Status.dataset.state, 'loading');
    assert.equal(ui.nodes.Retry.disabled, true);
    await ui.view.open();
    ui.retry();
    assert.equal(ui.state.calls.length, 1);
    assert.equal(JSON.stringify(ui.state.calls[0].args), JSON.stringify([
        '/habitus/habit-summary/', {json: true, data: {month: '2026-10'}}]));
    ui.state.calls[0].resolve(success());
    await opened;
    assert.equal(ui.nodes.Percent.textContent, '75%');
    assert.equal(ui.nodes.Text.textContent, success().text);
    assert.equal(ui.nodes.Result.hidden, false);
    assert.equal(ui.nodes.Retry.disabled, false);
    await ui.view.open();
    assert.equal(ui.state.calls.length, 1);
    ui.retry();
    await tick();
    assert.equal(ui.state.calls.length, 2);
    ui.state.calls[1].resolve(success());
    await tick();
});

test('waits for timezone and every pending mark save before capturing the snapshot', async () => {
    const tz = deferred();
    const ui = setup({timezoneReady: tz.promise});
    const opened = ui.view.open();
    await tick();
    assert.equal(ui.state.calls.length, 0);
    ui.state.pending = true;
    tz.resolve('UTC');
    await tick();
    assert.equal(ui.state.calls.length, 0);
    ui.event('habitus:marks-settled');
    await tick();
    assert.equal(ui.state.calls.length, 0);
    ui.state.pending = false;
    ui.event('habitus:marks-settled');
    await tick();
    assert.equal(ui.state.calls.length, 1);
    ui.state.calls[0].resolve(success());
    await opened;
});

test('late responses cannot replace a changed snapshot, month or local day', async () => {
    for (const change of [ui => ui.event('habitus:activity-marked'), ui => ui.event('habitus:rows-changed'),
        ui => { ui.dialog.dataset.month = '2026-11'; }, ui => { ui.state.now += 86400000; },
        ui => ui.calendar.dispatchEvent(new Event('submit'))]) {
        const ui = setup();
        const opened = ui.view.open();
        await tick();
        change(ui);
        ui.state.calls[0].resolve(success());
        await opened;
        assert.equal(ui.nodes.Result.hidden, true);
        assert.equal(ui.nodes.Stats.hidden, true);
        assert.equal(ui.nodes.Status.dataset.state, 'stale');
        assert.equal(ui.state.calls.length, 1);
    }
});

test('changes after success invalidate cached numbers and text without automatic generation', async () => {
    const ui = setup();
    const opened = ui.view.open();
    await tick();
    ui.state.calls[0].resolve(success());
    await opened;
    ui.event('habitus:activity-marked');
    assert.equal(ui.nodes.Stats.hidden, true);
    assert.equal(ui.nodes.Result.hidden, true);
    assert.equal(ui.state.calls.length, 1);
    const reopened = ui.view.open();
    await tick();
    assert.equal(ui.state.calls.length, 2);
    ui.state.calls[1].resolve(success());
    await reopened;
});

test('errors keep exact local stats, respect Retry-After, and never retry automatically', async () => {
    const ui = setup();
    const opened = ui.view.open();
    await tick();
    const error = Object.assign(Error('Лимит'), {retryAfter: '30', result: {
        state: 'unavailable', error: 'Лимит', stats: success().stats}});
    ui.state.calls[0].reject(error);
    await opened;
    assert.equal(ui.nodes.Status.dataset.state, 'unavailable');
    assert.equal(ui.nodes.Percent.textContent, '75%');
    assert.equal(ui.nodes.Result.hidden, true);
    assert.equal(ui.nodes.Retry.disabled, true);
    ui.retry();
    await tick();
    assert.equal(ui.state.calls.length, 1);
    ui.state.now += 31000;
    ui.state.timers.at(-1)();
    assert.equal(ui.nodes.Retry.disabled, false);
    assert.equal(ui.state.calls.length, 1);
    ui.retry();
    await tick();
    assert.equal(ui.state.calls.length, 2);
    ui.state.calls[1].reject(Error('Timeout'));
    await tick();
    assert.equal(ui.nodes.Status.textContent, 'Timeout');
    assert.equal(ui.state.calls.length, 2);
});

test('empty and unavailable days show no fabricated percentage or AI text', async () => {
    for (const state of ['empty', 'no_days']) {
        const ui = setup();
        const opened = ui.view.open();
        await tick();
        ui.state.calls[0].resolve({state, stats: {...success().stats, completed: 0, available: 0, percent: null}});
        await opened;
        assert.equal(ui.nodes.Percent.textContent, 'Нет доступных дней');
        assert.equal(ui.nodes.Result.hidden, true);
        assert.equal(ui.nodes.Status.dataset.state, state);
    }
});

test('closing during generation keeps late content hidden; a later open uses the result', async () => {
    const ui = setup();
    const opened = ui.view.open();
    await tick();
    ui.dialog.open = false;
    ui.state.calls[0].resolve(success());
    await opened;
    assert.equal(ui.nodes.Result.hidden, true);
    ui.dialog.open = true;
    await ui.view.open();
    assert.equal(ui.nodes.Result.hidden, false);
    assert.equal(ui.state.calls.length, 1);
});

test('preview never calls the site summary endpoint', async () => {
    const ui = setup({preview: true});
    await ui.view.open();
    assert.equal(ui.state.calls.length, 0);
});
