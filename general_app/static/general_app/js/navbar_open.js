document.addEventListener("DOMContentLoaded", function () {
    const navbarToggle = document.querySelector('.navbar-toggle');
    navbarToggle.addEventListener('click', function () {
        const navbarCollapse = document.querySelector('.navbar-collapse');
        if (navbarCollapse.classList.contains('open')) {
            navbarCollapse.classList.remove('open');
        } else {
            navbarCollapse.classList.add('open');
        }
    });
});
