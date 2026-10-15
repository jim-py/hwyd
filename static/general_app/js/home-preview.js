(() => {
    'use strict';
    const preview = document.querySelector('[data-habitus-preview]');
    if (!preview) return;
    const cells = [...preview.querySelectorAll('[data-preview-cell]')];
    const habits = [...preview.querySelectorAll('[data-preview-habit]')];
    const toggle = preview.querySelector('.public-preview-group-toggle');

    // Same five color stops and interpolation as the tracker's group percentages.
    function groupColor(percent) {
        const colors = [[224, 102, 102], [220, 146, 116], [249, 203, 156], [247, 244, 202], [187, 201, 173]];
        const index = Math.min(Math.floor(percent / 25), colors.length - 2);
        const fraction = (percent - index * 25) / 25;
        const rgb = colors[index].map((value, channel) => Math.round(value + (colors[index + 1][channel] - value) * fraction));
        return {background: `rgb(${rgb.join(', ')})`, color: (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) / 1000 > 128 ? '#333' : '#fff'};
    }

    function updateGroup(day) {
        const daily = cells.filter(cell => cell.dataset.previewCell === day);
        const percent = Math.round(daily.filter(cell => cell.getAttribute('aria-pressed') === 'true').length / daily.length * 100);
        const progress = preview.querySelector(`[data-preview-progress="${day}"]`);
        const bar = progress.querySelector('.progress-bar');
        progress.setAttribute('aria-valuenow', String(percent));
        progress.classList.toggle('off', percent === 0);
        progress.classList.toggle('full', percent > 0);
        bar.style.width = percent ? '100%' : '0%';
        bar.textContent = percent ? String(percent) : '';
        Object.assign(bar.style, groupColor(percent));
    }

    function playSound(done) {
        try {
            const sound = new Audio(done ? preview.dataset.soundOn : preview.dataset.soundOff);
            sound.volume = 0.5;
            sound.play()?.catch(() => {});
        } catch (_) {
            // Audio availability does not affect the local example.
        }
    }

    for (const cell of cells) {
        cell.disabled = false;
        cell.addEventListener('click', () => {
            const done = cell.getAttribute('aria-pressed') !== 'true';
            cell.setAttribute('aria-pressed', String(done));
            cell.classList.toggle('on', done);
            updateGroup(cell.dataset.previewCell);
            playSound(done);
        });
    }
    toggle.disabled = false;
    toggle.addEventListener('click', () => {
        const expanded = toggle.getAttribute('aria-expanded') !== 'true';
        toggle.setAttribute('aria-expanded', String(expanded));
        for (const habit of habits) habit.hidden = !expanded;
    });
    for (const progress of preview.querySelectorAll('[data-preview-progress]')) updateGroup(progress.dataset.previewProgress);
    document.querySelector('[data-preview-hint]').hidden = false;
})();
