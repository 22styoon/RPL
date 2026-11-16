"""재질 구성과 R의 기계적 연관을 진단하는 보조 회귀."""
import warnings
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.outliers_influence import variance_inflation_factor

SHARES = ["발생량구성_폐지류", "발생량구성_폐합성수지류", "발생량구성_폐금속류"]


def run_composition_diagnostics(materials: pd.DataFrame):
    data = materials.loc[materials.geography != "전국"].copy()
    rows = []
    for region, part in data.groupby("geography", sort=False):
        total = part.generated_t.sum()
        shares = part.set_index("material").generated_t / total
        rates = part.set_index("material").material_recycling_t / part.set_index("material").generated_t
        rows.append({"시도": region, "R_r(%)": float((shares * rates).sum() * 100),
                     **{f"발생량구성_{material}": float(shares[material]) for material in ("폐지류", "폐합성수지류", "폐금속류")}})
    frame = pd.DataFrame(rows)
    if len(frame) < 12 or frame[SHARES].isna().any().any():
        return {"status": "withheld", "reason": "시도 완전 관측 12개 미만", "n": len(frame)}
    y = frame["R_r(%)"].astype(float)
    x = sm.add_constant(frame[SHARES].astype(float), has_constant="add")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitted = sm.OLS(y, x).fit()
        hc0 = fitted.get_robustcov_results(cov_type="HC0")
        hc3 = fitted.get_robustcov_results(cov_type="HC3")
    restriction = np.zeros((len(SHARES), x.shape[1]))
    restriction[:, 1:] = np.eye(len(SHARES))
    def joint(model, name):
        test = model.f_test(restriction)
        return {"공분산": name, "통계량_F": float(np.asarray(test.fvalue).squeeze()),
                "분자_df": int(test.df_num), "분모_df": int(test.df_denom),
                "p값": float(np.asarray(test.pvalue).squeeze())}
    tests = pd.DataFrame([joint(fitted, "일반 OLS"), joint(hc0, "HC0 강건"), joint(hc3, "HC3 강건")])
    coefficients = []
    for index, term in enumerate(x.columns):
        coefficients.append({"항": term, "계수": float(fitted.params.iloc[index]),
            "일반 SE": float(fitted.bse.iloc[index]), "HC0 SE": float(hc0.bse[index]),
            "HC3 SE": float(hc3.bse[index]), "HC3 CI 하한": float(hc3.conf_int()[index, 0]),
            "HC3 CI 상한": float(hc3.conf_int()[index, 1])})
    residuals = np.asarray(fitted.resid)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bp = het_breuschpagan(residuals, x)
    influence = fitted.get_influence()
    diagnostics = pd.DataFrame({"시도": frame["시도"], "적합값": fitted.fittedvalues,
        "잔차": residuals, "레버리지": influence.hat_matrix_diag,
        "Cook 거리": influence.cooks_distance[0]})
    vif = []
    for i, term in enumerate(x.columns):
        if term == "const":
            continue
        vif.append({"항": term, "VIF": float(variance_inflation_factor(x.to_numpy(), i))})
    loo = []
    for excluded in frame["시도"]:
        keep = frame["시도"] != excluded
        sub_x = sm.add_constant(frame.loc[keep, SHARES], has_constant="add")
        sub_fit = sm.OLS(y.loc[keep], sub_x).fit()
        loo.append({"제외 시도": excluded, "n": int(keep.sum()), "R²": float(sub_fit.rsquared),
                    "F 통계량": float(sub_fit.fvalue), "F p값": float(sub_fit.f_pvalue),
                    **{f"계수_{term}": float(sub_fit.params[term]) for term in SHARES}})
    condition_number = float(np.linalg.cond(x.to_numpy()))
    result = {"status": "computed", "n": int(fitted.nobs), "residual_df": int(fitted.df_resid),
        "r_squared": float(fitted.rsquared), "condition_number": condition_number,
        "bp_lm": float(bp[0]), "bp_lm_p": float(bp[1]), "bp_f": float(bp[2]), "bp_f_p": float(bp[3]),
        "tests": tests, "coefficients": pd.DataFrame(coefficients), "vif": pd.DataFrame(vif),
        "diagnostics": diagnostics, "leave_one_out": pd.DataFrame(loo),
        "interpretation": "R_r은 동일한 재질별 발생량 구성비와 처리비율의 산술 결합이다. 이 회귀의 연관과 p값은 일부가 정의상 기계적으로 발생하므로 S_r의 타당성·정책효과 증거가 아니다."}
    return result
