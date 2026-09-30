import { getCSRFToken } from "../../site/js/csrf.js";

export async function markViewed(slug) {
    await fetch(`/home/guides/${slug}/viewed/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": getCSRFToken(),
            "Content-Type": "application/json"
        }
    });
}