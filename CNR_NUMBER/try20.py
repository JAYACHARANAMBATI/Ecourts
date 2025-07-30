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
import pytesseract
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from concurrent.futures import ThreadPoolExecutor

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA


CHROME_DRIVER_PATH = r"C:\\Users\\91964\\OneDrive\\Desktop\\Ecourts\\chromedriver-win64\\chromedriver.exe"
os.environ["GOOGLE_API_KEY"] = "AIzaSyBPE2vHlvSFI7AA43iUgJgnr9mR7WQFx6o"
MAX_CAPTCHA_ATTEMPTS = 10

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

# === CAPTCHA Solver and Page Loader Loop ===
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

            # Use Gemini to solve CAPTCHA
            captcha_text = solve_captcha_with_gemini("captcha.png", os.environ["GOOGLE_API_KEY"])
            captcha_text = ''.join(filter(str.isalnum, captcha_text))
            print("🔍 Solved CAPTCHA (Gemini):", captcha_text)

            # Enter CAPTCHA
            captcha_input = driver.find_element(By.ID, "fcaptcha_code")
            captcha_input.clear()
            captcha_input.send_keys(captcha_text)

            search_button = driver.find_element(By.ID, "searchbtn")
            driver.execute_script("arguments[0].click();", search_button)
            time.sleep(4)

            # Validate Page
            soup = BeautifulSoup(driver.page_source, "html.parser")
            text = soup.get_text(separator="\n")
            if "Case details not found" in text or "Invalid Captcha" in text:
                print("❌ CAPTCHA or CNR error on page. Restarting browser.")
                driver.quit()
                continue

            links = driver.find_elements(By.XPATH, "//a[contains(@onclick, 'viewBusiness')]")
            if len(links) == 0:
                print("❌ 0 hearings found. Likely CAPTCHA failed. Restarting.")
                driver.quit()
                continue

            onclick_data_list = [link.get_attribute("onclick") for link in links]

            print(f"📅 Found {len(onclick_data_list)} hearing entries.")
            return soup, onclick_data_list

        except Exception as e:
            print("❌ Unexpected error:", e)
            driver.quit()
            continue

    print("❌ All attempts failed. Exiting.")
    sys.exit()


# === Extract Individual Hearing (Parallel) ===
def extract_hearing_data(onclick_data):
    options = Options()
    options.add_argument('--headless')
    driver = webdriver.Chrome(service=Service(CHROME_DRIVER_PATH), options=options)

    try:
        driver.get("https://services.ecourts.gov.in/ecourtindia_v6/")
        time.sleep(2)
        driver.execute_script(onclick_data)
        time.sleep(2.5)

        full_text = driver.execute_script("return document.body.innerText")
        lines = full_text.splitlines()

        business = next((line for line in lines if "Business" in line), "Business: Not mentioned").split(":", 1)[-1].strip()
        purpose = next((line for line in lines if "Next Purpose" in line), "Next Purpose: Not mentioned").split(":", 1)[-1].strip()
        hearing_date = next((line for line in lines if "Date" in line), "Date: Not mentioned").split(":", 1)[-1].strip()
        next_hearing = next((line for line in lines if "Next Hearing Date" in line), "Next Hearing Date: Not mentioned").split(":", 1)[-1].strip()

        return {
            "Hearing Date": hearing_date or "Not available",
            "Court": "Trial Court",
            "Business": business or "Not available",
            "Purpose": purpose or "Not available",
            "Next Hearing Date": next_hearing or "Not available"
        }

    except Exception as e:
        print(f"❌ Thread error: {e}")
        return None
    finally:
        driver.quit()


# === Run main logic ===
if __name__ == "__main__":
    cnr_number = input("🔢 Enter CNR Number: ").strip()
    soup, onclick_data_list = solve_and_load_case(cnr_number)

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

    # Print case details
    print("\n=== Case Details ===")
    for field, value in case_info.items():
        if field != "extraction_timestamp":
            print(f"{field}: {value}")

    case_json = {
        "case_info": case_info,
        "hearings": []
    }

    # Dynamic thread count
    num_links = len(onclick_data_list)
    max_threads = min(num_links, 10)
    print(f"⚙️ Spawning {max_threads} parallel threads for extraction...")

    # Parallel extraction
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        results = list(executor.map(extract_hearing_data, onclick_data_list))

    case_json["hearings"] = [res for res in results if res]

    # Save to JSON
    with open("case_data.json", "w", encoding="utf-8") as f:
        json.dump(case_json, f, ensure_ascii=False, indent=2)
    print("✅ All data saved to case_data.json")


