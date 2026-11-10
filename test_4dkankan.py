"""Legacy manual integration path; excluded from automatic test collection."""
from tools.integration.probe_scene_api import main, test_connection

__test__ = False
test_connection.__test__ = False

if __name__ == '__main__':
    raise SystemExit(main())
