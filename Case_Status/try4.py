import os
import time
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain_core.documents import Document
from langchain.prompts import PromptTemplate

CHROME_DRIVER_PATH = r"C:\\Users\\91964\\OneDrive\\Desktop\\Ecourts\\chromedriver-win64\\chromedriver.exe"

def choose_option_from_select(select_element, prompt):
    options = select_element.options[1:]
    for i, option in enumerate(options, 1):
        print(f"{i}. {option.text.strip()}")
    while True:
        try:
            choice = int(input(prompt))
            if 1 <= choice <= len(options):
                select_element.select_by_index(choice)
                return options[choice - 1].text.strip()
            else:
                print("❌ Invalid number. Try again.")
        except ValueError:
            print("❌ Enter a valid number.")

def solve_and_load_case():
    service = Service(CHROME_DRIVER_PATH)
    driver = webdriver.Chrome(service=service)
    wait = WebDriverWait(driver, 15)
    try:
        driver.get("https://services.ecourts.gov.in/ecourtindia_v6/?p=casestatus/index&app_token=1c847047b60f905b3ec1f8455ae475a3240ff6ec263ab395e0eadce41cd6de0e")
        wait.until(EC.presence_of_element_located((By.ID, "sess_state_code")))

        # --- Select location ---
        state_dropdown = Select(driver.find_element(By.ID, "sess_state_code"))
        print("\n📍 Select State:")
        choose_option_from_select(state_dropdown, "➡️ Enter State choice: ")
        time.sleep(1)

        district_dropdown = Select(driver.find_element(By.ID, "sess_dist_code"))
        print("\n🏙️ Select District:")
        choose_option_from_select(district_dropdown, "➡️ Enter District choice: ")
        time.sleep(1)

        court_dropdown = Select(driver.find_element(By.ID, "court_complex_code"))
        print("\n🏛️ Select Court Complex:")
        choose_option_from_select(court_dropdown, "➡️ Enter Court Complex choice: ")
        time.sleep(1)

        # --- Close modal if exists ---
        try:
            WebDriverWait(driver, 3).until(
                EC.visibility_of_element_located((By.ID, "validateError"))
            )
            close_btn = driver.find_element(By.XPATH, "//div[@id='validateError']//button")
            close_btn.click()
            WebDriverWait(driver, 5).until_not(
                EC.visibility_of_element_located((By.ID, "validateError"))
            )
            print("✅ Modal closed.")
        except:
            print("✅ No modal.")

        wait.until(EC.element_to_be_clickable((By.ID, "casenumber-tabMenu"))).click()
        time.sleep(1)

        case_type_dropdown = Select(driver.find_element(By.ID, "case_type"))
        print("\n📂 Select Case Type:")
        choose_option_from_select(case_type_dropdown, "➡️ Enter Case Type choice: ")

        case_number = input("🔢 Enter Case Number (e.g., 43): ").strip()
        driver.find_element(By.ID, "search_case_no").send_keys(case_number)

        year = input("📅 Enter Case Year (e.g., 2023): ").strip()
        driver.find_element(By.ID, "rgyear").send_keys(year)

        # --- CAPTCHA and Submit ---
        for attempt in range(1, 11):
            print(f"\n🔁 Attempt {attempt}: Please solve the CAPTCHA...")
            captcha_img = wait.until(EC.presence_of_element_located((By.ID, "captcha_image")))
            captcha_img.screenshot(f"captcha_attempt_{attempt}.png")
            print(f"📸 CAPTCHA saved: captcha_attempt_{attempt}.png")

            captcha_text = input("🔤 Enter CAPTCHA: ")
            captcha_input = wait.until(EC.element_to_be_clickable((By.ID, "case_captcha_code")))
            captcha_input.clear()
            captcha_input.send_keys(captcha_text)

            go_btn = driver.find_element(By.XPATH, "//button[@onclick='submitCaseNo();']")
            driver.execute_script("arguments[0].click();", go_btn)
            time.sleep(3)

            if 'href="#td_court_name_' in driver.page_source:
                print("✅ CAPTCHA correct. Case list loaded.")
                break
        else:
            print("❌ CAPTCHA failed after 10 attempts.")
            driver.quit()
            return None, None

        # --- List Cases ---
        rows = driver.find_elements(By.XPATH, "//table[contains(@class, 'table')]/tbody/tr")
        cases = []
        for idx, row in enumerate(rows, 1):
            try:
                case_id = row.find_element(By.XPATH, ".//a").get_attribute("onclick")
                title = row.text.strip().split('\n')[0]
                cases.append((idx, title, case_id))
                print(f"{idx}. {title}")
            except:
                continue

        if not cases:
            print("❌ No cases found.")
            driver.quit()
            return None, None

        selected = int(input("➡️ Select case number: "))
        onclick_code = cases[selected - 1][2]
        driver.execute_script(onclick_code)
        print("⏳ Loading case details...")
        time.sleep(5)

        # --- Extract base case text ---
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        case_text = soup.get_text(separator="\n")

        # --- Extract all hearing links ---
        links = driver.find_elements(By.XPATH, "//a[contains(@onclick, 'viewBusiness') or contains(@onclick, 'showHearingDetails')]")
        print(f"📅 Found {len(links)} hearing entries.")

        hearings = []
        for idx, link in enumerate(links, 1):
            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", link)
                time.sleep(0.5)
                # Use JS click to avoid overlays
                driver.execute_script("arguments[0].click();", link)
                time.sleep(2)
                full_text = driver.execute_script("return document.body.innerText")
                lines = full_text.splitlines()
                business = next((line for line in lines if "Business" in line), "Business: Not mentioned").split(":", 1)[-1].strip()
                purpose = next((line for line in lines if "Next Purpose" in line), "Next Purpose: Not mentioned").split(":", 1)[-1].strip()
                hearing_date = next((line for line in lines if "Date" in line), "Date: Not mentioned").split(":", 1)[-1].strip()
                next_hearing = next((line for line in lines if "Next Hearing Date" in line), "Next Hearing Date: Not mentioned").split(":", 1)[-1].strip()
                hearings.append({
                    "Hearing Date": hearing_date or "Not available",
                    "Court": "Trial Court",
                    "Business": business or "Not available",
                    "Purpose": purpose or "Not available",
                    "Next Hearing Date": next_hearing or "Not available"
                })
                driver.back()
                time.sleep(2)
                # Re-find links after navigating back (DOM may reload)
                links = driver.find_elements(By.XPATH, "//a[contains(@onclick, 'viewBusiness') or contains(@onclick, 'showHearingDetails')]")
            except Exception as e:
                print(f"❌ Error extracting hearing {idx}: {e}")

        driver.quit()
        return case_text, hearings

    except Exception as e:
        print(f"❌ Error: {e}")
        driver.quit()
        return None, None

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

def extract_all_hearing_data(driver):
    hearings = []
    # Find all hearing links (with viewBusiness or showHearingDetails)
    links = driver.find_elements(By.XPATH, "//a[contains(@onclick, 'viewBusiness') or contains(@onclick, 'showHearingDetails')]")
    print(f"📅 Found {len(links)} hearing entries.")
    for idx, link in enumerate(links, 1):
        try:
            driver.execute_script("arguments[0].scrollIntoView();", link)
            link.click()
            time.sleep(2)
            full_text = driver.execute_script("return document.body.innerText")
            lines = full_text.splitlines()
            business = next((line for line in lines if "Business" in line), "Business: Not mentioned").split(":", 1)[-1].strip()
            purpose = next((line for line in lines if "Next Purpose" in line), "Next Purpose: Not mentioned").split(":", 1)[-1].strip()
            hearing_date = next((line for line in lines if "Date" in line), "Date: Not mentioned").split(":", 1)[-1].strip()
            next_hearing = next((line for line in lines if "Next Hearing Date" in line), "Next Hearing Date: Not mentioned").split(":", 1)[-1].strip()
            hearings.append({
                "Hearing Date": hearing_date or "Not available",
                "Court": "Trial Court",
                "Business": business or "Not available",
                "Purpose": purpose or "Not available",
                "Next Hearing Date": next_hearing or "Not available"
            })
            driver.back()
            time.sleep(2)
            # Re-find links after navigating back (DOM may reload)
            links = driver.find_elements(By.XPATH, "//a[contains(@onclick, 'viewBusiness') or contains(@onclick, 'showHearingDetails')]")
        except Exception as e:
            print(f"❌ Error extracting hearing {idx}: {e}")
    return hearings

def build_rag_chat(context_string):
    os.environ["GOOGLE_API_KEY"] = "AIzaSyAxGTzN-8qA8FSmGZtI3J0L2gjMpkO6MM4"  # Replace with your API Key

    docs = [Document(page_content=context_string)]
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(docs)

    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
    vectorstore = FAISS.from_documents(chunks, embeddings)

    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.2)

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

    return qa_chain

if __name__ == "__main__":
    print("\n🚀 Starting eCourt Automation & Gemini Chatbot...")

    case_text, hearings = solve_and_load_case()
    if case_text is None:
        print("❌ Could not fetch case details.")
        sys.exit()

    case_json = {
        "base_details": case_text,
        "hearings": hearings
    }

    # Save to JSON
    with open("case_data.json", "w", encoding="utf-8") as f:
        json.dump(case_json, f, ensure_ascii=False, indent=2)
    print("✅ All data saved to case_data.json")

    # === Vector Embedding & QA ===
    print("⚙️ Preparing data for Gemini Flash 1.5...")

    with open("case_data.json", "r", encoding="utf-8") as f:
        json_obj = json.load(f)

    context_string = f"=== CASE DETAILS ===\n{json_obj['base_details']}\n\n=== HEARINGS ===\n"
    for hearing in json_obj["hearings"]:
        context_string += (
            f"- Hearing Date: {hearing['Hearing Date']}, "
            f"Court: {hearing['Court']}, "
            f"Business: {hearing['Business']}, "
            f"Purpose: {hearing['Purpose']}, "
            f"Next Hearing Date: {hearing['Next Hearing Date']}\n"
        )

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
            print("👋 Exiting chatbot.")
            break
        try:
            result = qa_chain.run(query)
            print("\n💬 Answer:", result, "\n")
        except Exception as e:
            print(f"❌ Error during QA: {e}\n")
