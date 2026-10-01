// Window behavior is independent of message rendering, polling and API requests.
export function createChatWindow(dialog, opener) {
    const narrow = window.matchMedia('(max-width: 1023px)');
    const margin = 8;
    const minimum = { width: 320, height: 320 };
    const interactive = 'button, a, input, textarea, select, label, [role="button"], [contenteditable]';
    let bounds = null;
    let gesture = null;
    let frame = null;

    const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
    const viewport = () => ({ width: document.documentElement.clientWidth, height: window.innerHeight });

    function constrain(rect) {
        const size = viewport();
        const width = clamp(rect.width, Math.min(minimum.width, size.width - margin * 2), size.width - margin * 2);
        const height = clamp(rect.height, Math.min(minimum.height, size.height - margin * 2), size.height - margin * 2);
        return {
            left: clamp(rect.left, margin, size.width - width - margin),
            top: clamp(rect.top, margin, size.height - height - margin),
            width, height
        };
    }

    function place(rect) {
        bounds = constrain(rect);
        for (const key of ['left', 'top', 'width', 'height']) dialog.style[key] = `${bounds[key]}px`;
    }

    function desktopBounds() {
        const size = viewport();
        return bounds || { left: (size.width - 420) / 2, top: (size.height - 600) / 2, width: 420, height: 600 };
    }

    function stopGesture() {
        if (!gesture) return;
        const { pointerId } = gesture;
        gesture = null;
        dialog.classList.remove('chat-window--dragging', 'chat-window--adjusting');
        if (dialog.hasPointerCapture(pointerId)) dialog.releasePointerCapture(pointerId);
    }

    function applyMode() {
        document.body.classList.toggle('chat-fullscreen-open', dialog.open && narrow.matches);
        dialog.setAttribute('aria-modal', String(narrow.matches));
        if (narrow.matches) {
            for (const key of ['left', 'top', 'width', 'height']) dialog.style.removeProperty(key);
        } else {
            place(desktopBounds());
        }
    }

    function onViewportChange() {
        stopGesture();
        const open = dialog.open;
        const wasModal = dialog.matches(':modal');
        const focus = dialog.contains(document.activeElement) ? document.activeElement : null;
        if (open && wasModal !== narrow.matches) {
            // Native dialog cannot switch modal state while open. Ignore the
            // queued close event after this immediate reopen (see close handler).
            dialog.close();
            applyMode();
            if (narrow.matches) dialog.showModal();
            else dialog.show();
            focus?.focus({ preventScroll: true });
        }
        applyMode();
    }

    function onResize() {
        if (frame !== null) return;
        frame = requestAnimationFrame(() => {
            frame = null;
            onViewportChange();
        });
    }

    dialog.addEventListener('pointerdown', event => {
        if (!dialog.open || narrow.matches || event.button !== 0 || !event.isPrimary || gesture) return;
        const handle = event.target.closest('[data-chat-resize]');
        const header = event.target.closest('.modal__header');
        if (!handle && (!header || event.target.closest(interactive))) return;
        event.preventDefault();
        const rect = dialog.getBoundingClientRect();
        gesture = {
            pointerId: event.pointerId, edge: handle?.dataset.chatResize || '',
            x: event.clientX, y: event.clientY,
            rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height }
        };
        dialog.setPointerCapture(event.pointerId);
        dialog.classList.add('chat-window--adjusting');
        if (!handle) dialog.classList.add('chat-window--dragging');
    });

    dialog.addEventListener('pointermove', event => {
        if (!gesture || gesture.pointerId !== event.pointerId) return;
        const { edge, rect } = gesture;
        const dx = event.clientX - gesture.x;
        const dy = event.clientY - gesture.y;
        if (!edge) {
            place({ ...rect, left: rect.left + dx, top: rect.top + dy });
            return;
        }
        const size = viewport();
        let left = rect.left, top = rect.top;
        let right = left + rect.width, bottom = top + rect.height;
        const minWidth = Math.min(minimum.width, size.width - margin * 2);
        const minHeight = Math.min(minimum.height, size.height - margin * 2);
        if (edge.includes('w')) left = clamp(rect.left + dx, margin, right - minWidth);
        if (edge.includes('e')) right = clamp(right + dx, left + minWidth, size.width - margin);
        if (edge.includes('n')) top = clamp(rect.top + dy, margin, bottom - minHeight);
        if (edge.includes('s')) bottom = clamp(bottom + dy, top + minHeight, size.height - margin);
        place({ left, top, width: right - left, height: bottom - top });
    });

    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
        dialog.addEventListener(type, event => {
            if (gesture?.pointerId === event.pointerId) stopGesture();
        });
    }
    dialog.addEventListener('keydown', event => {
        // Native modal Escape remains unchanged. Non-modal Escape belongs only
        // to the focused chat, so other page controls and dialogs keep their keys.
        if (event.key === 'Escape' && !narrow.matches && !event.defaultPrevented) {
            event.preventDefault();
            event.stopPropagation();
            dialog.close();
        }
    });
    dialog.addEventListener('close', () => {
        if (dialog.open) return;
        stopGesture();
        if (frame !== null) cancelAnimationFrame(frame);
        frame = null;
        window.removeEventListener('resize', onResize);
        document.body.classList.remove('chat-fullscreen-open');
        if (dialog.contains(document.activeElement)) opener.focus({ preventScroll: true });
    });

    return {
        open() {
            if (dialog.open) return;
            applyMode();
            if (narrow.matches) dialog.showModal();
            else dialog.show();
            applyMode();
            window.addEventListener('resize', onResize);
        }
    };
}
