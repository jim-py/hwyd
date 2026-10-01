const dialog = document.getElementById('topModal');
const status = document.getElementById('topStatus');
const list = document.getElementById('topLeaders');
const current = document.getElementById('topCurrent');
let generation = 0;

export async function loadTop() {
    const request = ++generation;
    status.hidden = false;
    status.textContent = 'Загрузка…';
    list.replaceChildren();
    current.hidden = true;
    try {
        const response = await fetch(dialog.dataset.topUrl, { credentials: 'same-origin', cache: 'no-store' });
        if (!response.ok || response.redirected) throw new Error();
        const data = await response.json();
        if (request !== generation) return;
        for (const leader of data.leaders) {
            const row = document.createElement('li');
            row.className = leader.is_own ? 'streak-top__row streak-top__row--own' : 'streak-top__row';
            const rank = document.createElement('span');
            rank.className = 'streak-top__rank';
            rank.textContent = leader.rank;
            const name = document.createElement('span');
            name.className = 'streak-top__name';
            name.textContent = leader.name;
            const streak = document.createElement('span');
            streak.className = 'streak-top__value';
            const icon = document.createElement('i');
            icon.className = 'fa-solid fa-fire';
            icon.setAttribute('aria-hidden', 'true');
            streak.append(icon, ` ${leader.streak}`);
            streak.setAttribute('aria-label', `Стрик: ${leader.streak} дней подряд`);
            row.append(rank, name, streak);
            list.append(row);
        }
        status.hidden = data.leaders.length > 0;
        status.textContent = 'Рейтинг появится после первых посещений.';
        const rank = data.current.rank;
        current.textContent = rank ? `Ваше место: ${rank} · Стрик: ${data.current.streak} дней подряд` : 'У вас пока нет стрика. Заходите каждый день, чтобы попасть в Top.';
        current.hidden = false;
        document.getElementById('topRank').textContent = rank ? `#${rank}` : '—';
        document.getElementById('topStreak').setAttribute('aria-label', `Top: место ${rank || '—'}`);
    } catch {
        if (request !== generation) return;
        status.textContent = 'Не удалось загрузить Top. Закройте окно и попробуйте ещё раз.';
    }
}
