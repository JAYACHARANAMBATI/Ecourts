import os
import time
import requests
from io import BytesIO
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# LangChain & Gemini
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import RetrievalQA

# ===== CONFIG =====
CHROME_DRIVER_PATH = r"C:\Users\91964\OneDrive\Desktop\Ecourts\chromedriver-win64\chromedriver.exe"
CNR_NUMBER = "APKR060043112021"
os.environ["GOOGLE_API_KEY"] = "AIzaSyCaiCtwdbOuUrWmuR6Z_RZPSPKj4v5dHT0"  # Replace with your Gemini key

# ===== STEP 1: Scrape eCourts Case Details =====
service = Service(executable_path=CHROME_DRIVER_PATH)
driver = webdriver.Chrome(service=service)
driver.get("https://services.ecourts.gov.in/ecourtindia_v6/")
time.sleep(2)

try:
    cnr_input = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "cino")))
    cnr_input.clear()
    cnr_input.send_keys(CNR_NUMBER)
    print("✅ CNR number entered.")
except Exception as e:
    print("❌ Failed to enter CNR:", e)
    driver.quit()
    exit()

# CAPTCHA
try:
    captcha_img = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "captcha_image")))
    captcha_url = captcha_img.get_attribute("src")
    if captcha_url.startswith("/"):
        captcha_url = "https://services.ecourts.gov.in" + captcha_url
    response = requests.get(captcha_url)
    img = Image.open(BytesIO(response.content))
    img.show()
except:
    print("❌ Failed to load captcha.")
    driver.quit()
    exit()

# Manual CAPTCHA input
captcha_text = input("🔡 Enter CAPTCHA from image: ")

# Submit the form
try:
    captcha_input = driver.find_element(By.ID, "fcaptcha_code")
    captcha_input.clear()
    captcha_input.send_keys(captcha_text)
    search_btn = driver.find_element(By.ID, "searchbtn")
    search_btn.click()
    print("🔁 Submitted form...")
except Exception as e:
    print("❌ Submission failed:", e)
    driver.quit()
    exit()

# Wait for result
try:
    result_div = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CLASS_NAME, "caseStatusData"))
    )
    case_text = result_div.text
    with open("case_data.txt", "w", encoding="utf-8") as f:
        f.write(case_text)
    print("📄 Case data saved to file.")
except:
    print("❌ Case details not found (wrong captcha?).")
    driver.quit()
    exit()

driver.quit()

# ===== STEP 2: Use LangChain + Gemini Flash for RAG =====

# Load the case data
loader = TextLoader("case_data.txt")
docs = loader.load()

# Split into chunks
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)

# Create vector DB using Gemini embeddings
embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
db = FAISS.from_documents(chunks, embeddings)

# Load Gemini Flash 1.5 model
llm = GoogleGenerativeAI(model="models/gemini-1.5-flash", temperature=0)

# RAG QA chain
qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=db.as_retriever(search_type="similarity", k=3),
    return_source_documents=False
)

# ===== STEP 3: Ask Questions =====
while True:
    question = input("\n❓ Ask your question (or 'exit'): ")
    if question.lower() == "exit":
        break
    response = qa_chain.run(question)
    print("💬 Answer:", response)
