let csrfTokenCache = null;

export function getCSRFToken() {
    if (csrfTokenCache) return csrfTokenCache;

    const cookies = document.cookie.split(";");

    for (let cookie of cookies) {
        cookie = cookie.trim();

        if (cookie.startsWith("csrftoken=")) {
            csrfTokenCache =
                decodeURIComponent(cookie.substring(10));
        }
    }

    return csrfTokenCache || "";
}