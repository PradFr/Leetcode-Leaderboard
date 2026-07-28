import os
import sys

# Add the project root to the python path so that imports work correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
