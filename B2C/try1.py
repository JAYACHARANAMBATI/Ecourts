import os
import sys
import time
import json
import requests
import base64
import google.generativeai as genai
from io import BytesIO
from PIL import Image
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# === Configuration ===
CHROME_DRIVER_PATH = r"C:\\Users\\91964\\OneDrive\\Desktop\\Ecourts\\chromedriver-win64\\chromedriver.exe"
os.environ["GOOGLE_API_KEY"] = "AIzaSyBPE2vHlvSFI7AA43iUgJgnr9mR7WQFx6o"
MAX_CAPTCHA_ATTEMPTS = 10

# === CAPTCHA Solver ===
def solve_captcha_with_gemini(img_path, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    with open(img_path, "rb") as img_file:
        image_bytes = img_file.read()
    response = model.generate_content([
        {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(image_bytes).decode()}},
        "Please extract the text shown in this CAPTCHA image."
    ])
    return response.text.strip()

# === Main Function ===
def solve_and_load_case(cnr_number):
    for attempt in range(1, MAX_CAPTCHA_ATTEMPTS + 1):
        print(f"\n🔁 Attempt {attempt} of {MAX_CAPTCHA_ATTEMPTS}")

        # Setup browser
        options = Options()
        options.add_argument('--headless')
        driver = webdriver.Chrome(service=Service(CHROME_DRIVER_PATH), options=options)
        driver.get("https://services.ecourts.gov.in/ecourtindia_v6/")

        try:
            # Enter CNR
            cnr_input = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "cino")))
            cnr_input.clear()
            cnr_input.send_keys(cnr_number)
            print("✅ CNR number entered.")

            # Get CAPTCHA image
            captcha_img_elem = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "captcha_image")))
            captcha_img_url = captcha_img_elem.get_attribute("src")
            if captcha_img_url.startswith("/"):
                captcha_img_url = "https://services.ecourts.gov.in" + captcha_img_url

            img_data = requests.get(captcha_img_url).content
            image = Image.open(BytesIO(img_data))
            image.save("captcha.png")

            # Solve CAPTCHA with Gemini
            captcha_text = solve_captcha_with_gemini("captcha.png", os.environ["GOOGLE_API_KEY"])
            captcha_text = ''.join(filter(str.isalnum, captcha_text))
            print("🔍 Solved CAPTCHA (Gemini):", captcha_text)

            # Submit CAPTCHA
            captcha_input = driver.find_element(By.ID, "fcaptcha_code")
            captcha_input.clear()
            captcha_input.send_keys(captcha_text)

            search_button = driver.find_element(By.ID, "searchbtn")
            driver.execute_script("arguments[0].click();", search_button)
            time.sleep(4)

            # Parse page
            soup = BeautifulSoup(driver.page_source, "html.parser")
            text = soup.get_text(separator="\n")

            if "Case details not found" in text or "Invalid Captcha" in text:
                print("❌ CAPTCHA or CNR error. Restarting...")
                driver.quit()
                continue

            print("✅ Case details loaded successfully.")
            return soup

        except Exception as e:
            print("❌ Unexpected error:", e)
            driver.quit()
            continue

    print("❌ All attempts failed. Exiting.")
    sys.exit()

# === Run Script ===
if __name__ == "__main__":
    cnr_number = input("🔢 Enter CNR Number: ").strip()
    soup = solve_and_load_case(cnr_number)

    # Extract case details
    def extract_value(label, fallback="Not available"):
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2 and label.lower() in cells[0].get_text(strip=True).lower():
                return cells[1].get_text(strip=True)
        for tag in soup.find_all(["span", "div"]):
            if label.lower() in tag.get_text(strip=True).lower():
                next_sib = tag.find_next_sibling()
                if next_sib:
                    return next_sib.get_text(strip=True)
        return fallback

    case_info = {
        "Case Type": extract_value("Case Type"),
        "Filing Number": extract_value("Filing Number"),
        "Registration Number": extract_value("Registration Number"),
        "CNR Number": extract_value("CNR Number"),
        "First Hearing Date": extract_value("First Hearing Date"),
        "Decision Date": extract_value("Decision Date"),
        "Case Status": extract_value("Case Status"),
        "Nature of Disposal": extract_value("Nature of Disposal"),
        "Court Number and Judge": extract_value("Court Number and Judge"),
        "extraction_timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    # Extract case history table
    case_history_table = None
    tables = soup.find_all("table")
    for table in tables:
        # Check if this is the case history table
        if table.get("class") == ["history_table", "table"]:
            case_history_table = str(table)
            break

    # Extract hearing rows from the table
    hearing_rows = []
    if case_history_table:
        # Parse the table again to extract rows
        history_soup = BeautifulSoup(case_history_table, "html.parser")
        rows = history_soup.find_all("tr")[1:]  # Skip header row
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                hearing_rows.append({
                    "Judge": cols[0].get_text(strip=True) if cols[0] else "Not available",
                    "Business on Date": cols[1].get_text(strip=True) if cols[1] else "Not available",
                    "Hearing Date": cols[2].get_text(strip=True) if cols[2] else "Not available",
                    "Purpose of Hearing": cols[3].get_text(strip=True) if cols[3] else "Not available"
                })

    # Build final JSON with case history table
    case_json = {
        "case_info": case_info,
        "hearings": hearing_rows,
        "case_history_table": case_history_table  # Include the raw HTML table
    }

    # Save to file
    filename = f"case_{case_info['CNR Number'].split('(')[0].replace('/', '_')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(case_json, f, indent=4, ensure_ascii=False)

    # Display
    print("\n=== Case Details ===")
    for field, value in case_info.items():
        if field != "extraction_timestamp":
            print(f"{field}: {value}")

    print(f"\n✅ Saved to: {filename}")
