document.addEventListener("DOMContentLoaded", () => {
    let timer = 0;
    let interval;
    let score = 0;
    let running = false;
    let maxProblems = Number(document.getElementById('maxProblems').value);
    let countdownValue = Number(document.getElementById('countdownValue').value);

    const $timer = document.getElementById('timer');
    const $score = document.getElementById('scoreCounter');
    const $problem = document.querySelector('.math-training__problem');
    const $answer = document.getElementById('answer');
    const $startButton = document.getElementById('startButton');
    const $maxProblems = document.getElementById('maxProblems');
    const $countdownValue = document.getElementById('countdownValue');
    const $countdown = document.getElementById('countdown');

    function startTimer() {
        interval = setInterval(function () {
            timer += 10;
            $timer.innerText = (timer / 1000).toFixed(2);
        }, 10);
    }

    function generateMathProblem() {
        let num1 = 0, num2 = 0;
        while (true) {
            num1 = Math.floor(Math.random() * 10);
            num2 = Math.floor(Math.random() * 10);
            if (num1 >= num2 && num2 !== 0) break;
        }
        const operations = ['+', '-', '*', '/'];
        const operation = operations[Math.floor(Math.random() * operations.length)];
        let problemText, answer;
        switch (operation) {
            case '+': problemText = `${num1} + ${num2}`; answer = num1 + num2; break;
            case '-': problemText = `${num1} - ${num2}`; answer = num1 - num2; break;
            case '*': problemText = `${num1} * ${num2}`; answer = num1 * num2; break;
            case '/':
                const tempAnswer = Math.floor(Math.random() * 10);
                let adjustedNum1 = tempAnswer * num2;
                problemText = `${adjustedNum1} / ${num2}`;
                answer = adjustedNum1 / num2;
                break;
        }
        $problem.innerText = problemText;
        return answer;
    }

    function startCountdown() {
        $startButton.style.display = 'none';
        $maxProblems.style.display = 'none';
        $countdownValue.style.display = 'none';
        document.querySelector('label[for="maxProblems"]').style.display = 'none';
        document.querySelector('label[for="countdownValue"]').style.display = 'none';
        $countdown.innerText = countdownValue;

        let countdown = setInterval(() => {
            countdownValue--;
            $countdown.innerText = countdownValue;
            if (countdownValue <= 0) {
                clearInterval(countdown);
                $countdown.style.display = 'none';
                $problem.style.display = 'block';
                $answer.style.display = 'block';
                $timer.style.display = 'block';
                $score.style.display = 'block';
                $answer.disabled = false;
                $answer.focus();
                answer = generateMathProblem();
                startTimer();
                running = true;
            }
        }, 1000);
    }

    $startButton.addEventListener('click', () => { if (!running) startCountdown(); });
    $maxProblems.addEventListener('input', (e) => maxProblems = e.target.value);
    $countdownValue.addEventListener('input', (e) => countdownValue = e.target.value);

    window.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !running) $startButton.click();
    });

    $answer.addEventListener('input', (e) => {
        if (Number(e.target.value) === answer) {
            e.target.value = '';
            score++;
            $score.innerText = `Решено: ${score}`;
            if (score < maxProblems) {
                answer = generateMathProblem();
            } else {
                $problem.innerText = 'Тренажёр завершен!';
                clearInterval(interval);
                $answer.disabled = true;
                running = false;
                sendToServer();
            }
        }
    });

    function sendToServer() {
        $.ajax({
            url: "{% url 'mathtraining' %}",
            type: "post",
            data: {
                'csrfmiddlewaretoken': '{{ csrf_token }}',
                'time': timer,
                'examples_solved': score
            }
        });
    }
});
