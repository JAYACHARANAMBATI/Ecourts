import os
import time
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
import base64
import google.generativeai as genai
import concurrent.futures
from bs4 import BeautifulSoup

os.environ["GOOGLE_API_KEY"] = "AIzaSyAxGTzN-8qA8FSmGZtI3J0L2gjMpkO6MM4"
genai.configure(api_key="AIzaSyBPE2vHlvSFI7AA43iUgJgnr9mR7WQFx6o")

driver_path = r"C:\Users\91964\OneDrive\Desktop\Ecourts\chromedriver-win64\chromedriver.exe"
options = webdriver.ChromeOptions()
options.add_argument("--headless=new")  # Use new headless mode for Chrome
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")
service = Service(driver_path)
driver = webdriver.Chrome(service=service, options=options)
wait = WebDriverWait(driver, 15)

driver.get("https://services.ecourts.gov.in/ecourtindia_v6/?p=casestatus/index&app_token=1c847047b60f905b3ec1f8455ae475a3240ff6ec263ab395e0eadce41cd6de0e")

# === Helper to choose from dropdown ===
def choose_option_from_select(select_element, prompt):
    options = select_element.options[1:]  # Skip first default
    for i, option in enumerate(options, 1):
        print(f"{i}. {option.text.strip()}")
    while True:
        try:
            choice = int(input(prompt))
            if 1 <= choice <= len(options):
                selected_text = options[choice - 1].text.strip()
                select_element.select_by_index(choice)
                return selected_text
            else:
                print("Invalid number.")
        except ValueError:
            print("Please enter a valid number.")


wait.until(EC.presence_of_element_located((By.ID, "sess_state_code")))
state_dropdown = Select(driver.find_element(By.ID, "sess_state_code"))
print("\nSelect State:")
selected_state = choose_option_from_select(state_dropdown, "Enter choice number for State: ")
time.sleep(2)


wait.until(EC.presence_of_element_located((By.ID, "sess_dist_code")))
district_dropdown = Select(driver.find_element(By.ID, "sess_dist_code"))
print(f"\nSelect District in {selected_state}:")
selected_district = choose_option_from_select(district_dropdown, "Enter choice number for District: ")
time.sleep(2)


wait.until(EC.presence_of_element_located((By.ID, "court_complex_code")))
court_dropdown = Select(driver.find_element(By.ID, "court_complex_code"))
print(f"\nSelect Court Complex in {selected_district}:")
selected_court = choose_option_from_select(court_dropdown, "Enter choice number for Court Complex: ")
time.sleep(2)


try:
    advocate_tab_button = wait.until(EC.element_to_be_clickable((By.ID, "advname-tabMenu")))
    driver.execute_script("arguments[0].click();", advocate_tab_button)
    print("\n👉 Switched to Advocate Search Tab")
    time.sleep(2)
except Exception as e:
    print("❌ Failed to click Advocate Tab:", e)
    driver.quit()
    exit()

advocate_name = input("\n✍️ Enter Advocate Name: ")
advocate_input = wait.until(EC.presence_of_element_located((By.ID, "advocate_name")))
advocate_input.clear()
advocate_input.send_keys(advocate_name)


try:
    modal = driver.find_element(By.ID, "validateError")
    if modal.is_displayed():
        close_btns = modal.find_elements(By.XPATH, ".//button[@data-dismiss='modal']")
        if close_btns:
            driver.execute_script("arguments[0].click();", close_btns[0])
            time.sleep(1)
except Exception:
    pass 

try:
    both_radio = wait.until(EC.element_to_be_clickable((By.ID, "radBAdvt")))
    driver.execute_script("arguments[0].click();", both_radio)
    case_status = "Both"
    print("\n🔍 Case Status set to: Both")
except Exception as e:
    print("❌ Error selecting 'Both' status:", e)
    driver.quit()
    exit()

MAX_ATTEMPTS = 10
for attempt in range(1, MAX_ATTEMPTS + 1):
    print(f"\n🔁 Attempt {attempt}: Solving CAPTCHA using Gemini Vision...")

    try:
        captcha_img = wait.until(EC.presence_of_element_located((By.ID, "captcha_image")))
        captcha_path = f"captcha_advocate_attempt_{attempt}.png"
        captcha_img.screenshot(captcha_path)
        print(f"📸 CAPTCHA image saved as '{captcha_path}'")

        # --- Gemini Vision OCR ---
        with open(captcha_path, "rb") as img_file:
            image_bytes = img_file.read()
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content([
            {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(image_bytes).decode()}},
            "Please extract the text shown in this CAPTCHA image."
        ])
        captcha_text = response.text.strip()
        print("🔍 CAPTCHA Text (Gemini):", captcha_text)
    except Exception as e:
        print("❌ CAPTCHA image or Gemini error:", e)
        continue

    try:
        captcha_input = wait.until(EC.element_to_be_clickable((By.ID, "adv_captcha_code")))
        captcha_input.clear()
        captcha_input.send_keys(captcha_text)
    except Exception as e:
        print("❌ CAPTCHA input error:", e)
        continue

    try:
        go_button = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//button[@onclick='submit_adv_name()']")
        ))
        driver.execute_script("arguments[0].click();", go_button)
        print("🧾 Submitted Advocate Form. Waiting for result...")
    except Exception as e:
        print("❌ Error clicking Go button:", e)
        continue

    time.sleep(4)
    if 'href="#td_court_name_' in driver.page_source or "case_details" in driver.page_source:
        print(f"✅ CAPTCHA correct. Case data for advocate '{advocate_name}' loaded successfully!\n")
        break
    else:
        print("❌ CAPTCHA incorrect or no data. Retrying...")
        driver.save_screenshot(f"captcha_adv_fail_attempt_{attempt}.png")
        with open(f"advocate_page_fail_attempt_{attempt}.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        time.sleep(2)
else:
    print("\n🚫 Failed after multiple CAPTCHA attempts. Please try again later.")
    driver.quit()
    exit()


try:
    wait.until(EC.presence_of_element_located((By.XPATH, "//table[contains(@class, 'table')]")))
except:
    print("❌ No case data table found.")
    driver.quit()
    exit()

# --- List Cases ---
rows = driver.find_elements(By.XPATH, "//table[contains(@class, 'table')]/tbody/tr")
cases = []
for idx, row in enumerate(rows, 1):
    link_elems = row.find_elements(By.XPATH, ".//a")
    if not link_elems:
        continue
    case_id = link_elems[0].get_attribute("onclick")
    title = row.text.strip().split('\n')[0]
    cases.append((idx, title, case_id))
    print(f"{idx}. {title}")

if not cases:
    print("❌ No cases found.")
    driver.quit()
    exit()

all_cases = []
for idx, title, onclick_code in cases:
    print(f"\n⏳ Loading case {idx}: {title}")
    try:
        # Get the onclick code directly
        onclick_attr = onclick_code
        print(f"🔍 Found onclick: {onclick_attr}")
        
        # Extract information from onclick
        onclick_parts = onclick_attr.replace('viewHistory(', '').replace(')', '').split(',')
        case_info = {
            
            'CNR Number': onclick_parts[1].strip().strip("'"),
            
        }
        all_cases.append(case_info)
    except Exception as e:
        print(f"❌ Error processing case {idx}: {str(e)}")
        continue

# Save all cases to a single JSON file
with open('all_cases.json', 'w', encoding='utf-8') as f:
    json.dump(all_cases, f, ensure_ascii=False, indent=2)
print("✅ All cases saved to all_cases.json")

