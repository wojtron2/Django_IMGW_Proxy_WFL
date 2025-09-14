# IMGW Proxy with lat/lon to teryt conversion from geoportal API

Aplikacja pozwala na wyswietlenie ostrzezen IMGW dla danej dlugosci lat/lon (zwraca w JSON)


---
Wymagania:

- Python 3.12 (lub zgodny z projektem)
- Git

## Przygotowanie katalogu dla projektu
Win+R -> cmd

cd C:\

mkdir IMGW_Proxy_WFL

cd IMGW_Proxy_WFL

- Nastepnie pobieranie projektu:

git clone https://github.com/wojtron2/Django_IMGW_Proxy_WFL

cd Django_IMGW_Proxy_WFL\imgw_proxy2\imgwproj

- Uruchamianie projektu

py -3.12 -m venv .venv

.venv\Scripts\activate.bat



python -m pip install --upgrade pip

pip install -r requirements.txt


python manage.py migrate


(Opcjonalnie) Utworzenie użytkownika admina dla sprawdzenia bazy
python manage.py createsuperuser


python manage.py runserver


---

##


Uzywa feed IMGW do odczytywania informacji o warningach dla danego TERYT:

https://danepubliczne.imgw.pl/api/data/warningsmeteo

oraz dokonuje odczytywanie informacji jaki TERYT wypada dla danej lat/lon z geoportalu, przykladowe query do geoportalu:

https://mapy.geoportal.gov.pl/wss/ims/maps/PRG_gugik_wyszukiwarka/MapServer/1/query?f=pjson&geometry=%7B%22x%22%3A20.69%2C%22y%22%3A49.62%7D&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=teryt%2Cnazwa&returnGeometry=false

dla zmniejszenia czasu odpowiedzi (kto zna geoportal wie ze potrafi czasem zamulic) i unikniecia zapytan do geoportalu dla wartosci lat/lon ktore byly juz sprawdzane zastosowano konfigurowalne cache'owanie kombinacji lat/lon - TERYT dla redukcji obciazenia serwera, wyłączalne zmienną w settings, czyli kazda kombinacja lat/lon -> teryt juz ustalona bedzie zapisana w bazie, co optymalizuje obciazenie serwera,

METEO_CACHE_ENABLED = True  # toggle use of TERYT - lat/lon cache





Mozna sprawdzic komunikaty IMGW dla danego lat/lon:

http://127.0.0.1:8000/api/meteo/warnings?lat=52.2297&lon=21.0122

http://127.0.0.1:8000/api/meteo/warnings?lat=52.2000&lon=20.6170

http://127.0.0.1:8000/api/meteo/warnings?lat=50.0614&lon=19.9372

http://127.0.0.1:8000/api/meteo/warnings?lat=52.4064&lon=16.9252

http://127.0.0.1:8000/api/meteo/warnings?lat=49.62&lon=20.69




Uzyskujemy w ten sposob JSONa z ostrzeżeniami IMGW dla danego powiatu znajdujacego sie na danej lat/lon oraz numer teryt dla tego powiatu, nazwe powiatu, czas obowiazywania od do, poziom, prawdopodobienstwo wystapienia,tytul ostrzezenia, tresc ostrzezenia i kto je wydał oraz kiedy,


Jesli serwer IMGW niedostepny wczyta tylko dotychczasowe ostrzezenia z bazy, kazdy odczyt ma w jsonie informacje czy IMGW dziala i czy prezentowane dane sa wlasnie odswiezone,
"imgw_available": true oznacza ze dane zostaly odswiezone i prezentowane ostrzezenie jest wlasnie sprawdzone na serwerze IMGW
imgw_available": false oznacza ze serwer IMGW nie odpowiedzial i prezentowane dane są z bazy danych (najnowsze zapisane ostrzezenie),


Kazde wywolanie powyzszego api dokona zapisu danego ostrzezenia w bazie, ale jest tez mechanizm pilnujacy by zapisywaly sie tylko ostrzezenia ktorych jeszcze nie ma w bazie by unikac duplikatow,





dodatkowo wariant odczytujacy tylko aktualne ostrzezenia, bez zapisywania do bazy

http://127.0.0.1:8000/api/meteo/warnings/live?lat=52.2297&lon=21.0122


odczyt ostrzezen zapisanych w bazie

http://127.0.0.1:8000/api/meteo/history?lat=52.2297&lon=21.0122

lub tez uwzgledniajacy zakres czasowy

http://127.0.0.1:8000/api/meteo/history?lat=52.2297&lon=21.0122&since=2025-09-01&until=2025-09-15


jest tez opcjonalnie wersja do odczytu gdy znamy teryt

http://127.0.0.1:8000/api/meteo/history/teryt/1465


jest rowniez i status (czas ostatniego fetcha)

http://127.0.0.1:8000/api/meteo/status



jezeli chcemy zobaczyc baze danych w GUI jak sie aktualizuje i pojawiaja nowe wpisy korzystajac z adminpanel, 
to można stworzyc usera:

python manage.py createsuperuser

i wtedy sprawdzic sobie recznie nowe rekordy ostrzezen w bazie

http://127.0.0.1:8000/admin/



