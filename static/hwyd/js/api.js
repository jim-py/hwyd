import { getCSRFToken } from "../../site/js/csrf.js";

export async function requestJSON(url, {method = 'POST', data = {}, json = false} = {}) {
    const headers = {'Accept': 'application/json'};
    if (method !== 'GET') headers['X-CSRFToken'] = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || getCSRFToken();
    if (json) headers['Content-Type'] = 'application/json';
    const body = method === 'GET' ? undefined : json ? JSON.stringify(data) : data instanceof FormData ? data : new URLSearchParams(data);
    let response;
    try {
        response = await fetch(url, {method, credentials: 'same-origin', cache: 'no-store', headers, body});
    } catch {
        throw new Error('Не удалось связаться с сервером. Попробуйте ещё раз.');
    }
    let result = null;
    if (response.headers.get('Content-Type')?.includes('application/json')) result = await response.json();
    if (!response.ok || response.redirected) {
        throw new Error(result?.error || 'Не удалось выполнить запрос. Попробуйте ещё раз.');
    }
    return result;
}

export function post(url, data) {
    return requestJSON(url, {data});
}

export async function markViewed(slug) {
    const response = await fetch(`/home/guides/${slug}/viewed/`, {
        method: "POST",
        keepalive: true,
        headers: {
            "X-CSRFToken": getCSRFToken(),
            "Content-Type": "application/json"
        }
    });
    if (!response.ok) throw new Error(`Guide progress: HTTP ${response.status}`);
}
