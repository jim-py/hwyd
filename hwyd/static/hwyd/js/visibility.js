import {isViewAs} from './view-as.js';

// Group collapse and completed visibility are independent states.
export function createVisibilityControls(table, post, showToast) {
    const eye = document.getElementById('hideCompleteActivities');
    const openAll = document.getElementById('openAll');
    let hideCompleted = table.dataset.hideCompleted === 'true';
    const vanishing = table.dataset.vanishing;
    const fades = new Map();
    let pending = false;
    const rows = () => [...table.querySelectorAll('tbody tr[data-activity-id]')];
    const groups = () => rows().filter(row => row.dataset.isGroup === 'true');

    function cancelFade(row) {
        const animation = fades.get(row);
        fades.delete(row);
        animation?.cancel();
    }

    function setCompletedHidden(row, hidden, animate) {
        if (!hidden) {
            cancelFade(row);
            row.hidden = false;
            return;
        }
        if (row.hidden || fades.has(row)) return;
        if (!animate || !row.animate || window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches) {
            row.hidden = true;
            return;
        }
        const animation = row.animate([
            { opacity: 1, transform: 'translateY(0)' },
            { opacity: 0, transform: 'translateY(-3px)' },
        ], { duration: 220, easing: 'cubic-bezier(0.2, 0, 0, 1)' });
        fades.set(row, animation);
        animation.onfinish = () => {
            if (fades.get(row) !== animation) return;
            fades.delete(row);
            row.hidden = true;
            animation.cancel();
        };
    }

    function render(animateRow = null) {
        const currentRows = rows();
        for (const row of fades.keys()) if (!currentRows.includes(row)) cancelFade(row);
        const groupRows = currentRows.filter(row => row.dataset.isGroup === 'true');
        const groupMap = new Map(groupRows.map(row => [row.dataset.activityId, row]));
        const hasCompleted = currentRows.some(row => row.dataset.isGroup !== 'true' && row.dataset.completed === 'true');
        eye.dataset.contextAvailable = String(hasCompleted);
        eye.hidden = eye.dataset.enabled === 'false' || !hasCompleted;
        openAll.dataset.contextAvailable = String(groupRows.length > 0);
        openAll.hidden = openAll.dataset.enabled === 'false' || groupRows.length === 0;
        openAll.style.display = openAll.hidden ? 'none' : 'flex';
        for (const row of currentRows) {
            if (row.dataset.isGroup === 'true') {
                const collapsed = row.dataset.groupCollapsed === 'true';
                const header = row.querySelector('td.header');
                header.classList.toggle('expand', collapsed);
                if (table.dataset.manualGroups === 'true') {
                    header.setAttribute('aria-expanded', String(!collapsed));
                    header.setAttribute('aria-disabled', String(pending));
                }
                continue;
            }
            const group = groupMap.get(row.dataset.groupId);
            if (group?.dataset.groupCollapsed === 'true') {
                cancelFade(row);
                row.hidden = true;
            } else {
                setCompletedHidden(row, hideCompleted && row.dataset.completed === 'true',
                    vanishing === 'smooth' && row === animateRow);
            }
        }
        const eyeLabel = hideCompleted ? 'Показать выполненные' : 'Скрыть выполненные';
        eye.title = eyeLabel;
        eye.setAttribute('aria-label', eyeLabel);
        eye.setAttribute('aria-pressed', String(!hideCompleted));
        eye.querySelector('i').className = `fa-solid ${hideCompleted ? 'fa-eye' : 'fa-eye-slash'}`;
        const expand = groupRows.some(row => row.dataset.groupCollapsed === 'true');
        const groupLabel = expand ? 'Раскрыть все группы' : 'Свернуть все группы';
        openAll.title = groupLabel;
        openAll.setAttribute('aria-label', groupLabel);
        openAll.querySelector('i').className = `fa-solid ${expand ? 'fa-folder-open' : 'fa-folder'}`;
        openAll.disabled = pending || groupRows.length === 0;
    }

    async function saveGroups(url, data, update) {
        if (pending) return;
        if (isViewAs) {
            // Inspect collapsed groups locally; never persist another user's state.
            update({collapsed: data.collapsed,
                groups: groups().map(row => ({id: row.dataset.activityId, collapsed: data.collapsed}))});
            render();
            return;
        }
        pending = true;
        render();
        try {
            const response = await post(url, data);
            update(response);
        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            pending = false;
            render();
        }
    }

    eye.addEventListener('click', () => {
        hideCompleted = !hideCompleted;
        render();
    });
    openAll.addEventListener('click', () => {
        const collapsed = !groups().some(row => row.dataset.groupCollapsed === 'true');
        saveGroups(table.dataset.openAllUrl, { collapsed }, response => {
            const states = new Map(response.groups.map(group => [String(group.id), group.collapsed]));
            for (const row of groups()) {
                if (states.has(row.dataset.activityId)) row.dataset.groupCollapsed = String(states.get(row.dataset.activityId));
            }
        });
    });
    table.addEventListener('click', event => {
        const header = event.target.closest('td.header');
        const row = header?.closest('tr');
        if (table.dataset.manualGroups !== 'true' || event.defaultPrevented || pending || row?.dataset.isGroup !== 'true') return;
        const collapsed = row.dataset.groupCollapsed !== 'true';
        saveGroups(table.dataset.openGroupUrl, { openedGroup: row.dataset.activityId, collapsed }, response => {
            row.dataset.groupCollapsed = String(response.collapsed);
        });
    });
    window.addEventListener('habitus:activity-marked', event => {
        if (event.detail.error) showToast(event.detail.error, 'error');
        if (event.detail.day !== Number(table.dataset.currentDay) || !rows().includes(event.detail.row)) return;
        event.detail.row.dataset.completed = String(event.detail.completed);
        render(event.detail.completed && !event.detail.error ? event.detail.row : null);
    });
    window.addEventListener('habitus:rows-changed', render);
    render();
    return { refresh: render };
}
