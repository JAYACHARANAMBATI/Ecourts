import os
import time
import requests
from io import BytesIO
from PIL import Image
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA

# === CONFIGURATION ===
CHROME_DRIVER_PATH = r"C:\\Users\\91964\\OneDrive\\Desktop\\Ecourts\\chromedriver-win64\\chromedriver.exe"
CNR_NUMBER = "APKR060043112021"
os.environ["GOOGLE_API_KEY"] = "AIzaSyCaiCtwdbOuUrWmuR6Z_RZPSPKj4v5dHT0"

# === Step 1: Open eCourts ===
service = Service(CHROME_DRIVER_PATH)
driver = webdriver.Chrome(service=service)
driver.get("https://services.ecourts.gov.in/ecourtindia_v6/")

# === Step 2: Enter CNR and show CAPTCHA ===
try:
    cnr_input = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "cino")))
    cnr_input.clear()
    cnr_input.send_keys(CNR_NUMBER)
    print("✅ CNR number entered.")

    captcha_img_elem = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "captcha_image")))
    captcha_img_url = captcha_img_elem.get_attribute("src")
    if captcha_img_url.startswith("/"):
        captcha_img_url = "https://services.ecourts.gov.in" + captcha_img_url

    img_data = requests.get(captcha_img_url).content
    image = Image.open(BytesIO(img_data))
    image.show()
    print("📸 CAPTCHA image opened.")
except Exception as e:
    print("❌ CAPTCHA loading failed:", e)
    driver.quit()
    exit()

# === Step 3: Ask user for CAPTCHA ===
captcha_text = input("🔡 Enter CAPTCHA as seen in image: ")

# === Step 4: Submit the form ===
try:
    captcha_input = driver.find_element(By.ID, "fcaptcha_code")
    captcha_input.clear()
    captcha_input.send_keys(captcha_text)
    driver.find_element(By.ID, "searchbtn").click()
    print("📨 Form submitted.")
except Exception as e:
    print("❌ CAPTCHA submission error:", e)
    driver.quit()
    exit()

# === Step 5: Extract base case details ===
time.sleep(5)
soup = BeautifulSoup(driver.page_source, "html.parser")
case_text = soup.get_text(separator="\n")

with open("case_data.txt", "w", encoding="utf-8") as f:
    f.write("=== BASE CASE DETAILS ===\n")
    f.write(case_text)

if "Case details not found" in case_text:
    print("⚠️ Invalid CNR or CAPTCHA.")
    driver.quit()
    exit()

# === Step 6: Extract hearing details ===
print("🔄 Extracting hearing details...")
links = driver.find_elements(By.XPATH, "//a[contains(@onclick, 'viewBusiness')]")
print(f"📅 Found {len(links)} hearing entries.")

with open("case_data.txt", "a", encoding="utf-8") as f:
    f.write("\n\n=== HEARING DETAILS TABLE ===\n")
    f.write("| Hearing Date | Court | Business | Purpose | Next Hearing Date |\n")
    f.write("|--------------|--------|----------|---------|-------------------|\n")

    for index, link in enumerate(links):
        try:
            print(f"\n🔎 Extracting hearing {index + 1}...")
            driver.execute_script("arguments[0].scrollIntoView(true);", link)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", link)
            time.sleep(2.5)

            full_text = driver.execute_script("return document.body.innerText")
            lines = full_text.splitlines()

            business = next((line for line in lines if "Business" in line), "Business: Not mentioned")
            purpose = next((line for line in lines if "Next Purpose" in line), "Next Purpose: Not mentioned")
            hearing_date = next((line for line in lines if "Date" in line), "Date: Not mentioned")
            next_hearing = next((line for line in lines if "Next Hearing Date" in line), "Next Hearing Date: Not mentioned")
            court = "Trial Court"  # Can be enhanced later

            f.write(f"| {hearing_date.strip()} | {court} | {business.strip()} | {purpose.strip()} | {next_hearing.strip()} |\n")
            print(f"✅ Hearing {index + 1} saved.")

        except Exception as e:
            print(f"❌ Failed to extract hearing {index + 1}: {e}")

print("✅ All hearing details saved.")
driver.quit()

# === Step 7: Load into Gemini Flash 1.5 and build Q&A ===
print("⚙️ Loading data into Gemini Flash 1.5...")

loader = TextLoader("case_data.txt", encoding="utf-8")
docs = loader.load()

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

# === Step 8: Interactive Q&A chatbot ===
print("\n🤖 Ask about the case (type 'exit' to quit):")
while True:
    query = input("❓ Question: ")
    if query.lower() == "exit":
        break
    result = qa_chain.run(query)
    print("\n💬 Answer:", result, "\n")
