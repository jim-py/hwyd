const initialized = new WeakSet();

export function enableDialogDrag(dialog) {
    if (!dialog || initialized.has(dialog)) return;
    const header = dialog.querySelector('.modal__header');
    if (!header) return;
    initialized.add(dialog);
    const desktopOnly = dialog.hasAttribute('data-desktop-drag');
    const mobileInput = window.matchMedia('(max-width: 767px), (pointer: coarse)');
    const canDrag = () => !desktopOnly || (dialog.dataset.mobile !== 'true' && !mobileInput.matches);
    let gesture = null;
    let moved = false;

    function place(left, top) {
        const rect = dialog.getBoundingClientRect();
        const maxLeft = Math.max(16, document.documentElement.clientWidth - rect.width - 16);
        const maxTop = Math.max(16, window.innerHeight - rect.height - 16);
        dialog.style.inset = 'auto';
        dialog.style.margin = '0';
        dialog.style.left = `${Math.min(maxLeft, Math.max(16, left))}px`;
        dialog.style.top = `${Math.min(maxTop, Math.max(16, top))}px`;
        moved = true;
    }

    function stopDrag() {
        if (!gesture) return;
        const pointerId = gesture.pointerId;
        gesture = null;
        if (header.hasPointerCapture(pointerId)) header.releasePointerCapture(pointerId);
    }

    header.addEventListener('pointerdown', event => {
        if (!canDrag() || (desktopOnly && event.pointerType !== 'mouse')) return;
        if (!dialog.open || gesture || event.button !== 0 || !event.isPrimary) return;
        if (event.target.closest('button, a, input, select, textarea')) return;
        event.preventDefault();
        const rect = dialog.getBoundingClientRect();
        gesture = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, left: rect.left, top: rect.top };
        header.setPointerCapture(event.pointerId);
    });
    header.addEventListener('pointermove', event => {
        if (gesture?.pointerId !== event.pointerId) return;
        place(gesture.left + event.clientX - gesture.x, gesture.top + event.clientY - gesture.y);
    });
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
        header.addEventListener(type, event => {
            if (gesture?.pointerId === event.pointerId) stopDrag();
        });
    }
    function resetPosition() {
        moved = false;
        for (const property of ['inset', 'margin', 'left', 'top']) dialog.style.removeProperty(property);
    }
    function updatePlacement() {
        stopDrag();
        if (!canDrag()) {
            if (moved) resetPosition();
            return;
        }
        if (!dialog.open || !moved) return;
        const rect = dialog.getBoundingClientRect();
        place(rect.left, rect.top);
    }
    window.addEventListener('resize', updatePlacement);
    if (desktopOnly) mobileInput.addEventListener('change', updatePlacement);
    dialog.addEventListener('close', () => {
        stopDrag();
        resetPosition();
    });
}
