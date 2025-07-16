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
from langchain.chains import RetrievalQA

# === CONFIG ===
CHROME_DRIVER_PATH = r"C:\Users\91964\OneDrive\Desktop\Ecourts\chromedriver-win64\chromedriver.exe"
CNR_NUMBER = "APKR060043112021"
os.environ["GOOGLE_API_KEY"] = "AIzaSyCaiCtwdbOuUrWmuR6Z_RZPSPKj4v5dHT0"

# === STEP 1: Open Browser ===
service = Service(CHROME_DRIVER_PATH)
driver = webdriver.Chrome(service=service)
driver.get("https://services.ecourts.gov.in/ecourtindia_v6/")

# === STEP 2: Enter CNR ===
try:
    cnr_input = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "cino")))
    cnr_input.clear()
    cnr_input.send_keys(CNR_NUMBER)
    print("✅ CNR number entered.")
except Exception as e:
    print("❌ Failed to enter CNR:", e)
    driver.quit()
    exit()

# === STEP 3: Get and Show CAPTCHA ===
try:
    captcha_img = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "captcha_image")))
    captcha_url = captcha_img.get_attribute("src")
    if captcha_url.startswith("/"):
        captcha_url = "https://services.ecourts.gov.in" + captcha_url
    response = requests.get(captcha_url)
    img = Image.open(BytesIO(response.content))
    img.show()
except:
    print("❌ Failed to load CAPTCHA.")
    driver.quit()
    exit()

captcha_text = input("🔡 Enter CAPTCHA from image: ")

# === STEP 4: Submit Form ===
try:
    captcha_input = driver.find_element(By.ID, "fcaptcha_code")
    captcha_input.clear()
    captcha_input.send_keys(captcha_text)

    search_btn = driver.find_element(By.ID, "searchbtn")
    search_btn.click()
    print("🔁 Submitted form...")
except Exception as e:
    print("❌ Form submission failed:", e)
    driver.quit()
    exit()

# === STEP 5: Extract and Save Page Text (even if error) ===
time.sleep(5)  # wait for page to load
case_data_html = driver.page_source
soup = BeautifulSoup(case_data_html, "html.parser")
case_text = soup.get_text(separator="\n")

with open("case_data.txt", "w", encoding="utf-8") as f:
    f.write(case_text)

if "Case details not found" in case_text:
    print("⚠️ Case details not found — likely wrong CAPTCHA. Proceeding with page content anyway.")
else:
    print("✅ Case data found and saved.")

driver.quit()

# === STEP 6: RAG - Google Gemini QA ===
print("⚙️ Preparing Gemini Flash QA...")

# Load and split text
loader = TextLoader("case_data.txt", encoding="utf-8")
docs = loader.load()
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)

# Vector store
embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
db = FAISS.from_documents(chunks, embeddings)

# Gemini Flash 1.5
llm = ChatGoogleGenerativeAI(model="models/gemini-1.5-flash", temperature=0.2)

qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=db.as_retriever(search_type="similarity", k=3),
    return_source_documents=False
)

# === STEP 7: Ask Questions ===
print("\n✅ Ready! Ask anything about the case (type 'exit' to quit):")
while True:
    question = input("❓ Your question: ")
    if question.lower() == "exit":
        break
    answer = qa_chain.run(question)
    print("💬 Answer:", answer)
