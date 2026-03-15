import requests
import csv
import os
import re
import sys
import time
import urllib3
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Configuration ---
VERIFIK_API_KEY = os.environ.get("VERIFIK_API_KEY", "YOUR_VERIFIK_API_KEY_HERE")
VERIFIK_API_BASE_URL = "https://api.verifik.co/v1/venezuela/cedula"
OUTPUT_CSV_FILE = "cedula_data.csv"

PNP_BASE_URL = "https://www.sistemaspnp.com"
PNP_GET_CAPTCHA_URL_PATH = "/cedula/"
PNP_CAPTCHA_PATTERN = r'(¿Cuánto es \d+\s*[+\-*/]\s*\d+\?)'
PNP_FORM_CEDULA_FIELD = "txtCedula"
PNP_FORM_CAPTCHA_FIELD = "txtCaptcha"
PNP_FORM_BUTTON_XPATH = "/html/body/div[1]/div/div/div/form/div[4]/button"

# --- Helpers ---

def normalize_cedula(cedula):
    cedula = str(cedula).strip().upper()
    return cedula if '-' in cedula else f"V-{cedula}"

def save_to_csv(data_list, filename):
    if not data_list:
        print("No data to save.")
        return
    headers = sorted(list(set().union(*(d.keys() for d in data_list))))
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data_list)
        print(f"Data saved to '{filename}'")
    except IOError as e:
        print(f"Error saving CSV: {e}")

def solve_pnp_captcha(question):
    match = re.search(r'(\d+)\s*([+\-*/])\s*(\d+)', question)
    if not match: return None
    n1, op, n2 = int(match.group(1)), match.group(2), int(match.group(3))
    try:
        if op == '+': return str(n1 + n2)
        if op == '-': return str(n1 - n2)
        if op == '*': return str(n1 * n2)
        if op == '/': return str(n1 // n2) if n2 != 0 else None
    except: return None
    return None

# --- Data Fetching ---

def get_verifik_data(cedula):
    normalized = normalize_cedula(cedula)
    headers = {"Authorization": f"Bearer {VERIFIK_API_KEY}", "Content-Type": "application/json"}
    try:
        resp = requests.get(f"{VERIFIK_API_BASE_URL}/{normalized}", headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data") if data.get("success") else None
    except Exception as e:
        print(f"Verifik error for {normalized}: {e}")
        return None

def get_pnp_data(cedula):
    normalized = normalize_cedula(cedula)

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox") # Crucial para Linux/Fedora
    chrome_options.add_argument("--disable-dev-shm-usage") # Evita errores de memoria compartida
    # Agregamos un User-Agent real para evitar bloqueos
    chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 5) # Aumentamos el margen de espera

    try:
        driver.get(f"{PNP_BASE_URL}{PNP_GET_CAPTCHA_URL_PATH}")

        # Esperar a que el cuerpo de la página cargue para buscar el captcha
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        # Extraer el texto completo para el regex
        page_content = driver.find_element(By.TAG_NAME, "body").text
        captcha_match = re.search(PNP_CAPTCHA_PATTERN, page_content)

        if not captcha_match:
            return {"cedula": normalized, "fuente": "Sistemas PNP", "status": "Captcha no visible"}

        solution = solve_pnp_captcha(captcha_match.group(1))

        # Interactuar con los campos
        wait.until(EC.visibility_of_element_located((By.NAME, PNP_FORM_CEDULA_FIELD))).send_keys(normalized)
        driver.find_element(By.NAME, PNP_FORM_CAPTCHA_FIELD).send_keys(solution)

        # Click en el botón usando un selector más genérico pero seguro
        submit_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-primary, button[type='submit']")))
        submit_btn.click()

        # Espera intencional corta para que el DOM se actualice tras el click
        time.sleep(3)

        # Analizar resultados con BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        # Buscamos cualquier contenedor que tenga texto relevante
        target = soup.select_one("div.alert-success, div.card-body, .container")

        if target and len(target.get_text(strip=True)) > 3: # Validamos que traiga algo real
            return {
                "cedula": normalized,
                "fuente": "Sistemas PNP",
                "datos_tarjeta": target.get_text(strip=True, separator=' ')
            }

        return {"cedula": normalized, "fuente": "Sistemas PNP", "status": "No se encontraron datos"}

    except Exception as e:
        return {"cedula": normalized, "fuente": "Sistemas PNP", "status": f"Error: {str(e)[:50]}"}
    finally:
        driver.quit()

# --- Main ---

if __name__ == "__main__":
    print("1. Verifik API\n2. Sistemas PNP (Scraper)")
    choice = input("Choice (1/2): ")
    
    print("1. Manual\n2. File")
    input_type = input("Input (1/2): ")
    
    cedulas = []
    if input_type == '1':
        while True:
            c = input("Cedula (Enter to finish): ").strip()
            if not c: break
            cedulas.append(c)
    else:
        fname = input("File path: ")
        try:
            with open(fname, 'r', encoding='utf-8') as f:
                cedulas = [line.strip() for line in f if line.strip()]
        except Exception as e: print(f"File error: {e}")

    results = []
    for c in cedulas:
        if choice == '1':
            res = get_verifik_data(c)
            if res: res['fuente'] = 'Verifik API'
            results.append(res or {"cedula": c, "fuente": "Verifik API", "status": "Error"})
        else:
            results.append(get_pnp_data(c) or {"cedula": c, "fuente": "Sistemas PNP", "status": "Error"})

    save_to_csv(results, OUTPUT_CSV_FILE)
