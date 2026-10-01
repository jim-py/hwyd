const toast = document.getElementById('habitusToast');
const text = toast.querySelector('.habitus-toast__text');
let timer;
let animation;

export function showToast(message, tone = 'success') {
    if (!message) return;
    clearTimeout(timer);
    animation?.cancel();
    text.textContent = message;
    toast.dataset.tone = tone === 'error' ? 'error' : 'success';
    toast.hidden = false;
    // A manual popover stays above native dialogs without taking focus.
    if (toast.showPopover && !toast.matches(':popover-open')) toast.showPopover();

    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        animation = toast.animate([
            { opacity: 0, transform: 'translateY(6px)', offset: 0 },
            { opacity: 1, transform: 'translateY(0)', offset: 0.06 },
            { opacity: 1, transform: 'translateY(0)', offset: 0.94 },
            { opacity: 0, transform: 'translateY(6px)', offset: 1 },
        ], { duration: 3000, easing: 'ease-out' });
    }

    timer = setTimeout(() => {
        if (toast.hidePopover && toast.matches(':popover-open')) toast.hidePopover();
        toast.hidden = true;
        text.textContent = '';
        animation?.cancel();
    }, 3000);
}
