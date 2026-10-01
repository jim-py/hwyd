export function enableDialogDrag(dialog) {
    const header = dialog.querySelector('.modal__header');
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
    window.addEventListener('resize', () => {
        stopDrag();
        if (!dialog.open || !moved) return;
        const rect = dialog.getBoundingClientRect();
        place(rect.left, rect.top);
    });
    dialog.addEventListener('close', () => {
        stopDrag();
        moved = false;
        for (const property of ['inset', 'margin', 'left', 'top']) dialog.style.removeProperty(property);
    });
}
