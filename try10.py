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
from selenium.common.exceptions import TimeoutException

from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.chains import RetrievalQAWithSourcesChain

# === CONFIGURATION ===
CHROME_DRIVER_PATH = r"C:\\Users\\91964\\OneDrive\\Desktop\\Ecourts\\chromedriver-win64\\chromedriver.exe"
CNR_NUMBER = "APKR060043112021"
os.environ["GOOGLE_API_KEY"] = "AIzaSyCaiCtwdbOuUrWmuR6Z_RZPSPKj4v5dHT0"  # 🔁 Replace with your actual Gemini API key

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

detailed_texts = []

for index, link in enumerate(links):
    try:
        print(f"\n🔎 Extracting hearing {index + 1}...")
        driver.execute_script("arguments[0].scrollIntoView(true);", link)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", link)
        time.sleep(2.5)

        full_text = driver.execute_script("return document.body.innerText")
        detailed_texts.append(f"\n=== HEARING DETAIL {index + 1} ===\n{full_text.strip()}\n")
        print(f"✅ Hearing {index + 1} extracted.")

    except Exception as e:
        print(f"❌ Failed to extract hearing {index + 1}: {e}")

# === Step 7: Save all hearing details ===
with open("case_data.txt", "a", encoding="utf-8") as f:
    f.write("\n\n=== HEARING DETAILS ===\n")
    for text in detailed_texts:
        f.write(text)

print("✅ All hearing details saved.")
driver.quit()

# === Step 8: Load into Gemini Flash 1.5 and build Q&A ===
print("⚙️ Loading data into Gemini Flash 1.5...")

loader = TextLoader("case_data.txt", encoding="utf-8")
docs = loader.load()

splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)

embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
vectorstore = FAISS.from_documents(chunks, embeddings)

llm = ChatGoogleGenerativeAI(model="models/gemini-1.5-flash", temperature=0.2)
qa_chain = RetrievalQAWithSourcesChain.from_chain_type(llm=llm, retriever=vectorstore.as_retriever())

# === Step 9: Interactive Q&A chatbot ===
print("\n🤖 Ask about the case (type 'exit' to quit):")
while True:
    query = input("❓ Question: ")
    if query.lower() == "exit":
        break
    result = qa_chain.invoke({"question": query})
    print("\n💬 Answer:", result["answer"])
    if result.get("sources"):
        print("📚 Source(s):", result["sources"])
    print("\n")
