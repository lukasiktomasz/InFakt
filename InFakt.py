import requests
import json
import csv
import time
import re
from datetime import datetime

def wczytaj_konfiguracje():
    """Wczytuje konfigurację z pliku config.json"""
    with open("config.json", "r") as plik:
        return json.load(plik)

def pobierz_nieoplacone_faktury(api_key, api_url):
    """Pobiera wszystkie faktury z API inFakt, zwiększając limit zwracanych rekordów i logując walutę."""
    url = f"{api_url}/invoices.json"
    headers = {
        "X-inFakt-ApiKey": api_key,
        "Accept": "application/json"
    }
    
    faktury = []
    page = 1  # Licznik stron
    while url:
        print(f"🔄 Pobieranie strony {page}... URL: {url}")
        try:
            response = requests.get(url, headers=headers, timeout=10)  # Timeout 10 sekund
            if response.status_code == 200:
                dane = response.json()

                entities = dane.get("entities", [])
                if not entities:
                    print(f"⚠️ Brak danych na stronie {page}. Kończę pobieranie.")
                    break

                faktury.extend(entities)
                url = dane.get("metainfo", {}).get("next")  # Następna strona (jeśli istnieje)
                print(f"✅ Pobrano stronę {page}. Łączna liczba faktur: {len(faktury)}")
                page += 1
            else:
                print(f"❌ Błąd podczas pobierania strony {page}: {response.status_code} - {response.text}")
                break
        except requests.exceptions.Timeout:
            print(f"⚠️ Timeout podczas pobierania strony {page}. Ponawiam próbę...")
        except requests.exceptions.RequestException as e:
            print(f"❌ Błąd połączenia podczas pobierania strony {page}: {e}")
            break

    print(f"📋 Łącznie pobrano {len(faktury)} faktur.")

    print("\n📌 Lista nieopłaconych faktur do sprawdzenia:\n")
    niezaplacone_faktury = [f for f in faktury if f.get('left_to_pay', 0) > 0]  # Filtrujemy tylko nieopłacone faktury

    for faktura in niezaplacone_faktury:
        numer_faktury = faktura.get('number')
        kwota_brutto = faktura.get('gross_price') / 100  
        waluta_faktury = faktura.get('currency')  
        notatki = faktura.get('notes', '')

        numer_zamowienia = None
        match = re.search(r"PO-\d+-\d+", notatki)
        if match:
            numer_zamowienia = match.group(0)

        print(f"   📄 Faktura: {numer_faktury} | Kwota: {kwota_brutto:.2f} {waluta_faktury} | Zamówienie: {numer_zamowienia}")

    return niezaplacone_faktury







def wczytaj_historie_bankowa(plik_csv):
    """Wczytuje historię konta bankowego z pliku CSV, uwzględniając walutę."""
    historia = []
    with open(plik_csv, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        rows = list(reader)  # Wczytujemy całość do listy
        
        if not rows:
            print("❌ Plik CSV jest pusty!")
            return historia
        
        # Pobieramy walutę z pierwszego wiersza
        waluta_csv = rows[0][0].strip()
        print(f"📌 Waluta przelewów w pliku CSV: {waluta_csv}")

        for row in rows[1:]:  # Pomijamy pierwszy wiersz (nagłówek)
            if len(row) >= 6:
                historia.append({
                    "data": row[1],  # Kolumna 2 - Data wpływu
                    "opis": row[2],  # Kolumna 3 - Opis przelewu
                    "kwota": float(row[5].replace(',', '.')) * 100,  # Kolumna 6 - Kwota, konwersja na grosze
                    "waluta": waluta_csv  # Dodajemy walutę do wpisu
                })

    return historia


import re

def znajdz_plate_faktury(faktura, historia):
    """Sprawdza, czy dana faktura została opłacona na podstawie historii konta bankowego po numerze zamówienia i walucie."""
    kwota_brutto = faktura.get('gross_price')  # Pobieramy kwotę brutto faktury w groszach
    waluta_faktury = faktura.get('currency')  # Pobieramy walutę faktury
    notatki = faktura.get('notes', '')  # Notatki faktury, zawierają numer zamówienia
    
    # Wyciągnięcie numeru zamówienia z notatek faktury
    numer_zamowienia = None
    match = re.search(r"PO-\d+-\d+", notatki)
    if match:
        numer_zamowienia = match.group(0)  # Pobieramy numer zamówienia

    if not numer_zamowienia:
        print(f"⚠️ Faktura {faktura.get('number')} ({kwota_brutto/100:.2f} {waluta_faktury}) nie zawiera numeru zamówienia w notatkach.")
        return None

    for przelew in historia:
        opis = przelew["opis"]

        # Sprawdzamy, czy numer zamówienia pojawia się w opisie przelewu i czy waluta się zgadza
        if numer_zamowienia in opis and przelew["waluta"] == waluta_faktury:
            if przelew["kwota"] == kwota_brutto:
                return przelew["data"]

    # Jeśli faktura nie została odnaleziona, wypisujemy dodatkowe informacje
    print(f"⚠️ Faktura {faktura.get('number')} ({kwota_brutto/100:.2f} {waluta_faktury}) nie została odnaleziona w historii bankowej.")
    print(f"   📌 Szukano numeru zamówienia: {numer_zamowienia}")
    print(f"   💰 Szukano kwoty: {kwota_brutto/100:.2f} {waluta_faktury}")

    return None






def oznacz_fakture_jako_zaplacona(api_key, api_url, faktura_uuid, data_platnosci):
    """Oznacza fakturę jako zapłaconą poprzez API inFakt (asynchronicznie)."""
    url = f"{api_url}/async/invoices/{faktura_uuid}/paid.json?paid_date={data_platnosci}"
    headers = {
        "X-inFakt-ApiKey": api_key,
        "Accept": "application/json"
    }
    
    response = requests.post(url, headers=headers)
    
    if response.status_code == 201:
        dane = response.json()
        task_reference_number = dane.get("invoice_task_reference_number")
        print(f"Faktura {faktura_uuid} została przyjęta do oznaczenia jako zapłacona. Numer zadania: {task_reference_number}")
        return task_reference_number
    else:
        print(f"Błąd oznaczania faktury {faktura_uuid} jako zapłaconej: {response.status_code}")
        print(f"Treść odpowiedzi: {response.text}")
        return None

def sprawdz_status_zadania(api_key, api_url, task_reference_number):
    """Sprawdza status asynchronicznego zadania oznaczania faktury jako zapłaconej."""
    url = f"{api_url}/async/invoice_tasks/{task_reference_number}.json"
    headers = {
        "X-inFakt-ApiKey": api_key,
        "Accept": "application/json"
    }

    for _ in range(5):  # Maksymalnie 5 prób
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            dane = response.json()
            return dane.get("processing_description")
        
        elif response.status_code == 500:
            print(f"⚠️ Błąd 500 - Serwer inFakt ma problem. Ponawianie za 1 sekundę...")
            time.sleep(1)  # Skrócone oczekiwanie
        else:
            print(f"❌ Błąd sprawdzania statusu zadania: {response.status_code}, {response.text}")
            return None
    
    print("❌ Nie udało się uzyskać statusu po 5 próbach.")
    return None


if __name__ == "__main__":
    print("Wczytywanie konfiguracji...")
    config = wczytaj_konfiguracje()
    API_KEY = config.get("api_key", "")
    API_URL = config.get("api_url", "")
    
    if not API_KEY or not API_URL:
        print("Błąd: Brak klucza API lub adresu API w pliku konfiguracyjnym.")
    else:
        print("Pobieranie faktur...")
        faktury = pobierz_nieoplacone_faktury(API_KEY, API_URL)
        
        print("Wczytywanie historii bankowej...")
        historia_bankowa = wczytaj_historie_bankowa("historia_2025-02-04.csv")
        
        if faktury:
            print("\n📌 Lista niezapłaconych faktur do sprawdzenia:\n")
            for faktura in faktury:
                if faktura.get('status') != "paid":  # Filtrujemy tylko niezapłacone faktury
                    numer_faktury = faktura.get('number')
                    kwota_brutto = faktura.get('gross_price')  # Kwota w groszach
                    
                    # Szukamy numeru zamówienia w notatkach faktury
                    numer_zamowienia = None
                    notatki = faktura.get('notes', '')
                    match = re.search(r"PO-\d+-\d+", notatki)
                    if match:
                        numer_zamowienia = match.group(0)
                    
                    print(f"   📄 Faktura: {numer_faktury} | Kwota: {kwota_brutto/100:.2f} PLN | Zamówienie: {numer_zamowienia}")

            print("\n🔍 Rozpoczynam wyszukiwanie płatności w historii bankowej...\n")
            for faktura in faktury:
                status = faktura.get('status')
                faktura_uuid = faktura.get('uuid')

                if status != "paid":  # Wybieramy tylko niezapłacone faktury
                    data_platnosci = znajdz_plate_faktury(faktura, historia_bankowa)
                    
                    if data_platnosci:
                        task_reference_number = oznacz_fakture_jako_zaplacona(API_KEY, API_URL, faktura_uuid, data_platnosci)
                        
                        if task_reference_number:
                            print(f"Oczekiwanie na zakończenie operacji oznaczania faktury {faktura_uuid}...")
                            time.sleep(1)  # Skrócone oczekiwanie
                            status_zadania = sprawdz_status_zadania(API_KEY, API_URL, task_reference_number)

                            while status_zadania and status_zadania != "Zakończone":
                                print("Oczekiwanie na zakończenie operacji...")
                                time.sleep(1)
                                status_zadania = sprawdz_status_zadania(API_KEY, API_URL, task_reference_number)

                            print(f"✅ Faktura {faktura_uuid} została pomyślnie oznaczona jako zapłacona!")
                    
                    else:
                        print(f"⚠️ Faktura {faktura_uuid} nie została odnaleziona w historii bankowej.")
                
                # Skrypt kontynuuje i przechodzi do następnej faktury
            print("✅ Wszystkie niezapłacone faktury zostały sprawdzone.")

        else:
            print("Brak niezapłaconych faktur do przetworzenia.")
