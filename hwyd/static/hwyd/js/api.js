import { getCSRFToken } from "../../site/js/csrf.js";

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
