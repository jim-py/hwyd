import re
import requests
import pandas as pd
from datetime import datetime

Chek = "t=20240216T1915&s=29900.00&fn=9961440300381637&i=68211&fp=2469164169&n=1"
Chek = input()
Token = "26817.m8ytY4omnqvUob2Sq"
Url = "https://proverkacheka.com/api/v1/check/get"
Data = {"token": Token, "qrraw": Chek}
r = requests.post(Url, data=Data)

pd.set_option('display.max_columns', None)
my_products=pd.DataFrame(r.json()['data']['json']['items'])
my_products['sum']=my_products['sum'] / 100
my_products = my_products.loc[:, ['name', 'sum', 'quantity']]

print(my_products)