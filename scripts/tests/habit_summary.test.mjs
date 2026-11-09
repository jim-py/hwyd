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
const facts = () => ({month: '2026-10', start: '2026-10-01', through: '2026-10-31', snapshot: 'snapshot-a',
    habit_count: 2, completed: 3, available: 4, percent: 75,
    habits: [{name: 'Чтение', completed: 2, available: 2, percent: 100},
        {name: 'Прогулка', completed: 1, available: 2, percent: 50}],
    changes: {improvements: [], declines: []}, regularity: {most_regular: [], least_regular: []}});
const statsResult = () => ({state: 'stats', stats: facts()});
const success = () => ({state: 'success', stats: facts(), ai: {
    summary: '<img src=x onerror=alert(1)>', advice: 'Выбери время для прогулки.'}, received_at: '2026-11-01T00:30:00Z'});

function setup({preview = false, timezoneReady = Promise.resolve('UTC')} = {}) {
    let document;
    class Element extends EventTarget {
        dataset = {}; hidden = true; textContent = ''; disabled = false; children = []; attrs = {};
        setAttribute(name, value) { this.attrs[name] = value; }
        getAttribute(name) { return this.attrs[name]; }
        append(...items) { this.children.push(...items); }
        replaceChildren(...items) { this.children = items; }
        querySelector() { return this.list ||= new Element(); }
        focus() { document.activeElement = this; }
    }
    const nodes = {};
    for (const name of ['Retry', 'Stats', 'StatsStatus', 'Result', 'Status', 'Period', 'Count', 'Marks',
        'Percent', 'Text', 'Advice', 'AdviceText', 'SnapshotHint', 'TabAI', 'TabStats', 'PanelAI', 'PanelStats',
        'Changes', 'ChangesTitle', 'ComparisonPeriod', 'Improvements', 'Declines', 'Most', 'Least', 'Habits']) nodes[name] = new Element();
    const window = new EventTarget();
    window.habitusTimezoneReady = timezoneReady;
    const dialog = {open: true, dataset: {month: '2026-10', summaryUrl: '/habitus/habit-summary/'},
        addEventListener() {}};
    const state = {pending: false, now: Date.now(), calls: [], timers: []};
    const calendar = new EventTarget();
    document = {getElementById: id => id === 'chooseDate' ? calendar : nodes[id.replace('habitSummary', '')],
        querySelector: () => state.pending, createElement: () => new Element()};
    const context = vm.createContext({window, isViewAs: preview, document,
        requestJSON() { throw Error('Unexpected request'); },
        Date: class extends Date {
            constructor(...args) { super(...(args.length ? args : [state.now])); }
            static now() { return state.now; }
        },
        setTimeout: fn => { state.timers.push(fn); return fn; }, clearTimeout() {},
    });
    vm.runInContext(source, context);
    const view = context.createHabitSummary(dialog, (...args) => {
        const task = deferred(); state.calls.push({args, ...task}); return task.promise;
    });
    return {view, nodes, state, dialog, calendar, document,
        event: name => window.dispatchEvent(new Event(name)),
        retry: () => nodes.Retry.dispatchEvent(new Event('click')),
        tab: name => nodes[`Tab${name}`].dispatchEvent(new Event('click'))};
}
async function open(ui, result = statsResult()) {
    const pending = ui.view.open(); await tick();
    ui.state.calls.at(-1).resolve(result); await pending;
}
async function generate(ui, result = success()) {
    ui.retry(); await tick(); ui.state.calls.at(-1).resolve(result); await tick();
}

test('open reads stats only; default AI tab and switching never generate', async () => {
    const ui = setup();
    assert.equal(ui.state.calls.length, 0);
    await open(ui);
    assert.equal(JSON.stringify(ui.state.calls[0].args), JSON.stringify([
        '/habitus/habit-summary/', {json: true, data: {month: '2026-10', generate: false}}]));
    assert.equal(ui.nodes.TabAI.getAttribute('aria-selected'), 'true');
    assert.equal(ui.nodes.PanelStats.hidden, true);
    assert.equal(ui.nodes.Result.hidden, true);
    ui.tab('Stats');
    assert.equal(ui.nodes.PanelStats.hidden, false);
    assert.equal(ui.nodes.PanelAI.hidden, true);
    assert.equal(ui.nodes.Percent.textContent, '75%');
    assert.equal(ui.nodes.Habits.children.length, 2);
    assert.equal(ui.nodes.Habits.children[0].children[1].textContent, '2 / 2 · 100%');
    ui.tab('AI');
    assert.equal(ui.state.calls.length, 1);
});

test('explicit refresh generates once; reopens retain summary and recheck stats without AI', async () => {
    const ui = setup();
    await open(ui);
    ui.retry(); await tick();
    assert.equal(ui.state.calls[1].args[1].data.generate, true);
    assert.equal(ui.nodes.Retry.disabled, true);
    ui.retry(); await ui.view.open();
    assert.equal(ui.state.calls.length, 2);
    ui.state.calls[1].resolve(success()); await tick();
    assert.equal(ui.nodes.Text.textContent, success().ai.summary);
    assert.equal(ui.nodes.AdviceText.textContent, success().ai.advice);
    assert.equal(ui.nodes.Status.hidden, true);
    assert.equal(ui.nodes.Result.hidden, false);
    ui.tab('Stats');
    await open(ui);
    assert.equal(ui.nodes.PanelAI.hidden, false);
    assert.equal(ui.nodes.Result.hidden, false);
    assert.equal(ui.state.calls.filter(call => call.args[1].data.generate).length, 1);
});

test('tabs support arrow, Home and End keys without requests', async () => {
    const ui = setup(); await open(ui);
    const key = (name, value) => {
        const event = new Event('keydown'); Object.defineProperty(event, 'key', {value});
        ui.nodes[`Tab${name}`].dispatchEvent(event);
    };
    key('AI', 'ArrowRight');
    assert.equal(ui.document.activeElement, ui.nodes.TabStats);
    assert.equal(ui.nodes.TabStats.tabIndex, 0);
    assert.equal(ui.nodes.TabAI.tabIndex, -1);
    key('Stats', 'Home');
    assert.equal(ui.document.activeElement, ui.nodes.TabAI);
    key('AI', 'End');
    assert.equal(ui.document.activeElement, ui.nodes.TabStats);
    assert.equal(ui.state.calls.length, 1);
});

test('waits for timezone and all mark saves before stats or generation', async () => {
    const tz = deferred();
    const ui = setup({timezoneReady: tz.promise});
    const pending = ui.view.open(); await tick();
    assert.equal(ui.state.calls.length, 0);
    ui.state.pending = true; tz.resolve('UTC'); await tick();
    assert.equal(ui.state.calls.length, 0);
    ui.event('habitus:marks-settled'); await tick();
    assert.equal(ui.state.calls.length, 0);
    ui.state.pending = false; ui.event('habitus:marks-settled'); await tick();
    ui.state.calls[0].resolve(statsResult()); await pending;
    assert.equal(ui.state.calls.length, 1);
});

test('errors retain the previous successful text and advice; stats remain accessible', async () => {
    const ui = setup(); await open(ui); await generate(ui);
    ui.tab('Stats'); ui.retry(); await tick();
    const result = {state: 'unavailable', stats: {...facts(), percent: 50}, error: 'Сервис недоступен'};
    ui.state.calls.at(-1).reject(Object.assign(Error(result.error), {result})); await tick();
    assert.equal(ui.nodes.PanelStats.hidden, false);
    assert.equal(ui.nodes.Percent.textContent, '50%');
    ui.tab('AI');
    assert.equal(ui.nodes.Text.textContent, success().ai.summary);
    assert.equal(ui.nodes.AdviceText.textContent, success().ai.advice);
    assert.equal(ui.nodes.Result.hidden, false);
    assert.equal(ui.nodes.Status.textContent, result.error);
    assert.equal(ui.state.calls.length, 3);
});

test('stale generated response never replaces saved AI; only changed stats refresh automatically', async () => {
    const ui = setup(); await open(ui); await generate(ui);
    ui.retry(); await tick();
    ui.event('habitus:activity-marked');
    assert.equal(ui.nodes.SnapshotHint.hidden, false);
    assert.equal(ui.nodes.Result.hidden, false);
    ui.state.calls.at(-1).resolve({...success(), ai: {summary: 'STALE', advice: 'STALE'}}); await tick();
    assert.equal(ui.nodes.Text.textContent, success().ai.summary);
    assert.equal(ui.state.calls.at(-1).args[1].data.generate, false);
    ui.state.calls.at(-1).resolve({...statsResult(), stats: {...facts(), snapshot: 'snapshot-b'}}); await tick();
    assert.equal(ui.nodes.SnapshotHint.hidden, false);
    assert.equal(ui.state.calls.filter(call => call.args[1].data.generate).length, 2);
});

test('changed month or local day discards a late AI response', async () => {
    for (const change of [ui => { ui.dialog.dataset.month = '2026-11'; }, ui => { ui.state.now += 86400000; },
        ui => ui.calendar.dispatchEvent(new Event('submit'))]) {
        const ui = setup(); await open(ui);
        ui.retry(); await tick(); change(ui);
        ui.state.calls.at(-1).resolve(success()); await tick();
        assert.equal(ui.nodes.Result.hidden, true);
        if (ui.state.calls.at(-1).args[1].data.generate === false) {
            assert.equal(ui.nodes.Status.dataset.state, 'loading');
            ui.state.calls.at(-1).resolve(statsResult()); await tick();
        } else {
            assert.equal(ui.nodes.Status.dataset.state, 'stale');
        }
    }
});

test('Retry-After blocks generation, allows stats reads, and never retries AI automatically', async () => {
    const ui = setup(); await open(ui); await generate(ui);
    ui.retry(); await tick();
    ui.state.calls.at(-1).reject(Object.assign(Error('Лимит'), {retryAfter: '30', result: {state: 'unavailable', stats: facts()}}));
    await tick();
    assert.equal(ui.nodes.Retry.disabled, true);
    ui.retry(); await tick();
    assert.equal(ui.state.calls.length, 3);
    await open(ui);
    assert.equal(ui.state.calls.at(-1).args[1].data.generate, false);
    ui.state.now += 31000; ui.state.timers.at(-1)();
    assert.equal(ui.nodes.Retry.disabled, false);
    assert.equal(ui.state.calls.length, 4);
});

test('backend change categories are independent of AI and empty comparisons stay hidden', async () => {
    const ui = setup();
    const stats = {...facts(), changes: {improvements: [{name: 'Чтение', delta_pp: 40}], declines: []},
        comparison_period: {previous_start: '2026-10-18', previous_end: '2026-10-24', current_start: '2026-10-25', current_end: '2026-10-31'}};
    await open(ui, {state: 'stats', stats});
    assert.equal(ui.nodes.Changes.hidden, false);
    assert.equal(ui.nodes.Improvements.hidden, false);
    assert.equal(ui.nodes.Declines.hidden, true);
    assert.equal(ui.nodes.Improvements.list.children[0].children[1].textContent, '+40 п.п.');
    assert.equal(ui.nodes.Result.hidden, true);
    await open(ui);
    assert.equal(ui.nodes.Changes.hidden, true);
});

test('relative current rates use neutral labels; zero denominator is never zero percent', async () => {
    const ui = setup();
    await open(ui, {state: 'stats', stats: {...facts(), regularity: {
        most_regular: [{name: 'Чтение', percent: 100}], least_regular: [{name: 'Прогулка', percent: 50}]}}});
    assert.equal(ui.nodes.ChangesTitle.textContent, 'В этом периоде');
    assert.equal(ui.nodes.Most.hidden, false);
    assert.equal(ui.nodes.Improvements.hidden, true);
    await open(ui, {state: 'no_days', stats: {...facts(), completed: 0, available: 0, percent: null}});
    assert.equal(ui.nodes.Percent.textContent, '—');
    assert.equal(ui.nodes.Result.hidden, true);
});

test('closing during generation preserves result for next open and keeps tabs independent', async () => {
    const ui = setup(); await open(ui);
    ui.retry(); await tick(); ui.dialog.open = false;
    ui.state.calls.at(-1).resolve(success()); await tick();
    ui.dialog.open = true; await open(ui);
    assert.equal(ui.nodes.Result.hidden, false);
    assert.equal(ui.state.calls.filter(call => call.args[1].data.generate).length, 1);
});

test('preview never requests stats or AI', async () => {
    const ui = setup({preview: true}); await ui.view.open(); ui.retry(); await tick();
    assert.equal(ui.state.calls.length, 0);
});
