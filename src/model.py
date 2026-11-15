"""Deterministic, synthetic annual material and real-resource cost model."""
from copy import deepcopy
from math import isfinite
from pathlib import Path
import yaml
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def number(value, name, upper=None):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) or value < 0:
        raise ValueError(f'{name}: finite nonnegative number required')
    if upper is not None and value > upper:
        raise ValueError(f'{name}: must be <= {upper}')
    return value

def load_config(path=None):
    with open(path or ROOT / 'configs/scenarios.yaml', encoding='utf-8') as stream:
        return yaml.safe_load(stream)

def annuity(capital, rate, years):
    number(capital, 'capital'); number(rate, 'discount_rate'); number(years, 'life_years')
    if years == 0:
        raise ValueError('life_years must be positive')
    return capital / years if rate == 0 else capital * rate / (1 - (1 + rate) ** (-years))

def evaluate(config, scenario):
    if config['units'] != {'mass': 't/year', 'cost': 'KRW/year', 'time': 'hours/household/year'}:
        raise ValueError('Unsupported units')
    common = config['common']
    for key, value in common.items():
        number(value, key)
    for key, value in scenario.items():
        if key not in ('id', 'name', 'rates', 'exploratory'):
            number(value, key)
    if set(scenario['rates']) != set(config['materials']):
        raise ValueError('Material coverage mismatch')
    rows = []
    for material, mass in config['materials'].items():
        number(mass, material)
        rates = scenario['rates'][material]
        if len(rates) != 3:
            raise ValueError('Three stage rates required')
        c, s, y = [number(v, f'{material} rate', 1) for v in rates]
        collected, sorted_mass, recycled = mass*c, mass*c*s, mass*c*s*y
        rows.append(dict(material=material, generated=mass, collected=collected,
                         sorted=sorted_mass, recycled=recycled, uncollected=mass-collected,
                         sorting_loss=collected-sorted_mass, processing_loss=sorted_mass-recycled,
                         disposal=mass-recycled))
    flows = pd.DataFrame(rows)
    mass = flows.generated.sum()
    if mass <= 0:
        raise ValueError('Positive total generation required')
    costs = {
        'household': common['households'] * (scenario['hours']*common['time_value'] + scenario['utilities']),
        'collection': flows.collected.sum()*scenario['collection_per_t'],
        'sorting': flows.collected.sum()*scenario['sorting_per_t'] + annuity(scenario['capital'], common['discount_rate'], common['life_years']),
        'reprocessing': flows.sorted.sum()*common['reprocessing_per_t'],
        'disposal': flows.disposal.sum()*common['disposal_per_t'],
        'producer_real': scenario['producer_real'],
    }
    capacity_ok = flows.collected.sum() <= scenario['capacity_t']
    return dict(id=scenario['id'], name=scenario['name'], final_rate=flows.recycled.sum()/mass,
                recycled_t=flows.recycled.sum(), disposal_t=flows.disposal.sum(),
                social_cost=sum(costs.values()), capacity_ok=bool(capacity_ok),
                exploratory=scenario['exploratory'], evidence_grade='D', **costs), flows

def compare(config, target=None):
    records = [evaluate(config, s)[0] for s in config['scenarios']]
    table = pd.DataFrame(records)
    baseline = table.loc[table.id == 'A', 'final_rate']
    if len(baseline) != 1 or table.id.duplicated().any():
        raise ValueError('Exactly one baseline A and unique IDs required')
    floor = float(baseline.iloc[0])
    if target is not None:
        floor = max(floor, number(target, 'target', 1))
    table['feasible'] = (table.final_rate + 1e-12 >= floor) & table.capacity_ok & ~table.exploratory
    table['savings_vs_a'] = float(table.loc[table.id == 'A', 'social_cost'].iloc[0]) - table.social_cost
    return table

def best(table):
    candidates = table.loc[table.feasible]
    return None if candidates.empty else candidates.loc[candidates.social_cost.idxmin(), 'id']

def sensitivity(config):
    rows = []
    for parameter in ('time_value', 'reprocessing_per_t', 'disposal_per_t'):
        for factor in (0.5, 1.0, 1.5):
            sample = deepcopy(config)
            sample['common'][parameter] *= factor
            table = compare(sample)
            for row in table.to_dict('records'):
                rows.append(dict(parameter=parameter, factor=factor, selected=best(table), **row))
    return pd.DataFrame(rows)
