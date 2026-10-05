const roleLabels = {owner: 'Владелец', admin: 'Admin'};

// Names remain text, including markup-like profile names.
export function renderUserName(element, name, role) {
    const nickname = document.createElement('span');
    nickname.className = 'user-name__nickname';
    nickname.textContent = name;
    element.replaceChildren(nickname);
    element.classList.remove('user-name--owner', 'user-name--admin');
    if (role !== 'owner' && role !== 'admin') return;
    element.classList.add(`user-name--${role}`);
    const label = document.createElement('span');
    label.className = 'user-name__role';
    label.textContent = ` (${roleLabels[role]})`;
    element.append(label);
}
