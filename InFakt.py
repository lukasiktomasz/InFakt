import requests
import json
import csv
import time
from datetime import datetime

def wczytaj_konfiguracje():
    """Wczytuje konfigurację z pliku config.json"""
    with open("config.json", "r") as plik:
        return json.load(plik)

def pobierz_faktury(api_key, api_url):
    """Pobiera listę faktur z API inFakt."""
    url = f"{api_url}/invoices.json"
    headers = {
        "X-inFakt-ApiKey": api_key,
        "Accept": "application/json"
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        dane = response.json()
        return dane.get("entities", [])  # Pobieramy listę faktur
    else:
        print(f"Błąd pobierania faktur: {response.status_code}, {response.text}")
        return None

def wczytaj_historie_bankowa(plik_csv):
    """Wczytuje historię konta bankowego z pliku CSV."""
    historia = []
    with open(plik_csv, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if len(row) >= 6:
                historia.append({
                    "data": row[1],  # Kolumna 2 - Data wpływu
                    "opis": row[2],  # Kolumna 3 - Opis przelewu
                    "kwota": float(row[5].replace(',', '.')) * 100  # Kolumna 6 - Kwota, konwersja na grosze
                })
    return historia

def znajdz_plate_faktury(faktura, historia):
    """Sprawdza, czy dana faktura została opłacona na podstawie historii konta bankowego."""
    numer_faktury = faktura.get('number')
    kwota_brutto = faktura.get('gross_price')
    notatki = faktura.get('notes', '').split('\n')[0]  # Pierwsza linijka notatek
    
    for przelew in historia:
        if numer_faktury in przelew["opis"] or notatki in przelew["opis"]:
            if przelew["kwota"] == kwota_brutto:
                return przelew["data"]
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
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        dane = response.json()
        return dane.get("processing_description")
    else:
        print(f"Błąd sprawdzania statusu zadania: {response.status_code}, {response.text}")
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
        faktury = pobierz_faktury(API_KEY, API_URL)
        
        print("Wczytywanie historii bankowej...")
        historia_bankowa = wczytaj_historie_bankowa("historia_2025-01-29_70109020530000000160301736.csv")
        
        if faktury:
            print("Przetwarzanie niezapłaconych faktur...")
            for faktura in faktury:
                status = faktura.get('status')
                faktura_uuid = faktura.get('uuid')
                if status != "paid":  # Wybieramy tylko niezapłacone faktury
                    data_platnosci = znajdz_plate_faktury(faktura, historia_bankowa)
                    if data_platnosci:
                        task_reference_number = oznacz_fakture_jako_zaplacona(API_KEY, API_URL, faktura_uuid, data_platnosci)
                        if task_reference_number:
                            print(f"Oczekiwanie na zakończenie operacji oznaczania faktury {faktura_uuid}...")
                            time.sleep(5)  # Poczekaj kilka sekund przed sprawdzeniem statusu
                            status_zadania = sprawdz_status_zadania(API_KEY, API_URL, task_reference_number)
                            while status_zadania and status_zadania != "Zakończone":
                                print("Oczekiwanie na zakończenie operacji...")
                                time.sleep(10)
                                status_zadania = sprawdz_status_zadania(API_KEY, API_URL, task_reference_number)
                            print(f"Faktura {faktura_uuid} została pomyślnie oznaczona jako zapłacona!")
                    else:
                        print(f"Faktura {faktura_uuid} nie została odnaleziona w historii bankowej.")
        else:
            print("Brak niezapłaconych faktur do wyświetlenia.")
