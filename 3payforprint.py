import time
import re
from playwright.sync_api import sync_playwright
from login import password, username, phonenumber  # credentials
import requests
from datetime import datetime

# Target endpoints
LOGIN_URL = "https://www.payforprint.ubc.ca/user"
PROTECTED_URL = "https://www.payforprint.ubc.ca/app?service=page/UserSummary"
CHECK_INTERVAL = 300  # Track every 5 minutes

INITIAL_BALANCE = 177.61
sms_sent = False
NTFY_TOPIC = "ubc-lostcard-alert-998877"

def send_sms_alert(amount_spent, current_balance):
    global sms_sent
    if sms_sent:
        return  # Already texted, don't waste free credits
        
    print("Sending emergency text message...")
    try:
        # response = requests.post('https://textbelt.com', {
        #     'phone': phonenumber,
        #     'message': f"⚠️ ALERT: UBC PayForPrint spending detected! ${amount_spent:.2f} spent. New Balance: ${current_balance:.2f}",
        #     'key': 'textbelt',  # Uses the free tier key
        # })

        response = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=f"⚠️ ALERT: UBC PayForPrint spending detected! ${amount_spent:.2f} spent. New Balance: ${current_balance:.2f}".encode('utf-8'),
            headers={
                "Title": "UBC Card Security Alert",
                "Priority": "high",  # This makes it bypass do-not-disturb on most phones
                "Tags": "warning,money_with_wings"
            }
        )
        
        if response.status_code == 200:
            print("📱 Notification/message sent successfully!")
            sms_sent = True
        else:
            print(f"❌ Notification failed with status: {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to reach gateway: {e}")

def check_balance(page):
    try:
        print("Navigating to dashboard...")
        page.goto(PROTECTED_URL)
        page.wait_for_load_state("networkidle")
        
        # Check if we got redirected back to login (meaning session expired)
        if "Log in" in page.title() or page.locator("input[type='password']").is_visible():
            print("Session expired or unauthenticated. Re-authenticating...")
            
            # Navigate to the base login page explicitly
            page.goto(LOGIN_URL)
            page.wait_for_load_state("load")
            
            # Fill out the form fields using type-based selectors to be framework-proof
            page.locator("input[type='text']").first.fill(username)
            page.locator("input[type='password']").fill(password)
            
            # Click the submit button and wait for page transition
            print("Submitting login form...")
            page.locator("input[type='submit']").click()
            page.wait_for_load_state("networkidle")
            
            # Confirm landing on dashboard
            page.goto(PROTECTED_URL)
            page.wait_for_load_state("networkidle")

        # --- Tracking Logic Here ---
        print("Successfully reached dashboard. Extracting state...")
        body_text = page.locator("body").inner_text()

         # Scans the text for the value next to the word "Balance"
        balance_match = re.search(r'Balance[:\s]*\$?\s*([0-9]+\.[0-9]{2})', body_text, re.IGNORECASE)

        if balance_match:
            current_balance = float(balance_match.group(1))
            print(f"[STATUS] Live Dashboard Balance: ${current_balance:.2f} (Expecting: ${INITIAL_BALANCE:.2f})")
            
            # Trigger alert if the balance has dropped below your hardcoded amount
            if current_balance < INITIAL_BALANCE:
                amount_spent = INITIAL_BALANCE - current_balance
                print(f"🚨 [ALERT] BALANCE DROPPED! ${amount_spent:.2f} has been spent!")
                print(f"Expected: ${INITIAL_BALANCE:.2f} -> Live: ${current_balance:.2f}")
                
                # Sound terminal alarm
                send_sms_alert(amount_spent, current_balance)                
                for _ in range(5):
                    print("\a")
                    time.sleep(0.2)
            else:
                print("[OK] No spending detected.")
        else:
            print("[WARNING] Could not parse balance from text. Check page layout.")
            
    except Exception as e:
        print(f"[ERROR] Tracker loop error: {e}")
               
        # Capture full text to inspect or look for specific balance containers
        page_text = page.content()
        
        # Example tracking marker: look for a balance indicator or keyword
        if "Summary" in page_text:
            print("[SUCCESS] Page successfully tracked.")
            # Optional: Print out a snippet of the page or save your metrics
            # print(page.locator("body").inner_text()[:400])
        else:
            print("[WARNING] Reached page, but 'Summary' structure was not found.")
            
    except Exception as e:
        print(f"[ERROR] An issue occurred during tracking loop: {e}")

if __name__ == "__main__":
    with sync_playwright() as p:
        # Launch browser. Set headless=False if you want to visually watch it log in!
        print("Launching automated browser context...")
        browser = p.chromium.launch(headless=True)
        
        # Opens an isolated browser session that handles cookies natively
        context = browser.new_context()
        page = context.new_page()
        
        print("Starting monitoring loops...")
        try:
            while True:
                check_balance(page)
                print(f"Waiting {CHECK_INTERVAL} seconds until next check...")
                print(datetime.now())
                time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\nTracker stopped manually.")
        finally:
            browser.close()