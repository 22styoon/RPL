import unittest
from streamlit.testing.v1 import AppTest

class DashboardTests(unittest.TestCase):
    def test_dashboard_and_infeasible_target(self):
        app = AppTest.from_file('app.py').run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        app.sidebar.slider[1].set_value(100).run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.metric[0].value, '충족 대안 없음')
