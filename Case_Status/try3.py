import os
import time
import json
import sys
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (TimeoutException, NoSuchElementException, 
                                      WebDriverException, NoSuchDriverException,
                                      ElementClickInterceptedException)

class ECourtsScraper:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.chromedriver_path = self.get_chromedriver_path()
        self.setup_driver()
        
    def get_chromedriver_path(self):
        """Locate ChromeDriver in common locations"""
        possible_paths = [
            r"C:\Users\91964\OneDrive\Desktop\Ecourts\chromedriver-win64\chromedriver.exe",
            os.path.join(os.getcwd(), "chromedriver.exe"),
            os.path.join(os.getcwd(), "chromedriver-win64", "chromedriver.exe"),
            r"C:\chromedriver\chromedriver.exe"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                print(f"Found ChromeDriver at: {path}")
                return path
        
        print("\nERROR: ChromeDriver not found in any of these locations:")
        for path in possible_paths:
            print(f"- {path}")
        print("\nPlease download ChromeDriver from: https://chromedriver.chromium.org/")
        print("Make sure it matches your Chrome browser version")
        print("Place it in one of the locations above or specify the path when prompted")
        
        custom_path = input("\nEnter full path to chromedriver.exe (or press Enter to exit): ").strip()
        if custom_path and os.path.exists(custom_path):
            return custom_path
        
        sys.exit(1)

    def setup_driver(self):
        """Initialize the Chrome WebDriver with proper options"""
        try:
            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_argument("--disable-notifications")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-popup-blocking")
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            
            service = Service(executable_path=self.chromedriver_path)
            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait = WebDriverWait(self.driver, 20)
            print("\nWebDriver initialized successfully")
        except Exception as e:
            print(f"\nFailed to initialize WebDriver: {str(e)}")
            sys.exit(1)

    def select_dropdown_option(self, element_id, prompt):
        """Helper function to select options from dropdown menus"""
        try:
            dropdown = Select(self.wait.until(
                EC.presence_of_element_located((By.ID, element_id))
            ))
            
            options = [opt.text.strip() for opt in dropdown.options if opt.text.strip()]
            print(f"\n{prompt}:")
            for idx, opt in enumerate(options[1:], 1):
                print(f"{idx}. {opt}")
            
            while True:
                try:
                    choice = int(input("Enter your choice (number): "))
                    if 1 <= choice <= len(options[1:]):
                        dropdown.select_by_index(choice)
                        return options[choice]
                    print("Invalid choice. Please try again.")
                except ValueError:
                    print("Please enter a valid number.")
        except Exception as e:
            print(f"Error selecting dropdown option: {str(e)}")
            raise

    def handle_captcha(self, attempt):
        """Handle CAPTCHA input with retries"""
        try:
            # Wait for CAPTCHA image to load
            captcha_img = self.wait.until(
                EC.visibility_of_element_located((By.ID, "captcha_image"))
            )
            
            # Save CAPTCHA image
            captcha_path = f"captcha_attempt_{attempt}.png"
            captcha_img.screenshot(captcha_path)
            print(f"\nCAPTCHA image saved as: {captcha_path}")
            
            # Get user input for CAPTCHA
            captcha_text = input("Please enter the CAPTCHA text: ").strip()
            
            # Input CAPTCHA
            captcha_field = self.driver.find_element(By.ID, "case_captcha_code")
            captcha_field.clear()
            captcha_field.send_keys(captcha_text)
            
            return True
        except Exception as e:
            print(f"CAPTCHA handling failed: {str(e)}")
            return False

    def get_modal_text(self, modal, text):
        """Helper to extract text from modal"""
        try:
            element = modal.find_element(
                By.XPATH, f".//*[contains(text(),'{text}')]"
            )
            return element.text.split(":", 1)[-1].strip()
        except:
            return "Not available"

    def get_case_details(self):
        """Extract case details from the page"""
        try:
            # Wait for case details to load
            self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[@id='case_details']//table"))
            )
            
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            case_data = {"details": {}, "hearings": []}
            
            # Extract basic case information
            for row in soup.select("#case_details tr"):
                cols = row.find_all(["th", "td"])
                if len(cols) >= 2:
                    key = cols[0].get_text(" ", strip=True).replace(":", "").title()
                    value = cols[1].get_text(" ", strip=True)
                    if key and value:
                        case_data["details"][key] = value
            
            # Extract hearing details
            hearing_links = self.driver.find_elements(
                By.XPATH, "//a[contains(@onclick, 'viewBusiness')]"
            )
            
            for i, link in enumerate(hearing_links, 1):
                try:
                    hearing_date = link.text.strip()
                    if not hearing_date:
                        continue
                        
                    # Click hearing link
                    self.driver.execute_script("arguments[0].click();", link)
                    time.sleep(1.5)
                    
                    # Extract hearing details from modal
                    modal = self.wait.until(
                        EC.visibility_of_element_located((By.ID, "businessModal"))
                    )
                    
                    hearing_info = {
                        "Hearing Date": hearing_date,
                        "Business": self.get_modal_text(modal, "Business:"),
                        "Purpose": self.get_modal_text(modal, "Next Purpose:"),
                        "Next Hearing Date": self.get_modal_text(modal, "Next Hearing Date:")
                    }
                    
                    case_data["hearings"].append(hearing_info)
                    
                    # Close modal
                    close_btn = modal.find_element(
                        By.XPATH, ".//button[contains(text(),'Close')]"
                    )
                    close_btn.click()
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"Failed to process hearing {i}: {str(e)}")
                    continue
            
            return case_data
            
        except Exception as e:
            print(f"Failed to extract case details: {str(e)}")
            return None

    def close_validation_errors(self):
        """Close any validation error modals that might be blocking the UI"""
        try:
            # Wait for potential error modal
            error_modal = self.wait.until(
                EC.presence_of_element_located((By.ID, "validateError"))
            )
            
            # If modal is visible, close it
            if error_modal.is_displayed():
                print("\nClosing validation error message...")
                close_btn = error_modal.find_element(By.XPATH, ".//button[contains(text(),'OK')]")
                close_btn.click()
                time.sleep(1)
        except (TimeoutException, NoSuchElementException):
            # No error modal found, continue normally
            pass
        except Exception as e:
            print(f"Error handling validation modal: {str(e)}")

    def switch_to_case_number_tab(self):
        """Switch to the case number tab with error handling"""
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                # Close any validation errors first
                self.close_validation_errors()
                
                # Find and click the case number tab
                case_tab = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "casenumber-tabMenu"))
                )
                self.driver.execute_script("arguments[0].click();", case_tab)
                time.sleep(1)
                
                # Verify we switched successfully
                if "active" in case_tab.get_attribute("class"):
                    print("\nSuccessfully switched to Case Number tab")
                    return
                
            except ElementClickInterceptedException:
                print(f"\nAttempt {attempt}: Tab click intercepted by another element")
                self.close_validation_errors()
                time.sleep(2)
            except Exception as e:
                print(f"\nAttempt {attempt}: Error switching tabs - {str(e)}")
                time.sleep(2)
        
        print("\nFailed to switch to Case Number tab after multiple attempts")
        raise Exception("Could not switch to Case Number tab")

    def run(self):
        """Main execution flow"""
        try:
            # Open eCourts website
            self.driver.get("https://services.ecourts.gov.in/ecourtindia_v6/?p=casestatus/index&app_token=1c847047b60f905b3ec1f8455ae475a3240ff6ec263ab395e0eadce41cd6de0e")
            print("\nOpened eCourts website")
            time.sleep(2)
            
            # Select state, district, and court
            state = self.select_dropdown_option("sess_state_code", "Select State")
            time.sleep(1)
            
            district = self.select_dropdown_option("sess_dist_code", f"Select District in {state}")
            time.sleep(1)
            
            court = self.select_dropdown_option("court_complex_code", f"Select Court Complex in {district}")
            time.sleep(2)
            
            # Handle any validation errors before switching tabs
            self.close_validation_errors()
            
            # Switch to case number tab with retries
            self.switch_to_case_number_tab()
            
            # Select case type
            case_type = self.select_dropdown_option("case_type", "Select Case Type")
            time.sleep(1)
            
            # Input case details
            case_number = input("\nEnter Case Number (e.g., 43): ").strip()
            self.driver.find_element(By.ID, "search_case_no").send_keys(case_number)
            
            case_year = input("Enter Case Year (e.g., 2023): ").strip()
            self.driver.find_element(By.ID, "rgyear").send_keys(case_year)
            
            # CAPTCHA handling with retries
            for attempt in range(1, 6):
                print(f"\nAttempt {attempt} of 5")
                if not self.handle_captcha(attempt):
                    continue
                
                # Submit form
                submit_btn = self.driver.find_element(
                    By.XPATH, "//button[@onclick='submitCaseNo();']"
                )
                submit_btn.click()
                time.sleep(3)
                
                # Check if results loaded
                if 'td_court_name_' in self.driver.page_source:
                    print("\nSuccessfully loaded case results")
                    break
                
                print("Failed to load results. Trying again...")
            else:
                print("\nFailed after multiple attempts. Please try again later.")
                return
            
            # Select case from results
            cases = self.driver.find_elements(
                By.XPATH, "//table[@id='example']/tbody/tr"
            )
            
            if not cases:
                print("\nNo matching cases found")
                return
            
            print("\nAvailable Cases:")
            for idx, case in enumerate(cases, 1):
                case_text = case.text.split("\n")[0]
                print(f"{idx}. {case_text}")
            
            while True:
                try:
                    choice = int(input("\nSelect a case (enter number): "))
                    if 1 <= choice <= len(cases):
                        cases[choice-1].find_element(By.TAG_NAME, "a").click()
                        break
                    print("Invalid selection. Please try again.")
                except ValueError:
                    print("Please enter a valid number.")
            
            # Get case details
            print("\nFetching case details...")
            time.sleep(3)
            case_data = self.get_case_details()
            
            if case_data:
                # Save results
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"Case_Details_{timestamp}.json"
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(case_data, f, indent=4, ensure_ascii=False)
                
                print(f"\nSuccess! Case details saved to: {filename}")
            else:
                print("\nFailed to retrieve case details")
            
        except Exception as e:
            print(f"\nAn error occurred: {str(e)}")
        finally:
            input("\nPress Enter to close the browser...")
            if self.driver:
                self.driver.quit()

if __name__ == "__main__":
    scraper = ECourtsScraper()
    scraper.run()