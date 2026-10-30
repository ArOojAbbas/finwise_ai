import os
from dotenv import load_dotenv

# .env file se key load karo
load_dotenv(override=True)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Model settings
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.3
MODEL_OPTIONS = ["gpt-4o-mini", "gpt-4o"]

# Cache settings (InMemoryCache ya SQLiteCache)
CACHE_OPTIONS = ["InMemoryCache", "SQLiteCache"]
SQLITE_DB_PATH = "finwise_cache.db"

# Form options (PDF section 8)
EXPENSE_CATEGORIES = [
    "Housing/Rent",
    "Food",
    "Transportation",
    "Utilities",
    "Education",
    "Healthcare",
    "Entertainment",
    "Loan/Debt",
    "Other",
]

FINANCIAL_GOALS = [
    "Save money",
    "Emergency fund",
    "Pay off debt",
    "Vacation",
    "Start a business",
    "Improve budgeting",
]

CURRENCIES = ["PKR", "USD", "EUR", "GBP", "AED", "SAR", "INR"]

# Har screen par dikhane wala disclaimer
EDUCATIONAL_DISCLAIMER = (
    "This app is for informational and educational purposes only. "
    "It is not financial advice. Please consult a qualified financial professional."
)