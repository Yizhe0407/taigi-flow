import os
from dotenv import load_dotenv

# Load root .env
# __file__ is /Users/yizhe/Developer/taigi-flow/worker/tests/conftest.py
# parent is /Users/yizhe/Developer/taigi-flow/worker/tests/
# parent.parent is /Users/yizhe/Developer/taigi-flow/worker/
# parent.parent.parent is /Users/yizhe/Developer/taigi-flow/
root_env = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
load_dotenv(dotenv_path=root_env)
