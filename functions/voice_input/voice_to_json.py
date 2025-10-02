import os
import g4f
import json
import tempfile
from pathlib import Path
import speech_recognition as sr

BASE_DIR = Path(__file__).resolve().parent.parent
HOSTING = str(BASE_DIR).find('jim') == -1
DIRECTION = '/home/a0853298/tmp/' if HOSTING else 'C:/Users/jim/Documents/HWYD_BUDGET/myproject/test'


def recognize_phrase(phrase_wav_path: str) -> str:
    """
    Распознавание голоса в wav с помощью Google
    """

    recognizer = sr.Recognizer()
    with sr.AudioFile(phrase_wav_path) as source:
        audio_data = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio_data, language="ru-RU")
        except sr.UnknownValueError:
            text = 'exception'
        except sr.RequestError:
            text = 'exception'

    return text


def chat_gpt(text):
    """
    Запрос в Chat GPT для получение JSON из текста
    """

    response = g4f.ChatCompletion.create(
        model=g4f.models.gpt_35_turbo_0613,
        messages=[{"role": "user", "content": text + ". Выбери из этого текста сумма и категория и помести это в "
                                                     "JSON. Сумма должна быть цифрой, а категория строкой. Категория "
                                                     "должна быть похожа, как в списке Интернет-покупки, Еда, Вода"}]
    )

    response = response.lower() + '   '
    start_index = response.find('{')
    end_index = response.rfind('}') + 1
    json_data = response[start_index:end_index]

    result = json.loads(json_data)

    amount = [value for key, value in result.items() if 'сум' in key.lower()]
    category = [value for key, value in result.items() if 'катег' in key.lower()]
    return amount[0], category[0]


def wav_to_json(file):
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False, dir=DIRECTION) as temp_file:

        for chunk in file.chunks():
            temp_file.write(chunk)

        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.seek(0)

        res = recognize_phrase(temp_file.name)

    temp_file.close()
    os.remove(temp_file.name)

    if res == 'exception':
        return res

    return chat_gpt(res)
