import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const template = readFileSync(new URL('../../hwyd/templates/hwyd/scripts.html', import.meta.url), 'utf8');
const script = template.match(/{% if settings.showActivityDayLight %}([\s\S]*?){% endif %}/)[1];

function table({deletion = false, days = 31} = {}) {
    const month = {style: {}};
    const headings = Array.from({length: days}, (_, index) => ({day: index + 1, style: {}}));
    const header = day => ({querySelector(selector) {
        assert.equal(selector, 'p.headParagraph.minor');
        return day;
    }});
    const cells = [...(deletion ? [header(null)] : []), header(null), ...headings.map(header)];
    const table = {tHead: {rows: [{cells}]}};
    const bodyCells = cells.map((_, cellIndex) => ({cellIndex, closest(selector) {
        assert.equal(selector, 'table');
        return table;
    }}));
    let enter, leave;
    const $ = target => {
        if (target === '.table td') return {hover(onEnter, onLeave) { enter = onEnter; leave = onLeave; }};
        const elements = target === '.table th p' ? [month, ...headings] : [target];
        return {css(property, value) { for (const element of elements) element.style[property] = value; }};
    };
    vm.runInNewContext(script, {$, document: {addEventListener(type, callback) {
        assert.equal(type, 'DOMContentLoaded'); callback();
    }}});
    return {month, headings, bodyCells, enter(index) { enter.call(bodyCells[index]); },
        leave(index) { leave.call(bodyCells[index]); }};
}

for (const deletion of [false, true]) {
    test(`every day highlights its own heading with deletion ${deletion ? 'shown' : 'hidden'}`, () => {
        for (const days of [28, 29, 30, 31]) {
            const view = table({deletion, days});
            const offset = deletion ? 2 : 1;
            for (let day = 0; day < days; day++) {
                view.enter(day + offset);
                assert.deepEqual(view.headings.filter(heading => heading.style.border), [view.headings[day]]);
                assert.equal(view.headings[day].style['box-shadow'], '0 0 3px -1px rgb(0, 0, 0) inset');
                assert.equal(view.month.style.border || '', '');
                view.leave(day + offset);
                assert.ok(view.headings.every(heading => heading.style.border === '' && heading.style['box-shadow'] === ''));
            }
        }
    });

    test(`name and deletion cells never highlight a day with deletion ${deletion ? 'shown' : 'hidden'}`, () => {
        const view = table({deletion});
        for (let index = 0; index < (deletion ? 2 : 1); index++) {
            view.enter(index);
            assert.ok(view.headings.every(heading => !heading.style.border));
            assert.equal(view.month.style.border || '', '');
            view.leave(index);
        }
    });
}
