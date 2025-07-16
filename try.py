from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
from PIL import Image
from io import BytesIO
import time

# === Your configuration ===
CHROME_DRIVER_PATH = r"C:\Users\91964\OneDrive\Desktop\Ecourts\chromedriver-win64\chromedriver.exe"
CNR_NUMBER = "APKR060043112021"

# === Setup Chrome ===
service = Service(executable_path=CHROME_DRIVER_PATH)
driver = webdriver.Chrome(service=service)
driver.get("https://services.ecourts.gov.in/ecourtindia_v6/")

# === Wait for page to load ===
time.sleep(2)

# ✅ NO iframe switch — directly use the form

# === Enter the CNR number ===
try:
    cnr_input = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "cino"))
    )
    cnr_input.clear()
    cnr_input.send_keys(CNR_NUMBER)
except Exception as e:
    print("❌ Could not find CNR input field.")
    driver.quit()
    exit()

# === Get Captcha image ===
try:
    captcha_img = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "captcha_image"))
    )
    captcha_url = captcha_img.get_attribute("src")
    if captcha_url.startswith("/"):
        captcha_url = "https://services.ecourts.gov.in" + captcha_url

    # Download and show captcha
    captcha_response = requests.get(captcha_url)
    img = Image.open(BytesIO(captcha_response.content))
    img.show()
except Exception as e:
    print("❌ Could not load captcha image.")
    driver.quit()
    exit()

# === Ask user to type the captcha ===
captcha_text = input("Enter CAPTCHA as shown in the image: ")

# === Submit the form ===
try:
    captcha_input = driver.find_element(By.ID, "fcaptcha_code")
    captcha_input.send_keys(captcha_text)

    search_button = driver.find_element(By.ID, "searchBtn")
    search_button.click()
except:
    print("❌ Could not submit the form.")
    driver.quit()
    exit()

# === Wait and fetch result ===
time.sleep(5)

try:
    result = driver.find_element(By.CLASS_NAME, "caseStatusData")
    print("\n✅ === Case Status Details ===\n")
    print(result.text)
except:
    print("\n❌ Could not retrieve case details. CAPTCHA may be incorrect or case not found.")

input("\nPress Enter to close browser...")
driver.quit()
