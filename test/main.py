import g4f
import json

response = g4f.ChatCompletion.create(
    model=g4f.models.gpt_35_turbo_0613,
    messages=[{"role": "user", "content": "я потратил десять тысяч пятьсот рублей на интернет покупки . Выбери из "
                                          "этого текста сумма и категория и помести это в JSON. Сумма должна быть "
                                          "цифрой, а категория строкой. Категория должна быть похожа, как в списке "
                                          "Интернет-покупки, Еда, Вода"}]
)

print(response)

response = response.lower() + '   '
start_index = response.find('{')
end_index = response.rfind('}') + 1
json_data = response[start_index:end_index]

result = json.loads(json_data)

amount = [value for key, value in result.items() if 'сум' in key.lower()]
category = [value for key, value in result.items() if 'катег' in key.lower()]

print(amount, category)
