import { controls, buildGuideSteps } from '../../hwyd/js/guides/main_toolbar_content.js?v=20261008-admin';
import { loadDriver } from '../../hwyd/js/driver-loader.js';
const container = document.getElementById('pv-guide-controls');
const steps = buildGuideSteps();
for (const [selector, title] of controls) {
    const button = document.createElement('button'); button.type = 'button'; button.id = selector.slice(1); button.textContent = title;
    container.append(button);
}
for (const step of steps) {
    const item = document.createElement('li'); const title = document.createElement('strong'); title.textContent = step.popover.title;
    const text = document.createElement('p'); text.textContent = step.popover.description; item.append(title,text); document.getElementById('pv-guide-steps').append(item);
}
document.getElementById('pv-start-guide').addEventListener('click', async () => {
    const status = document.getElementById('pv-guide-status');
    try {
        await loadDriver();
        window.driver.js.driver({steps, showProgress:true, progressText:'{{current}} из {{total}}',
            nextBtnText:'Далее', prevBtnText:'Назад', doneBtnText:'Готово',
            disableActiveInteraction:true, overlayClickBehavior:()=>{}, popoverClass:'onboarding-popover',
            overlayOpacity:.65, stagePadding:6, stageRadius:10, popoverOffset:12,
            animate:!matchMedia('(prefers-reduced-motion: reduce)').matches}).drive();
        status.textContent = '';
    } catch { status.textContent = 'Не удалось загрузить предпросмотр гайда. Попробуйте ещё раз.'; }
});
