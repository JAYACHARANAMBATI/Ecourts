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
os.environ["GOOGLE_API_KEY"] = "AIzaSyCaiCtwdbOuUrWmuR6Z_RZPSPKj4v5dHT0"  # Replace with your real key

# === Step 1: Launch Browser ===
service = Service(CHROME_DRIVER_PATH)
driver = webdriver.Chrome(service=service)
driver.get("https://services.ecourts.gov.in/ecourtindia_v6/")

# === Step 2: Enter CNR number and refresh CAPTCHA ===
try:
    cnr_input = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "cino")))
    cnr_input.clear()
    cnr_input.send_keys(CNR_NUMBER)
    print("✅ CNR number entered.")

    captcha_img_elem = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "captcha_image"))
    )
    print("🔍 CAPTCHA element located.")

    # Manually refresh CAPTCHA using JavaScript
    old_src = captcha_img_elem.get_attribute("src")
    driver.execute_script("""
        document.getElementById("captcha_image").src =
        "/ecourtindia_v6/vendor/securimage/securimage_show.php?" + Math.random();
    """)

    # Wait until it changes
    WebDriverWait(driver, 10).until(
        lambda d: d.find_element(By.ID, "captcha_image").get_attribute("src") != old_src
    )
    print("✅ CAPTCHA refreshed.")

    # Show CAPTCHA image
    captcha_img_url = driver.find_element(By.ID, "captcha_image").get_attribute("src")
    if captcha_img_url.startswith("/"):
        captcha_img_url = "https://services.ecourts.gov.in" + captcha_img_url

    img_data = requests.get(captcha_img_url).content
    image = Image.open(BytesIO(img_data))
    image.show()
    print("📸 CAPTCHA image opened. Please check the window.")

except Exception as e:
    print("❌ Error entering CNR or refreshing CAPTCHA:", e)
    driver.quit()
    exit()

# === Step 3: Ask user for CAPTCHA input ===
captcha_text = input("🔡 Enter CAPTCHA: ")

# === Step 4: Submit the form ===
try:
    captcha_input = driver.find_element(By.ID, "fcaptcha_code")
    captcha_input.clear()
    captcha_input.send_keys(captcha_text)

    search_btn = driver.find_element(By.ID, "searchbtn")
    search_btn.click()
    print("📨 Form submitted.")
except Exception as e:
    print("❌ Form submission failed:", e)
    driver.quit()
    exit()

# === Step 5: Wait and extract page data ===
time.sleep(5)
html = driver.page_source
soup = BeautifulSoup(html, "html.parser")
case_text = soup.get_text(separator="\n")

with open("case_data.txt", "w", encoding="utf-8") as f:
    f.write(case_text)

if "Case details not found" in case_text:
    print("⚠️ CAPTCHA might be wrong, no case found.")
    driver.quit()
    exit()
else:
    print("✅ Case data saved to file.")

driver.quit()

# === Step 6: Load to RAG model using Gemini ===
print("⚙️ Loading into Gemini Flash 1.5...")

loader = TextLoader("case_data.txt", encoding="utf-8")
docs = loader.load()

splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)

embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
vectorstore = FAISS.from_documents(chunks, embeddings)

llm = ChatGoogleGenerativeAI(model="models/gemini-1.5-flash", temperature=0.2)
qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=vectorstore.as_retriever())

# === Step 7: Ask questions ===
print("\n🤖 Ask any question related to this case (type 'exit' to stop)\n")
while True:
    query = input("❓ Ask: ")
    if query.lower() == "exit":
        break
    result = qa_chain.run(query)
    print("💬 Answer:", result)
