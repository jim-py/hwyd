// Cell comments and habit descriptions share the data-title / ::before bubble.
// Put the habit bubble outside the scaled mobile table to avoid clipping it.
const bubble = document.createElement('div');
bubble.id = 'habitDescriptionTooltip';
bubble.className = 'habit-description-tooltip';
bubble.hidden = true;
bubble.setAttribute('role', 'tooltip');
bubble.tabIndex = -1;
document.body.append(bubble);
let activeName = null;

const hide = () => {
    bubble.hidden = true;
    bubble.removeAttribute('data-title');
    bubble.removeAttribute('aria-label');
    activeName = null;
};

const show = name => {
    activeName = name;
    const rect = name.getBoundingClientRect();
    if (rect.bottom <= 0 || rect.top >= window.innerHeight || rect.right <= 0 || rect.left >= window.innerWidth) {
        hide();
        return;
    }
    const width = Math.min(360, window.innerWidth - 32);
    const beside = window.innerWidth - rect.right - 24 >= width;
    const below = window.innerHeight - (beside ? rect.top : rect.bottom) - 16;
    const height = Math.min(300, below >= 144 ? below : Math.max(80, rect.top - 24));
    const top = below >= 144 ? (beside ? rect.top : rect.bottom) : Math.max(16, rect.top - height);
    const left = beside ? rect.right : Math.max(16, Math.min(rect.left, window.innerWidth - width - 16));
    bubble.style.setProperty('--description-tooltip-left', `${left}px`);
    bubble.style.setProperty('--description-tooltip-top', `${top}px`);
    bubble.style.setProperty('--description-tooltip-height', `${height}px`);
    bubble.dataset.title = name.dataset.title;
    bubble.setAttribute('aria-label', name.dataset.title);
    bubble.hidden = false;
};

for (const name of document.querySelectorAll('.paragraph.hasDescription')) {
    name.setAttribute('aria-describedby', bubble.id);
    name.addEventListener('pointerenter', () => show(name));
    name.addEventListener('focus', () => {
        if (name.matches(':focus-visible')) show(name);
    });
    name.addEventListener('pointerleave', event => {
        if (activeName === name && !bubble.contains(event.relatedTarget) && !name.matches(':focus-visible')) hide();
    });
    name.addEventListener('blur', event => {
        if (activeName === name && !bubble.contains(event.relatedTarget) && !bubble.matches(':hover')) hide();
    });
    name.addEventListener('keydown', event => {
        if (event.key === 'Escape') hide();
    });
}
bubble.addEventListener('pointerleave', event => {
    if (activeName && !activeName.contains(event.relatedTarget) && !activeName.matches(':focus-visible')) hide();
});
// Dialogs must never be covered by a previously focused habit's bubble.
document.addEventListener('contextmenu', hide);
window.addEventListener('resize', () => {
    if (activeName) show(activeName);
});
document.addEventListener('scroll', event => {
    if (activeName && !bubble.contains(event.target)) show(activeName);
}, true);

for (const field of document.querySelectorAll('textarea[name="description"]')) {
    const validate = () => field.setCustomValidity(
        [...field.value].length > 3000 ? 'Описание должно содержать не больше 3000 символов.' : ''
    );
    field.addEventListener('input', validate);
    field.form.addEventListener('submit', validate);
}
