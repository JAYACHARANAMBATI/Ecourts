import requests
from PIL import Image
from io import BytesIO
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# === Your configuration ===
CHROME_DRIVER_PATH = r"C:\Users\91964\OneDrive\Desktop\Ecourts\chromedriver-win64\chromedriver.exe"
CNR_NUMBER = "APKR060043112021"

# === Setup Chrome ===
service = Service(executable_path=CHROME_DRIVER_PATH)
driver = webdriver.Chrome(service=service)

# === Open the eCourts site ===
driver.get("https://services.ecourts.gov.in/ecourtindia_v6/")
time.sleep(2)  # Let the page load

# === Enter the CNR number ===
try:
    cnr_input = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "cino"))
    )
    cnr_input.clear()
    cnr_input.send_keys(CNR_NUMBER)
    print("✅ CNR number entered.")
except Exception as e:
    print("❌ Could not find CNR input field:", e)
    driver.quit()
    exit()

# === Load and display the CAPTCHA image ===
try:
    captcha_img = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "captcha_image"))
    )
    captcha_url = captcha_img.get_attribute("src")
    if captcha_url.startswith("/"):
        captcha_url = "https://services.ecourts.gov.in" + captcha_url

    response = requests.get(captcha_url)
    img = Image.open(BytesIO(response.content))
    img.show()
    print("🔍 CAPTCHA image displayed. Look at the image and enter below.")
except Exception as e:
    print("❌ Could not load CAPTCHA image:", e)
    driver.quit()
    exit()

# === Prompt user to enter CAPTCHA ===
captcha_text = input("📝 Please enter the CAPTCHA as shown in the image: ")

# === Fill CAPTCHA and click Search ===
try:
    captcha_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "fcaptcha_code"))
    )
    captcha_input.clear()
    captcha_input.send_keys(captcha_text)
    print("✅ CAPTCHA entered.")

    # ✅ FIXED ID: lowercase 'searchbtn'
    search_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, "searchbtn"))
    )
    search_button.click()
    print("🔁 Form submitted.")
except Exception as e:
    print("❌ Failed to enter CAPTCHA or click Search button:", e)
    driver.quit()
    exit()

# === Wait and print the case result ===
try:
    result_div = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CLASS_NAME, "caseStatusData"))
    )
    print("\n✅ === Case Status Details ===\n")
    print(result_div.text)
except:
    print("\n❌ Could not retrieve case details. CAPTCHA may be incorrect or CNR not found.")

input("\nPress Enter to close the browser...")
driver.quit()
