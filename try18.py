import os
import sys
import time
import json
import requests
from io import BytesIO
from PIL import Image
from bs4 import BeautifulSoup

import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\91964\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA

# === Config ===
CHROME_DRIVER_PATH = r"C:\\Users\\91964\\OneDrive\\Desktop\\Ecourts\\chromedriver-win64\\chromedriver.exe"
CNR_NUMBER = "APKR050031942023"
os.environ["GOOGLE_API_KEY"] = "AIzaSyCaiCtwdbOuUrWmuR6Z_RZPSPKj4v5dHT0"
MAX_CAPTCHA_ATTEMPTS = 10

# === CAPTCHA Solver and Page Loader Loop ===
def solve_and_load_case():
    for attempt in range(1, MAX_CAPTCHA_ATTEMPTS + 1):
        print(f"\n🔁 Attempt {attempt} of {MAX_CAPTCHA_ATTEMPTS}")

        # Setup browser
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        driver = webdriver.Chrome(service=Service(CHROME_DRIVER_PATH), options=options)
        driver.get("https://services.ecourts.gov.in/ecourtindia_v6/")

        try:
            # Enter CNR
            cnr_input = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "cino")))
            cnr_input.clear()
            cnr_input.send_keys(CNR_NUMBER)
            print("✅ CNR number entered.")

            # Get CAPTCHA image
            captcha_img_elem = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "captcha_image")))
            captcha_img_url = captcha_img_elem.get_attribute("src")
            if captcha_img_url.startswith("/"):
                captcha_img_url = "https://services.ecourts.gov.in" + captcha_img_url

            img_data = requests.get(captcha_img_url).content
            image = Image.open(BytesIO(img_data))
            image.save("captcha.png")

            captcha_text = pytesseract.image_to_string(image).strip()
            captcha_text = ''.join(filter(str.isalnum, captcha_text))
            print("🔍 Solved CAPTCHA:", captcha_text)

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

            print(f"📅 Found {len(links)} hearing entries.")
            return driver, soup, links

        except Exception as e:
            print("❌ Unexpected error:", e)
            driver.quit()
            continue

    print("❌ All attempts failed. Exiting.")
    sys.exit()

# === Run the CAPTCHA loop ===
driver, soup, links = solve_and_load_case()

# === Extract Case Details ===
case_text = soup.get_text(separator="\n")
case_json = {
    "base_details": case_text,
    "hearings": []
}

for index, link in enumerate(links):
    try:
        print(f"\n🔎 Extracting hearing {index + 1}...")
        driver.execute_script("arguments[0].scrollIntoView(true);", link)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", link)
        time.sleep(2.5)

        full_text = driver.execute_script("return document.body.innerText")
        lines = full_text.splitlines()

        business = next((line for line in lines if "Business" in line), "Business: Not mentioned").split(":", 1)[-1].strip()
        purpose = next((line for line in lines if "Next Purpose" in line), "Next Purpose: Not mentioned").split(":", 1)[-1].strip()
        hearing_date = next((line for line in lines if "Date" in line), "Date: Not mentioned").split(":", 1)[-1].strip()
        next_hearing = next((line for line in lines if "Next Hearing Date" in line), "Next Hearing Date: Not mentioned").split(":", 1)[-1].strip()
        court = "Trial Court"

        hearing_data = {
            "Hearing Date": hearing_date or "Not available",
            "Court": court,
            "Business": business or "Not available",
            "Purpose": purpose or "Not available",
            "Next Hearing Date": next_hearing or "Not available"
        }

        case_json["hearings"].append(hearing_data)
        print(f"✅ Hearing {index + 1} saved.")
    except Exception as e:
        print(f"❌ Failed to extract hearing {index + 1}: {e}")

driver.quit()

# === Save JSON ===
with open("case_data.json", "w", encoding="utf-8") as f:
    json.dump(case_json, f, ensure_ascii=False, indent=2)
print("✅ All data saved to case_data.json")

# === Vector Embedding & LLM ===
print("⚙️ Preparing data for Gemini Flash 1.5...")

with open("case_data.json", "r", encoding="utf-8") as f:
    json_obj = json.load(f)

context_string = f"=== CASE DETAILS ===\n{json_obj['base_details']}\n\n=== HEARINGS ===\n"
for hearing in json_obj["hearings"]:
    context_string += f"- Hearing Date: {hearing['Hearing Date']}, Court: {hearing['Court']}, Business: {hearing['Business']}, Purpose: {hearing['Purpose']}, Next Hearing Date: {hearing['Next Hearing Date']}\n"

docs = [Document(page_content=context_string)]
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)

embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
vectorstore = FAISS.from_documents(chunks, embeddings)

llm = ChatGoogleGenerativeAI(model="models/gemini-1.5-flash", temperature=0.2)

system_prompt = """
You are a helpful and intelligent AI assistant designed to extract, summarize, and answer queries about Indian eCourt case hearing data.

Your tasks include:
1. Understanding and interpreting legal hearing content.
2. Answering questions clearly and factually based on the hearing context.
3. If the user asks to list all hearings, output the data in a clean markdown table with columns:
   | Hearing Date | Court | Business | Purpose | Next Hearing Date |

Guidelines:
- If specific date data is missing, say: "Not available".
- For unclear queries, ask the user to rephrase.
- If asked for full details, extract *all hearing entries* with full fields available.
- Always prioritize clarity and completeness.
"""

prompt = PromptTemplate(
    input_variables=["context", "question"],
    template=system_prompt + "\n\nContext:\n{context}\n\nQuestion: {question}\nAnswer:"
)

qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=vectorstore.as_retriever(),
    chain_type_kwargs={"prompt": prompt}
)

# === Query Interface ===
print("\n🤖 Ask about the case (type 'exit' to quit):")
while True:
    query = input("❓ Question: ")
    if query.lower() == "exit":
        break
    result = qa_chain.run(query)
    print("\n💬 Answer:", result, "\n")
