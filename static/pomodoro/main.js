let timer;
let minutes = 25;
let seconds = 0;
let isRunning = false;

document.addEventListener('DOMContentLoaded', (event) => {
    const inputs = document.querySelectorAll('#minutesInput, #secondsInput');
    inputs.forEach(input => input.addEventListener('input', validateInput));
});

function validateInput(event) {
    let value = event.target.value;
    let id = event.target.id;

    value = value.replace(/[^0-9]/g, '');
    if (value === '') {
        value = id === 'minutesInput' ? 1 : 0;
    }
    value = parseInt(value, 10);
    if (id === 'minutesInput' && (value < 1 || value > 60)) {
        value = Math.max(1, Math.min(60, value));
    }
    if (id === 'secondsInput' && (value < 0 || value > 59)) {
        value = Math.max(0, Math.min(59, value));
    }
    event.target.value = value;
}

function startTimer() {
    if (!isRunning) {
        isRunning = true;
        document.getElementById('start-btn').disabled = true;
        document.getElementById('reset-btn').disabled = false;
        timer = setInterval(countdown, 1000);
    }
}

function resetTimer() {
    clearInterval(timer);
    isRunning = false;
    minutes = parseInt(document.getElementById('minutesInput').value);
    seconds = parseInt(document.getElementById('secondsInput').value);
    document.getElementById('timer').innerText =
        `${minutes < 10 ? '0' : ''}${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
    document.getElementById('start-btn').disabled = false;
    document.getElementById('reset-btn').disabled = true;
}

function countdown() {
    if (seconds === 0) {
        if (minutes !== 0) {
            minutes--;
            seconds = 59;
        }
    } else {
        seconds--;
    }

    document.getElementById('timer').innerText =
        `${minutes < 10 ? '0' : ''}${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;

    if (seconds === 0) {
        if (minutes === 0) {
            clearInterval(timer);
            isRunning = false;
            document.getElementById('start-btn').disabled = false;
            playAlarm(5000);
        }
    }
}

function playAlarm(duration) {
    const alarmSound = document.getElementById('alarmSound');
    alarmSound.currentTime = 0;
    alarmSound.play();

    setTimeout(() => {
        alarmSound.pause();
        alert("Время вышло, пора отдыхать!");
    }, duration);
}

function openSettings() {
    document.getElementById('settingsModal').style.display = "block";
}

function closeSettings() {
    document.getElementById('settingsModal').style.display = "none";
}

function applySettings() {
    minutes = parseInt(document.getElementById('minutesInput').value);
    seconds = parseInt(document.getElementById('secondsInput').value);
    document.getElementById('timer').innerText =
        `${minutes < 10 ? '0' : ''}${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
    closeSettings();
}
