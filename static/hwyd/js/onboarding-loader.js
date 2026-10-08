import { loadDriver } from "./driver-loader.js";
import { showToast } from './toast.js';

async function loadGuide(slug) {
    if (slug === 'main_toolbar') return import('./guides/main_toolbar.js?v=20261008-admin');
    throw new Error('Неизвестный гайд');
}

async function startOnboarding() {
    const guides = window.PENDING_GUIDES || [];

    if (!guides.length) return;

    // грузим driver.js только если нужен
    try {
        await loadDriver();
    } catch (error) {
        console.error('Guide load error:', error);
        showToast('Не удалось открыть обучение. Попробуйте ещё раз.', 'error');
        return;
    }

    for (const slug of guides) {
        try {
            const module = await loadGuide(slug);

            if (module.start) {
                await module.start();
            }
        } catch (e) {
            console.error("Guide load error:", slug, e);
        }
    }
}

document.addEventListener("DOMContentLoaded", startOnboarding);

document.getElementById('restartGuide')?.addEventListener('click', async () => {
    document.getElementById('some-modal-id').close();
    try {
        await loadDriver();
        await (await loadGuide('main_toolbar')).start();
    } catch (error) {
        console.error('Guide load error:', error);
        showToast('Не удалось открыть обучение. Попробуйте ещё раз.', 'error');
    }
});
