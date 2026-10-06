// Reuse the data-title / ::before comment bubble outside the scaled table.
const tooltip = document.createElement('div');
tooltip.className = 'cell-comment-tooltip';
tooltip.hidden = true;
tooltip.tabIndex = -1;
tooltip.setAttribute('role', 'tooltip');
document.body.append(tooltip);
document.body.classList.add('cell-comments-enhanced');
let activeCell = null;

const hide = () => {
    tooltip.hidden = true;
    tooltip.removeAttribute('data-title');
    tooltip.removeAttribute('aria-label');
    activeCell = null;
};

const show = cell => {
    const rect = cell.getBoundingClientRect();
    if (!cell.dataset.title || rect.bottom <= 0 || rect.top >= window.innerHeight || rect.right <= 0 || rect.left >= window.innerWidth) {
        hide();
        return;
    }
    const changed = activeCell !== cell || tooltip.dataset.title !== cell.dataset.title;
    activeCell = cell;
    tooltip.dataset.title = cell.dataset.title;
    tooltip.setAttribute('aria-label', cell.dataset.title);
    tooltip.hidden = false;
    if (changed) tooltip.scrollTop = 0;
    const { width, height } = tooltip.getBoundingClientRect();
    let left = rect.right;
    let top = rect.top;
    if (left + width > window.innerWidth - 16) left = rect.left - width;
    if (left < 16) {
        left = Math.max(16, Math.min(rect.left, window.innerWidth - width - 16));
        top = rect.bottom + height <= window.innerHeight - 16 ? rect.bottom : rect.top - height;
    }
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${Math.max(16, Math.min(top, window.innerHeight - height - 16))}px`;
};

for (const cell of document.querySelectorAll('.divClick.hasText')) {
    cell.addEventListener('pointerenter', () => show(cell));
    cell.addEventListener('pointerleave', event => {
        if (activeCell === cell && !tooltip.contains(event.relatedTarget)) hide();
    });
}
tooltip.addEventListener('pointerleave', event => {
    if (activeCell && !activeCell.contains(event.relatedTarget)) hide();
});
tooltip.addEventListener('keydown', event => {
    if (event.key === 'Escape') hide();
});
document.addEventListener('contextmenu', hide);
document.addEventListener('pointerdown', event => {
    if (activeCell && !activeCell.contains(event.target) && !tooltip.contains(event.target)) hide();
});
window.addEventListener('resize', () => {
    if (activeCell) show(activeCell);
});
document.addEventListener('scroll', event => {
    if (activeCell && !tooltip.contains(event.target)) show(activeCell);
}, true);
