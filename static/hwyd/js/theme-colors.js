const colorVariables = {
    backgroundColor: '--habitus-background', tableHeadColor: '--habitus-head',
    tableHeadColorWeekend: '--habitus-weekend', tableHeadTextColor: '--habitus-head-text',
    rowColumnLight: '--habitus-row-light'
};

export function applyThemeColors(colors, {updateInputs = true} = {}) {
    if (!colors) return;
    for (const [field, variable] of Object.entries(colorVariables)) {
        const value = colors[field];
        if (!/^#[\da-f]{6}$/i.test(value || '')) continue;
        document.documentElement.style.setProperty(variable, value);
        const input = document.querySelector(`#formColorSettings input[name="${field}"]`);
        if (updateInputs && input && input.value !== value) input.value = value;
    }
}

// The existing manual preview and scheduled changes share the same CSS rules.
const colorForm = document.getElementById('formColorSettings');
colorForm?.addEventListener('input', event => {
    if (event.target.name in colorVariables) {
        // Writing back to a native color picker during input can reset its selection.
        applyThemeColors({[event.target.name]: event.target.value}, {updateInputs: false});
    }
});
