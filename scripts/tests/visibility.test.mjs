import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const script = readFileSync(new URL('../../hwyd/static/hwyd/js/visibility.js', import.meta.url), 'utf8')
    .replace(/^import .*;\r?\n/gm, '').replace('export function', 'function');

function element(dataset = {}) {
    const handlers = new Map();
    const attrs = new Map();
    const icon = {};
    return {
        dataset, style: {}, hidden: false, disabled: false,
        classList: { toggle() {} },
        addEventListener: (type, fn) => handlers.set(type, fn),
        setAttribute: (name, value) => attrs.set(name, value),
        getAttribute: name => attrs.get(name), querySelector: () => icon,
        click() { handlers.get('click')?.({}); },
    };
}

function row(id, { group = false, completed = false, collapsed = false, groupId = '', animated = false } = {}) {
    const item = element({ activityId: String(id), isGroup: String(group), completed: String(completed),
        groupCollapsed: String(collapsed), groupId: String(groupId) });
    const header = element();
    item.querySelector = () => header;
    item.animations = [];
    if (animated) item.animate = (frames, options) => {
        const animation = { frames, options, cancelled: false, cancel() { this.cancelled = true; } };
        item.animations.push(animation);
        return animation;
    };
    return item;
}

function controls(rows, { hideCompleted = true, eyeEnabled = true, groupsEnabled = true, preview = false,
    vanishing = hideCompleted ? 'sharp' : 'off', reducedMotion = false,
    post = async () => ({ groups: [], collapsed: false }) } = {}) {
    const eye = element({ enabled: String(eyeEnabled) });
    const openAll = element({ enabled: String(groupsEnabled) });
    const table = element({ hideCompleted: String(hideCompleted), vanishing, currentDay: '23', manualGroups: 'true',
        openAllUrl: '/open-all', openGroupUrl: '/open-group' });
    table.querySelectorAll = () => rows;
    const listeners = new Map();
    const errors = [];
    const context = vm.createContext({
        document: { getElementById: id => id === 'openAll' ? openAll : eye },
        window: { addEventListener: (type, fn) => listeners.set(type, fn),
            matchMedia: () => ({ matches: reducedMotion }) }, isViewAs: preview,
    });
    vm.runInContext(script, context);
    const api = context.createVisibilityControls(table, post, (...args) => errors.push(args));
    const mark = (item, completed, day = 23, error = null) =>
        listeners.get('habitus:activity-marked')({ detail: { row: item, completed, day, error } });
    return { eye, openAll, table, errors, mark, refresh: api.refresh,
        changed: () => listeners.get('habitus:rows-changed')() };
}

test('groups and completed habits independently control visibility, including empty collapsed groups', () => {
    for (const group of [false, true]) for (const completed of [false, true]) {
        const rows = [row(1, { completed })];
        if (group) rows.push(row(2, { group: true, collapsed: true }));
        const view = controls(rows);
        assert.equal(view.eye.hidden, !completed);
        assert.equal(view.openAll.hidden, !group);
        assert.equal(view.openAll.style.display, group ? 'flex' : 'none');
    }
    assert.equal(controls([row(1, { group: true, completed: true })]).eye.hidden, true);
});

test('first, multiple and last completions update without resetting the chosen filter', () => {
    const a = row(1), b = row(2);
    const view = controls([a, b]);
    assert.equal(view.eye.hidden, true);
    view.mark(a, true);
    assert.equal(view.eye.hidden, false);
    assert.equal(a.hidden, true);
    view.eye.click();
    assert.equal(a.hidden, false);
    assert.equal(view.eye.title, 'Скрыть выполненные');
    assert.equal(view.eye.getAttribute('aria-label'), view.eye.title);
    assert.equal(view.eye.getAttribute('aria-pressed'), 'true');
    view.mark(b, true);
    view.mark(a, false);
    assert.equal(view.eye.hidden, false);
    view.mark(b, false);
    assert.equal(view.eye.hidden, true);
    view.mark(a, true);
    assert.equal(view.eye.hidden, false);
    assert.equal(a.hidden, false);
    assert.equal(view.eye.getAttribute('aria-pressed'), 'true');
});

test('hidden completed members and collapsed groups remain available to both controls', () => {
    const group = row(1, { group: true, collapsed: true });
    const habit = row(2, { completed: true, groupId: 1 });
    const view = controls([group, habit], { preview: true });
    assert.equal(habit.hidden, true);
    assert.equal(view.eye.hidden, false);
    view.eye.click();
    assert.equal(habit.hidden, true);
    view.openAll.click();
    assert.equal(habit.hidden, false);
    assert.equal(view.openAll.title, 'Свернуть все группы');
    assert.equal(view.openAll.getAttribute('aria-label'), view.openAll.title);
    assert.equal(view.openAll.disabled, false);
    view.openAll.click();
    assert.equal(habit.hidden, true);
    assert.equal(view.openAll.title, 'Раскрыть все группы');
});

test('settings still hide controls even after completion and row changes', () => {
    const habit = row(1);
    const rows = [habit];
    const view = controls(rows, { eyeEnabled: false, groupsEnabled: false });
    view.mark(habit, true);
    rows.push(row(2, { group: true }));
    view.changed();
    assert.equal(view.eye.hidden, true);
    assert.equal(view.openAll.hidden, true);
    assert.equal(view.openAll.style.display, 'none');
});

test('row changes recompute availability and stale or other-day mark events are ignored', () => {
    const habit = row(1, { completed: true });
    const rows = [habit, row(2, { group: true })];
    const view = controls(rows);
    rows.splice(0);
    view.changed();
    assert.equal(view.eye.hidden, true);
    assert.equal(view.openAll.hidden, true);
    view.mark(habit, true);
    assert.equal(view.eye.hidden, true);
    rows.push(row(3));
    view.changed();
    view.mark(rows[0], true, 22);
    assert.equal(view.eye.hidden, true);
    rows.push(row(4, { group: true }));
    view.changed();
    assert.equal(view.openAll.hidden, false);
});

test('failed optimistic marks restore both completion visibility and the filter state', () => {
    const habit = row(1);
    const view = controls([habit], { hideCompleted: false });
    view.mark(habit, true);
    view.mark(habit, false, 23, 'Ошибка сохранения');
    assert.equal(view.eye.hidden, true);
    assert.equal(habit.dataset.completed, 'false');
    assert.equal(habit.hidden, false);
    assert.deepEqual(view.errors, [['Ошибка сохранения', 'error']]);
    view.mark(habit, true);
    assert.equal(habit.hidden, false);
});

test('pending and failed group requests preserve labels, disabled and group state', async () => {
    let reject;
    const group = row(1, { group: true, collapsed: true });
    const view = controls([group], { post: () => new Promise((_, fail) => { reject = fail; }) });
    view.openAll.click();
    assert.equal(view.openAll.disabled, true);
    assert.equal(view.openAll.hidden, false);
    reject(new Error('Ошибка групп'));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(group.dataset.groupCollapsed, 'true');
    assert.equal(view.openAll.disabled, false);
    assert.equal(view.openAll.title, 'Раскрыть все группы');
    assert.deepEqual(view.errors, [['Ошибка групп', 'error']]);
});

test('the toolbar guide cannot reveal controls without matching context data', () => {
    const source = readFileSync(new URL('../../hwyd/static/hwyd/js/utils.js', import.meta.url), 'utf8')
        .replace('export function', 'function');
    const button = element({ contextAvailable: 'false' });
    button.hidden = true;
    button.style.display = 'none';
    const context = vm.createContext({
        document: { querySelector: () => button },
        getComputedStyle() { throw new Error('Unavailable controls must not be revealed'); },
    });
    vm.runInContext(source, context);
    context.forceShowHiddenButtons(['#openAll', '#hideCompleteActivities'])();
    assert.equal(button.hidden, true);
    assert.equal(button.style.display, 'none');
});

test('off keeps a newly completed habit visible and reveals the eye immediately', () => {
    const habit = row(1, { animated: true });
    const view = controls([habit], { vanishing: 'off', hideCompleted: false });
    assert.equal(view.eye.hidden, true);
    view.mark(habit, true);
    assert.equal(view.eye.hidden, false);
    assert.equal(habit.hidden, false);
    assert.equal(habit.animations.length, 0);
    view.mark(habit, false);
    assert.equal(view.eye.hidden, true);
    assert.equal(habit.hidden, false);
});

test('sharp hides immediately without an animation or delay', () => {
    const habit = row(1, { animated: true });
    const view = controls([habit], { vanishing: 'sharp' });
    view.mark(habit, true);
    assert.equal(view.eye.hidden, false);
    assert.equal(habit.hidden, true);
    assert.equal(habit.animations.length, 0);
});

test('smooth starts fading immediately and hides only after the short animation finishes', () => {
    const habit = row(1, { animated: true });
    const view = controls([habit], { vanishing: 'smooth' });
    view.mark(habit, true);
    assert.equal(view.eye.hidden, false);
    assert.equal(habit.hidden, false);
    assert.equal(habit.animations.length, 1);
    const animation = habit.animations[0];
    assert.equal(animation.frames[0].opacity, 1);
    assert.equal(animation.frames.at(-1).opacity, 0);
    assert.equal(animation.options.duration, 220);
    view.refresh();
    assert.equal(habit.hidden, false);
    assert.equal(habit.animations.length, 1);
    animation.onfinish();
    assert.equal(habit.hidden, true);
    assert.equal(view.eye.hidden, false);
    view.eye.click();
    assert.equal(habit.hidden, false);
});

test('rollback or showing completed habits cancels a fade and ignores its late completion', () => {
    for (const rollback of [true, false]) {
        const habit = row(1, { animated: true });
        const view = controls([habit], { vanishing: 'smooth' });
        view.mark(habit, true);
        const animation = habit.animations[0];
        if (rollback) view.mark(habit, false, 23, 'Ошибка сохранения');
        else view.eye.click();
        assert.equal(animation.cancelled, true);
        assert.equal(habit.hidden, false);
        animation.onfinish();
        assert.equal(habit.hidden, false);
        assert.equal(view.eye.hidden, rollback);
    }
});

test('reduced motion, collapsed groups and row removal do not leave a fade running', () => {
    const habit = row(1, { animated: true });
    const view = controls([habit], { vanishing: 'smooth', reducedMotion: true });
    view.mark(habit, true);
    assert.equal(habit.hidden, true);
    assert.equal(habit.animations.length, 0);
    const member = row(2, { animated: true, groupId: 3 });
    const group = row(3, { group: true });
    const rows = [member, group];
    const grouped = controls(rows, { vanishing: 'smooth' });
    grouped.mark(member, true);
    group.dataset.groupCollapsed = 'true';
    grouped.changed();
    assert.equal(member.hidden, true);
    assert.equal(member.animations[0].cancelled, true);
    group.dataset.groupCollapsed = 'false';
    grouped.mark(member, false);
    grouped.mark(member, true);
    const fade = member.animations.at(-1);
    rows.splice(0, 1);
    grouped.changed();
    assert.equal(fade.cancelled, true);
});
