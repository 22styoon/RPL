from copy import deepcopy
import unittest
from src.model import load_config, evaluate, compare, best, annuity, sensitivity

class ModelTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_mass_conservation(self):
        for scenario in self.config['scenarios']:
            _, flow = evaluate(self.config, scenario)
            residual = flow.generated - flow.recycled - flow.uncollected - flow.sorting_loss - flow.processing_loss
            self.assertTrue((residual.abs() < 1e-8).all())
            self.assertTrue((flow.recycled <= flow.generated).all())

    def test_invalid_missing_units_and_rates(self):
        for value in (-0.1, 1.1, float('nan'), None):
            sample = deepcopy(self.config)
            sample['scenarios'][0]['rates']['paper'][0] = value
            with self.assertRaises(ValueError):
                compare(sample)
        self.config['units']['mass'] = 'kg/day'
        with self.assertRaises(ValueError):
            compare(self.config)

    def test_constraints_and_infeasibility(self):
        table = compare(self.config)
        self.assertFalse(bool(table.loc[table.id == 'C', 'feasible'].iloc[0]))
        self.assertIsNone(best(compare(self.config, 1.0)))
        for scenario in self.config['scenarios']:
            scenario['capacity_t'] = 0
        self.assertIsNone(best(compare(self.config)))

    def test_transfer_not_in_social_cost(self):
        scenario = self.config['scenarios'][0]
        before, _ = evaluate(self.config, scenario)
        scenario['epr_transfer'] = 999999999
        after, _ = evaluate(self.config, scenario)
        self.assertEqual(before['social_cost'], after['social_cost'])

    def test_annuity_and_reproducibility(self):
        self.assertEqual(annuity(100, 0, 10), 10)
        with self.assertRaises(ValueError):
            annuity(100, .03, 0)
        self.assertTrue(compare(self.config).equals(compare(self.config)))
        self.assertEqual(sensitivity(self.config).parameter.nunique(), 3)

if __name__ == '__main__':
    unittest.main()
