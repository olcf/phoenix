import os

# phoenix reads conf_path at import time, so this has to be set before any
# phoenix module is imported.
os.environ.setdefault('PHOENIX_CONF', os.path.join(os.path.dirname(__file__), 'conf'))
