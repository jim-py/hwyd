async function loadDriver() {
    if (window.driver) return;

    await import("/static/js/driver.js.iife.js");
}

async function loadGuide(slug) {
    return import(`/static/js/onboarding/guides/${slug}.js`);
}

async function startOnboarding() {
    const guides = window.PENDING_GUIDES || [];

    if (!guides.length) return;

    await loadDriver();

    for (const slug of guides) {
        const module = await loadGuide(slug);
        await module.start();
    }
}

document.addEventListener("DOMContentLoaded", startOnboarding);