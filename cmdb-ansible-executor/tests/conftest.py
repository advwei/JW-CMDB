import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ANSIBLE_BASE_DIR", tempfile.mkdtemp(prefix="ansible-base-"))
