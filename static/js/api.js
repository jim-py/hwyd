import { getCSRFToken } from "./csrf.js";

export async function markViewed(slug) {
    await fetch(`/home/guides/${slug}/viewed/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": getCSRFToken(),
            "Content-Type": "application/json"
        }
    });
}