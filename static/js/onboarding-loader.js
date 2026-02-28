import { loadDriver } from "./driver-loader.js";

async function loadGuide(slug) {
    return import(`./guides/${slug}.js`);
}

async function startOnboarding() {
    const guides = window.PENDING_GUIDES || [];

    if (!guides.length) return;

    // грузим driver.js только если нужен
    await loadDriver();

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