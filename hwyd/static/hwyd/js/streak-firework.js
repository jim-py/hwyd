const button = document.getElementById('loginStreak');

if (button) {
    let clicks = 0;
    let running = false;

    function burst() {
        if (typeof button.animate !== 'function') return;
        running = true;
        const animations = [];
        let overlay;
        let cleaned = false;

        function cleanup() {
            if (cleaned) return;
            cleaned = true;
            animations.forEach(animation => animation.cancel());
            if (overlay) overlay.remove();
            document.removeEventListener('visibilitychange', onVisibilityChange);
            window.removeEventListener('pagehide', cleanup);
            running = false;
        }

        function onVisibilityChange() {
            if (document.hidden) cleanup();
        }

        try {
            if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
                const background = getComputedStyle(button).backgroundColor;
                animations.push(button.animate([
                    { backgroundColor: background },
                    { backgroundColor: '#fde68a' },
                    { backgroundColor: background }
                ], { duration: 180 }));
            } else {
                const rect = button.getBoundingClientRect();
                overlay = document.createElement('div');
                overlay.className = 'streak-firework';
                overlay.setAttribute('aria-hidden', 'true');
                overlay.style.cssText = 'position:fixed;width:0;height:0;pointer-events:none;z-index:2000;';
                overlay.style.left = `${rect.left + rect.width / 2}px`;
                overlay.style.top = `${rect.top + rect.height / 2}px`;
                document.body.append(overlay);

                const colors = ['#22c55e', '#fbbf24', '#fb923c', '#f87171', '#a7f3d0'];
                for (let i = 0; i < 24; i++) {
                    const angle = Math.PI + Math.PI * (i + 0.5) / 24;
                    const speed = 45 + Math.random() * 45;
                    const x = Math.cos(angle) * speed;
                    const y = Math.sin(angle) * speed;
                    const particle = document.createElement('span');
                    particle.style.cssText = 'position:absolute;width:4px;height:4px;border-radius:50%;pointer-events:none;';
                    particle.style.backgroundColor = colors[i % colors.length];
                    overlay.append(particle);
                    animations.push(particle.animate([
                        { transform: 'translate(-2px, -2px) scale(1)', opacity: 1 },
                        { transform: `translate(${x * 0.55}px, ${y * 0.55 + 18}px) scale(1)`, opacity: 0.9, offset: 0.55 },
                        { transform: `translate(${x}px, ${y + 60}px) scale(0)`, opacity: 0 }
                    ], { duration: 760, delay: Math.random() * 60, easing: 'linear' }));
                }
            }
            document.addEventListener('visibilitychange', onVisibilityChange);
            window.addEventListener('pagehide', cleanup);
            Promise.all(animations.map(animation => animation.finished.catch(() => {})))
                .finally(cleanup);
        } catch (failure) {
            cleanup();
        }
    }

    // Bubble phase respects the existing onboarding toolbar capture lock.
    document.addEventListener('click', event => {
        if (!button.contains(event.target)) {
            clicks = 0;
            return;
        }
        if (running) return;
        clicks += 1;
        if (clicks === 10) {
            clicks = 0;
            burst();
        }
    });
}
