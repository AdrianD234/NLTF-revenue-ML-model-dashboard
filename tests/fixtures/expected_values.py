from __future__ import annotations

EXPECTED_FINALIST_MAPE = {
    ("PED VKT per capita", "Quarterly MAPE"): 3.237144,
    ("PED VKT per capita", "Annual MAPE"): 2.033294,
    ("Light RUC volume", "Quarterly MAPE"): 5.363207,
    ("Light RUC volume", "Annual MAPE"): 1.273774,
    ("Heavy RUC volume", "Quarterly MAPE"): 2.809473,
    ("Heavy RUC volume", "Annual MAPE"): 2.061102,
}

EXPECTED_ENSEMBLE_WEIGHT_PCT = {
    "PED VKT per capita": [100.0],
    "Light RUC volume": [100.0],
    "Heavy RUC volume": [46.9332, 28.1844, 14.4373, 10.4451],
}

EXPECTED_STRESS_MAPE = {
    ("PED VKT per capita", "1-4 qtrs"): 1.738913,
    ("PED VKT per capita", "5-8 qtrs"): 2.263643,
    ("PED VKT per capita", "9-12 qtrs"): 5.353111,
    ("PED VKT per capita", "2024+"): float("nan"),
    ("PED VKT per capita", "2022-23"): 3.481973,
    ("PED VKT per capita", "Annual"): 2.033294,
    ("Light RUC volume", "1-4 qtrs"): 4.179904,
    ("Light RUC volume", "5-8 qtrs"): 3.780027,
    ("Light RUC volume", "9-12 qtrs"): 7.806239,
    ("Light RUC volume", "2024+"): float("nan"),
    ("Light RUC volume", "2022-23"): 9.100548,
    ("Light RUC volume", "Annual"): 1.273774,
    ("Heavy RUC volume", "1-4 qtrs"): 2.275400,
    ("Heavy RUC volume", "5-8 qtrs"): 2.499037,
    ("Heavy RUC volume", "9-12 qtrs"): 3.481058,
    ("Heavy RUC volume", "2024+"): float("nan"),
    ("Heavy RUC volume", "2022-23"): 2.478692,
    ("Heavy RUC volume", "Annual"): 2.061102,
}

EXPECTED_SCENARIO_COMPARISON = {
    "PED VKT per capita": {
        "scenario_a_quarterly_mape": 3.237144,
        "scenario_b_quarterly_mape": 4.674917,
        "full_sample_qtr_gain_pp": 1.437773,
        "scenario_a_annual_mape": 2.033294,
        "scenario_b_annual_mape": 3.585729,
        "full_sample_annual_gain_pp": 1.552435,
        "paired_gain_pp": 1.214456,
        "paired_win_rate_pct": 69.047619,
    },
    "Light RUC volume": {
        "scenario_a_quarterly_mape": 5.363207,
        "scenario_b_quarterly_mape": 8.521397,
        "full_sample_qtr_gain_pp": 3.158190,
        "scenario_a_annual_mape": 1.273774,
        "scenario_b_annual_mape": 2.702000,
        "full_sample_annual_gain_pp": 1.428227,
        "paired_gain_pp": 2.932205,
        "paired_win_rate_pct": 62.698413,
    },
    "Heavy RUC volume": {
        "scenario_a_quarterly_mape": 2.809473,
        "scenario_b_quarterly_mape": 8.761652,
        "full_sample_qtr_gain_pp": 5.952179,
        "scenario_a_annual_mape": 2.061102,
        "scenario_b_annual_mape": 8.879508,
        "full_sample_annual_gain_pp": 6.818406,
        "paired_gain_pp": 5.641798,
        "paired_win_rate_pct": 62.698413,
    },
}

EXPECTED_LIGHT_PAIRED_GAIN_PP = 2.932205

EXPECTED_FIXTURE_FINALISTS = {
    "PED": {"quarterly_mape": 2.473245, "annual_mape": 2.385625},
    "LIGHT_RUC": {"quarterly_mape": 9.147545, "annual_mape": 5.999499},
    "HEAVY_RUC": {"quarterly_mape": 3.484368, "annual_mape": 3.019980},
}
