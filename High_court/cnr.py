import os
import time
import json
import base64
import google.generativeai as genai
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ===== CONFIG =====
CHROME_DRIVER_PATH = r"C:\\Users\\91964\\OneDrive\\Desktop\\Ecourts\\chromedriver-win64\\chromedriver.exe"
os.environ["GOOGLE_API_KEY"] = "AIzaSyAxGTzN-8qA8FSmGZtI3J0L2gjMpkO6MM4"  # Replace with your Gemini API key
HC_URL = "https://hcservices.ecourts.gov.in/hcservices/main.php"
HEADLESS_MODE = False
MAX_ATTEMPTS = 10
# ==================

def solve_captcha_with_gemini_from_bytes(image_bytes, api_key):
    """Solve CAPTCHA from raw bytes using Gemini Flash 1.5"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content([
        {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(image_bytes).decode()}},
        "Extract the text from this CAPTCHA image. Return only alphanumeric characters, no spaces."
    ])
    return ''.join(filter(str.isalnum, response.text.strip()))

def open_browser():
    """Launch Chrome browser"""
    options = Options()
    if HEADLESS_MODE:
        options.add_argument("--headless")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return webdriver.Chrome(service=Service(CHROME_DRIVER_PATH), options=options)

def extract_case_details(soup):
    """Extract main case details"""
    def extract_value(label):
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2 and label.lower() in cells[0].get_text(strip=True).lower():
                return cells[1].get_text(strip=True)
        return "Not available"

    return {
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

def extract_hearing_history(soup):
    """Extract hearing history table"""
    hearings = []
    hearing_tables = soup.find_all("table")
    for table in hearing_tables:
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if any("Hearing" in h for h in headers):
            for row in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 4:
                    hearings.append({
                        "Hearing Date": cells[0],
                        "Business": cells[1],
                        "Purpose": cells[2],
                        "Next Hearing Date": cells[3]
                    })
    return hearings

def extract_case_history_div(soup):
    """Extract and structure all data inside #caseHistoryDiv"""
    case_history_div = soup.find("div", {"id": "caseHistoryDiv"})
    if not case_history_div:
        return {}

    data = {}
    tables = case_history_div.find_all("table")

    for idx, table in enumerate(tables, start=1):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows_data = []
        for row in table.find_all("tr")[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if headers and cells and len(headers) == len(cells):
                row_dict = {headers[i]: cells[i] for i in range(len(headers))}
                rows_data.append(row_dict)
        data[f"table_{idx}"] = rows_data

    return data

def extract_case_business_div(soup):
    """Extract and structure all data inside #caseBusinessDiv4"""
    case_business_div = soup.find("div", {"id": "caseBusinessDiv4"})
    if not case_business_div:
        return {}

    data = {}
    tables = case_business_div.find_all("table")

    for idx, table in enumerate(tables, start=1):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows_data = []
        for row in table.find_all("tr")[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if headers and cells and len(headers) == len(cells):
                row_dict = {headers[i]: cells[i] for i in range(len(headers))}
                rows_data.append(row_dict)
        data[f"table_{idx}"] = rows_data

    return data

def all_fields_not_available(case_info):
    """Check if all extracted fields are 'Not available'"""
    for key, value in case_info.items():
        if key != "extraction_timestamp" and value != "Not available":
            return False
    return True

def fetch_case_data(cnr_number):
    driver = open_browser()
    attempt = 0

    while attempt < MAX_ATTEMPTS:
        attempt += 1
        print(f"\n🔁 Attempt {attempt} of {MAX_ATTEMPTS}")
        driver.get(HC_URL)

        try:
            # Enter CNR
            cnr_input = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "cino")))
            cnr_input.clear()
            cnr_input.send_keys(cnr_number)
            print("✅ CNR entered.")

            # Capture CAPTCHA directly from browser
            captcha_elem = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "captcha_image")))
            captcha_bytes = captcha_elem.screenshot_as_png

            # Solve CAPTCHA
            captcha_text = solve_captcha_with_gemini_from_bytes(captcha_bytes, os.environ["GOOGLE_API_KEY"])
            print(f"🔍 Solved CAPTCHA: {captcha_text}")

            # Enter CAPTCHA & submit
            captcha_input = driver.find_element(By.ID, "captcha")
            captcha_input.clear()
            captcha_input.send_keys(captcha_text)
            driver.find_element(By.ID, "searchbtn").click()

            # Wait for page to load and check for errors
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            page_text = soup.get_text(separator="\n").strip()

            if "Invalid Captcha" in page_text:
                print("❌ Invalid CAPTCHA detected, retrying...")
                continue

            if "Case details not found" in page_text:
                print("⚠️ Case not found for given CNR.")
                return None

            # Extract Data
            case_info = extract_case_details(soup)
            hearings = extract_hearing_history(soup)
            case_history = extract_case_history_div(soup)
            case_business = extract_case_business_div(soup)

            # Retry if all fields are empty
            if all_fields_not_available(case_info):
                print("❌ All fields are 'Not available'. Treating as CAPTCHA failure. Retrying...")
                continue

            print("✅ Data retrieved successfully.")
            return {
                "case_info": case_info,
                "hearings": hearings,
                "case_history_div": case_history,
                "case_business_div4": case_business
            }

        except Exception as e:
            print(f"❌ Error: {e}")
            continue

    print("❌ Max attempts reached. No valid data found.")
    return None
    driver.quit()

if __name__ == "__main__":
    cnr_number = input("Enter CNR Number: ").strip()
    case_data = fetch_case_data(cnr_number)

    if case_data:
        # Show Case Info
        print("\n📜 Case Details:")
        for k, v in case_data["case_info"].items():
            if k != "extraction_timestamp":
                print(f"{k}: {v}")

        # Save JSON
        with open("hc_case_data.json", "w", encoding="utf-8") as f:
            json.dump(case_data, f, ensure_ascii=False, indent=2)
        print("\n✅ Data saved to hc_case_data.json")
    else:
        print("\n⚠️ No data extracted.")
