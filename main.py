import requests
import csv
import os
import re
import sys
import time
import urllib3
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
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
    
    options = uc.ChromeOptions()
    options.add_argument("--headless") # Modo invisible
    options.add_argument("--no-sandbox") 
    options.add_argument("--disable-dev-shm-usage")
    
    # undetected-chromedriver se encarga de descargar el driver correcto solo
    driver = uc.Chrome(options=options)
    wait = WebDriverWait(driver, 20)
    
    try:
        driver.get(f"{PNP_BASE_URL}{PNP_GET_CAPTCHA_URL_PATH}")
        
        # Extraer captcha del body text (más seguro que page_source)
        body_text = wait.until(EC.presence_of_element_located((By.TAG_NAME, "body"))).text
        captcha_match = re.search(PNP_CAPTCHA_PATTERN, body_text)
        
        if not captcha_match:
            return {"cedula": normalized, "status": "Captcha no encontrado"}
            
        solution = solve_pnp_captcha(captcha_match.group(1))
        print(f"Captcha solved: {solution}") # Debug
        
        # Llenar campos
        driver.find_element(By.NAME, PNP_FORM_CEDULA_FIELD).send_keys(normalized)
        driver.find_element(By.NAME, PNP_FORM_CAPTCHA_FIELD).send_keys(solution)
        
        # Click en el botón de envío
        submit_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']")))
        submit_btn.click()
        
        # Esperar a que el resultado cargue (ajustar selector según la web)
        time.sleep(5) 
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        # Buscamos el div que mencionaste en tu código original
        target = soup.select_one("body > div:nth-of-type(1) > div:nth-of-type(1)")
        
        if target:
            return {
                "cedula": normalized, 
                "fuente": "Sistemas PNP", 
                "datos": target.get_text(strip=True, separator=' ')
            }
        
        return {"cedula": normalized, "status": "No se encontraron datos"}
        
    except Exception as e:
        # Esto capturará el error y evitará que el script se detenga
        return {"cedula": normalized, "status": f"Error: {type(e).__name__}"}
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
