// Identity comes from server-validated page context, never from an arbitrary query.
export const isViewAs = Boolean(document.body.dataset.viewAs);

export function viewAsURL(value) {
    if (!isViewAs) return value;
    const url = new URL(value, location.href);
    url.searchParams.set('view_as', document.body.dataset.viewAs);
    return url.href;
}
